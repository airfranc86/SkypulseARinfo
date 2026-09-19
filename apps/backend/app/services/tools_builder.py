"""Armado de los datos de las herramientas (tender ropa, hacer deporte, lavar el auto) desde Open-Meteo.

Funciones puras sobre la serie horaria (`HourlyForecastExt`), sin I/O: las mismas que usa el dashboard,
así una herramienta y la página de Previsión cuentan lo mismo. Windy no interviene: la key del plan
Testing "returns randomly shuffled and slightly modified data" (ver
https://api.windy.com/point-forecast/pricing).

- `conditions_now` y `outlook`: la temperatura, humedad y viento de la hora en curso, y lo que viene en
  las próximas horas (lluvia acumulada, CAPE máximo, primer código de tormenta).
- `slot_scores`: el puntaje de cada franja de 3 h de la tira.
- `daily_aggregates`: un día por fecha local a partir de las horas, para los pronósticos de varios días.
  Los totales salen de la misma serie de la tira (best_match) y pueden diferir del consenso de dos
  modelos de las tarjetas de 7 días de Previsión.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, TypeVar

from app.schemas.tools import HourlyScore, ToolResult
from app.services.calculators import is_storm_wmo_code
from app.services.hourly_slots import Slot, at, nearest_hour_index, next_hour_index
from app.services.openmeteo import HourlyForecastExt
from app.utils.geo import degrees_to_cardinal_es

ScoreFn = Callable[..., ToolResult]

_T = TypeVar("_T")


@dataclass(frozen=True)
class NowConditions:
    """Lo instantáneo de la hora de la serie más cercana a ahora. None = la serie no lo trae."""
    temp_c: float | None
    humidity: float | None
    wind_speed_kmh: float | None


@dataclass(frozen=True)
class Outlook:
    """Lo que viene en las próximas horas. None = sin dato (no se inventa un cielo tranquilo)."""
    precip_mm: float | None
    cape_j_kg: float | None
    storm_code: int | None


@dataclass(frozen=True)
class DayAggregate:
    """Un día local armado con sus horas. None = ninguna hora del día trae esa variable."""
    date: str
    temp_max_c: float | None
    temp_min_c: float | None
    humidity_mean: float | None
    wind_speed_mean_kmh: float | None
    wind_speed_max_kmh: float | None
    wind_dir_cardinal: str | None
    precip_sum_mm: float | None
    precip_prob_max: float | None
    weather_code: int | None
    cape_max_j_kg: float | None


# ---------------------------------------------------------------------------
# Ahora y las próximas horas
# ---------------------------------------------------------------------------

def conditions_now(om: HourlyForecastExt, now: datetime) -> NowConditions:
    """Temperatura, humedad y viento de la hora más cercana a `now`."""
    index = nearest_hour_index(om, now)
    if index is None:
        return NowConditions(temp_c=None, humidity=None, wind_speed_kmh=None)
    return NowConditions(
        temp_c=at(om.temps_c, index),
        humidity=at(om.humidities, index),
        wind_speed_kmh=at(om.wind_speeds, index),
    )


def outlook(om: HourlyForecastExt, now: datetime, hours: int) -> Outlook:
    """Lluvia acumulada, CAPE máximo y primer código de tormenta de las `hours` horas que arrancan en la
    primera hora de la serie posterior a `now`: la que cierra la hora en curso. Lo que ya pasó (la lluvia
    o la tormenta de hace una hora) no cuenta como lo que viene."""
    start = next_hour_index(om, now)
    if start is None:
        return Outlook(precip_mm=None, cape_j_kg=None, storm_code=None)
    end = start + hours
    rain = [v for v in om.precipitations[start:end] if v is not None]
    capes = [v for v in om.cape_j_kg[start:end] if v is not None]
    storm = next((c for c in om.weather_codes[start:end] if is_storm_wmo_code(c)), None)
    return Outlook(
        precip_mm=round(sum(rain), 2) if rain else None,
        cape_j_kg=max(capes) if capes else None,
        storm_code=storm,
    )


# ---------------------------------------------------------------------------
# Tira de franjas
# ---------------------------------------------------------------------------

def slot_scores(slots: list[Slot], score_fn: ScoreFn) -> list[HourlyScore]:
    """El puntaje de cada franja con sus propias condiciones (`score_fn(temp, humedad, viento, lluvia,
    weather_code=…, cape_j_kg=…)`)."""
    return [
        HourlyScore(
            timestamp=s.timestamp,
            hour_label=s.hour_label,
            score=score_fn(
                s.temp_c, s.humidity, s.wind_speed_kmh, s.precip_mm,
                weather_code=s.weather_code, cape_j_kg=s.cape_j_kg,
            ).score,
            is_best=False,
        )
        for s in slots
    ]


# ---------------------------------------------------------------------------
# Un día por fecha
# ---------------------------------------------------------------------------

def _present(values: list[_T | None], indexes: list[int]) -> list[_T]:
    """Los valores no nulos de las horas `indexes`; las que la serie no trae se saltean."""
    picked = (values[i] for i in indexes if i < len(values))
    return [v for v in picked if v is not None]


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _mean_direction(degrees: list[float]) -> str | None:
    """Dirección media como vector (350° y 10° promedian al norte, no al sur), con letras en español."""
    if not degrees:
        return None
    sin_sum = sum(math.sin(math.radians(d)) for d in degrees)
    cos_sum = sum(math.cos(math.radians(d)) for d in degrees)
    return degrees_to_cardinal_es(math.degrees(math.atan2(sin_sum, cos_sum)) % 360)


def daily_aggregates(om: HourlyForecastExt, days: int) -> list[DayAggregate]:
    """Los primeros `days` días locales de la serie, cada uno con las horas de su fecha."""
    hours_by_date: dict[str, list[int]] = {}
    for index, date_str in enumerate(om.dates):
        hours_by_date.setdefault(date_str, []).append(index)

    aggregates: list[DayAggregate] = []
    for date_str, indexes in list(hours_by_date.items())[:days]:
        temps = _present(om.temps_c, indexes)
        winds = _present(om.wind_speeds, indexes)
        rain = _present(om.precipitations, indexes)
        probs = _present(om.precip_probs, indexes)
        capes = _present(om.cape_j_kg, indexes)
        codes = _present(om.weather_codes, indexes)
        aggregates.append(
            DayAggregate(
                date=date_str,
                temp_max_c=max(temps) if temps else None,
                temp_min_c=min(temps) if temps else None,
                humidity_mean=_mean(_present(om.humidities, indexes)),
                wind_speed_mean_kmh=_mean(winds),
                wind_speed_max_kmh=max(winds) if winds else None,
                wind_dir_cardinal=_mean_direction(_present(om.wind_dirs_deg, indexes)),
                precip_sum_mm=round(sum(rain), 2) if rain else None,
                precip_prob_max=max(probs) if probs else None,
                # El peor código del día (los códigos WMO crecen con la severidad).
                weather_code=max(codes) if codes else None,
                cape_max_j_kg=max(capes) if capes else None,
            )
        )
    return aggregates
