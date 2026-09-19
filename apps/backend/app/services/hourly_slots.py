"""Franjas de 3 h y lecturas puntuales sobre la serie horaria de Open-Meteo (funciones puras, sin I/O).

Las usan el dashboard (tira horaria y lluvia de las próximas 24 h) y las herramientas (tender ropa,
hacer deporte, cota de nieve): todos leen la misma serie, así que muestran lo mismo. Windy no entra:
la key del plan Testing "returns randomly shuffled and slightly modified data" (ver
https://api.windy.com/point-forecast/pricing).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypeVar

from app.services.openmeteo import HourlyForecastExt

# Franjas de 3 h (las horas locales 00, 03, 06… 21), como siempre mostró la tira horaria.
SLOT_HOURS = 3
HOUR_S = 3600

_T = TypeVar("_T")


@dataclass(frozen=True)
class Slot:
    """Una franja de 3 h armada con las horas de Open-Meteo que terminan en `hour_label`.

    Lo acumulado o extremo (lluvia, probabilidad, ráfaga, CAPE, código de tiempo) abarca las 3 h
    previas, como el `past3hprecip` de Windy; lo instantáneo (temperatura, humedad, viento, nubosidad)
    es el valor de la hora en punto.
    """
    timestamp: int
    hour_label: str
    date: str
    temp_c: float | None
    precip_mm: float | None
    precip_prob: float | None
    weather_code: int | None
    is_day: bool
    wind_speed_kmh: float | None
    wind_gust_kmh: float | None
    cape_j_kg: float | None
    freezing_level_m: float | None
    humidity: float | None
    cloud_cover: float | None


def window(values: list[_T | None], index: int) -> list[_T]:
    """Los valores no nulos de las 3 h que terminan en `index` (inclusive)."""
    start = max(0, index - SLOT_HOURS + 1)
    return [v for v in values[start:index + 1] if v is not None]


def at(values: list[_T | None], index: int) -> _T | None:
    """El valor en `index`, o None si la serie es más corta (variable que Open-Meteo no mandó)."""
    return values[index] if index < len(values) else None


def three_hour_slots(om: HourlyForecastExt) -> list[Slot]:
    """Una franja cada 3 h, en las horas locales múltiplo de 3. Sin dato no se inventa un cero."""
    slots: list[Slot] = []
    for i, label in enumerate(om.hour_labels):
        if int(label[:2]) % SLOT_HOURS:
            continue
        rain = window(om.precipitations, i)
        probs = window(om.precip_probs, i)
        codes = window(om.weather_codes, i)
        gusts = window(om.wind_gusts_kmh, i)
        capes = window(om.cape_j_kg, i)
        slots.append(
            Slot(
                timestamp=om.timestamps[i],
                hour_label=label,
                date=om.dates[i],
                temp_c=at(om.temps_c, i),
                precip_mm=round(sum(rain), 2) if rain else None,
                precip_prob=max(probs) if probs else None,
                # El peor código de las 3 h (los códigos WMO crecen con la severidad).
                weather_code=max(codes) if codes else None,
                is_day=om.is_day[i] if i < len(om.is_day) else True,
                wind_speed_kmh=at(om.wind_speeds, i),
                wind_gust_kmh=max(gusts) if gusts else None,
                cape_j_kg=max(capes) if capes else None,
                freezing_level_m=at(om.freezing_level_heights_m, i),
                humidity=at(om.humidities, i),
                cloud_cover=at(om.cloud_covers, i),
            )
        )
    return slots


def upcoming_slots(
    om: HourlyForecastExt,
    now: datetime,
    limit: int | None = None,
    grace_s: int = HOUR_S,
) -> list[Slot]:
    """Las franjas que vienen, desde la que cubre la hora en curso (igual que el frontend).

    `grace_s` es cuánto puede haber terminado una franja para seguir contando como la de ahora.
    """
    cutoff = now.timestamp() - grace_s
    slots = [s for s in three_hour_slots(om) if s.timestamp > cutoff]
    return slots if limit is None else slots[:limit]


def nearest_hour_index(om: HourlyForecastExt, now: datetime) -> int | None:
    """Índice de la hora de la serie más cercana a `now`; None si la serie está vacía."""
    if not om.timestamps:
        return None
    target = now.timestamp()
    return min(range(len(om.timestamps)), key=lambda i: abs(om.timestamps[i] - target))


def next_hour_index(om: HourlyForecastExt, now: datetime) -> int | None:
    """Índice de la primera hora de la serie posterior a `now`: la que cierra la hora en curso, cuya
    lluvia (acumulada de la hora previa) todavía no terminó de caer. None si la serie ya terminó."""
    target = now.timestamp()
    return next((i for i, stamp in enumerate(om.timestamps) if stamp > target), None)


def current_temp_850(om: HourlyForecastExt | None, now: datetime | None = None) -> float | None:
    """Temperatura a 850 hPa de la hora más cercana a `now` (insumo de la cota de nieve), o None."""
    if om is None or not om.temps_850_c:
        return None
    nearest = nearest_hour_index(om, now or datetime.now(timezone.utc))
    return None if nearest is None else at(om.temps_850_c, nearest)
