"""Servicio de riesgo de incendio forestal.

El puntaje se estima con `compute_fire_risk` a partir del pronóstico horario de Open-Meteo
(temperatura, humedad, viento y lluvia), la misma serie que usan el dashboard y las herramientas.
Open-Meteo no trae el FWI (Fire Weather Index): el modelo `fireDanger` de Windy tampoco estaba
disponible en el plan Testing que usaba producción, así que el puntaje ya era una estimación. Y los
datos de esa key llegan mezclados al azar ("returns randomly shuffled and slightly modified data",
https://api.windy.com/point-forecast/pricing), por eso Windy dejó de ser la fuente.

Exports principales:
    - get_fire_danger: lista de FireDangerEntry, una por hora, con el riesgo estimado.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from app.services.hourly_slots import at, window
from app.services.openmeteo import HourlyForecastExt, get_hourly_forecast_ext

logger = logging.getLogger(__name__)

# Serie de 7 días: la misma que pide el dashboard, así comparten caché.
_FORECAST_DAYS = 7

# ---------------------------------------------------------------------------
# Tipos de datos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FireDangerEntry:
    """Una hora de riesgo de incendio, siempre estimado (Open-Meteo no trae FWI)."""
    date: str
    hour_label: str
    fire_risk_score: float      # 0–100
    fire_risk_label: str        # "Muy bajo" / "Bajo" / "Moderado" / "Alto" / "Muy alto" / "Extremo"
    temp_c: float | None
    humidity: float | None
    wind_kmh: float | None
    precip_mm: float | None     # lluvia de las 3 h que terminan en esta hora
    timestamp_s: int            # epoch: la serie arranca a las 00:00 de hoy, no en "ahora"


# ---------------------------------------------------------------------------
# Lógica de cálculo de score
# ---------------------------------------------------------------------------

def compute_fire_risk(
    temp_c: float | None,
    humidity: float | None,
    wind_kmh: float | None,
    precip_mm: float | None,
) -> tuple[float, str]:
    """
    Score 0–100 basado en la lógica de NOAA Fire Weather Watch:
    - temp alta = más riesgo
    - humedad baja = más riesgo
    - viento alto = más riesgo
    - precipitación reciente = menos riesgo
    """
    score = 0.0
    if temp_c is not None:
        score += min((temp_c - 10) / 30 * 30, 30)   # max 30 pts
    if humidity is not None:
        score += max((60 - humidity) / 60 * 30, 0)   # max 30 pts
    if wind_kmh is not None:
        score += min(wind_kmh / 50 * 25, 25)          # max 25 pts
    if precip_mm is not None and precip_mm > 2:
        score = max(score - 20, 0)                    # lluvia reciente reduce riesgo
    score = max(0.0, min(100.0, score))

    if score < 20:
        label = "Muy bajo"
    elif score < 40:
        label = "Bajo"
    elif score < 60:
        label = "Moderado"
    elif score < 75:
        label = "Alto"
    elif score < 90:
        label = "Muy alto"
    else:
        label = "Extremo"

    return round(score, 1), label


# ---------------------------------------------------------------------------
# Serie horaria → entradas
# ---------------------------------------------------------------------------

def fire_entries_from_hourly(om: HourlyForecastExt) -> list[FireDangerEntry]:
    """Una entrada por hora de la serie. La lluvia es la de las 3 h que terminan en esa hora (lo que
    medía el `past3hprecip` de Windy, pero disponible en cada hora): más de 2 mm reducen el riesgo."""
    entries: list[FireDangerEntry] = []
    for i, hour_label in enumerate(om.hour_labels):
        temp_c = at(om.temps_c, i)
        humidity = at(om.humidities, i)
        wind_kmh = at(om.wind_speeds, i)
        rain = window(om.precipitations, i)
        precip_mm = round(sum(rain), 2) if rain else None

        score, label = compute_fire_risk(temp_c, humidity, wind_kmh, precip_mm)
        entries.append(
            FireDangerEntry(
                date=om.dates[i],
                hour_label=hour_label,
                fire_risk_score=score,
                fire_risk_label=label,
                temp_c=temp_c,
                humidity=humidity,
                wind_kmh=wind_kmh,
                precip_mm=precip_mm,
                timestamp_s=om.timestamps[i],
            )
        )
    return entries


def closest_to_now(entries: list[FireDangerEntry]) -> FireDangerEntry:
    """
    Entry cuyo timestamp está más cerca del momento actual.

    La serie no está garantizada a empezar en "ahora": la de Open-Meteo arranca a las 00:00 de hoy
    (y la de Windy, en el inicio del ciclo del modelo, que podía quedar varias horas atrás). Tomar
    `entries[0]` a ciegas como "condiciones actuales" mostraba la temperatura de la madrugada al
    mediodía.
    """
    now_s = datetime.now(timezone.utc).timestamp()
    return min(entries, key=lambda e: abs(e.timestamp_s - now_s))


# ---------------------------------------------------------------------------
# Función pública
# ---------------------------------------------------------------------------

async def get_fire_danger(lat: float, lon: float) -> list[FireDangerEntry]:
    """
    Pronóstico horario de riesgo de incendio a 7 días, estimado con la serie de Open-Meteo.
    Lista vacía si Open-Meteo no respondió (el router lo informa como 503).
    """
    om = await get_hourly_forecast_ext(lat, lon, days=_FORECAST_DAYS)
    if om is None:
        logger.warning("fire_danger: sin serie horaria de Open-Meteo para (%.4f, %.4f)", lat, lon)
        return []
    return fire_entries_from_hourly(om)
