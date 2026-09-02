"""Router para riesgo de incendio forestal por ubicación.

GET /api/incendios?lat=...&lon=...

Fuente primaria: Windy fireDanger model (FWI).
Fallback: estimación a partir de GFS (temperatura, humedad, viento, precipitación).
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request

from app.core.params import LatParam, LonParam
from app.core.rate_limit import limiter
from app.schemas.incendios import FireDangerResponse, FireDangerSlot, RISK_COLOR_MAP
from app.schemas.weather import WeatherCurrentResponse
from app.services.fire_danger import get_fire_danger, closest_to_now, compute_fire_risk, FireDangerEntry
from app.services.weather_aggregator import aggregate_current
from app.services.windy import WindyNotConfiguredError

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SOURCE_FIREDANGER = "windy_firedanger"
_SOURCE_ESTIMATED  = "windy_gfs_estimated"


def _build_response(
    entries: list[FireDangerEntry],
    current_weather: WeatherCurrentResponse | None,
) -> FireDangerResponse:
    """Construye FireDangerResponse a partir de la lista de entries."""
    if not entries:
        raise HTTPException(status_code=503, detail="fire_danger_unavailable")

    # El array de Windy no está garantizado a empezar en "ahora" — recortamos
    # desde el slot más cercano al momento actual en vez de asumir índice 0.
    # El frontend toma slots[0] como condiciones actuales, y el timeline debe
    # mostrar lo que viene, no horas que ya pasaron.
    closest = closest_to_now(entries)
    entries_from_now = entries[entries.index(closest):]

    slots = [
        FireDangerSlot(
            date=e.date,
            hour_label=e.hour_label,
            fwi=e.fwi,
            fire_risk_score=e.fire_risk_score,
            fire_risk_label=e.fire_risk_label,
            temp_c=e.temp_c,
            humidity=e.humidity,
            wind_kmh=e.wind_kmh,
            precip_mm=e.precip_mm,
            is_estimated=e.is_estimated,
        )
        for e in entries_from_now
    ]

    # El slot "actual" sale del pronóstico de Windy (GFS gratis o fireDanger),
    # que puede divergir bastante de la temperatura real (reportado en vivo:
    # 10°C mostrados con 26°C reales) — reemplazamos temp/humedad/viento del
    # slot actual por la observación real (SMN/Open-Meteo, la misma fuente
    # que usa el resto de la app para "ahora") cuando está disponible. Si el
    # score además es estimado (sin FWI real), lo recalculamos con estos
    # valores más precisos — mostrar una temperatura real junto a un score
    # calculado con datos de pronóstico distintos sería más confuso, no menos.
    # Si aggregate_current falla, seguimos con los valores de Windy sin más
    # (fail-open, mismo criterio que el resto del proyecto).
    first = slots[0]
    if current_weather is not None and current_weather.temp_c is not None:
        if first.is_estimated:
            new_score, new_label = compute_fire_risk(
                current_weather.temp_c,
                current_weather.humidity,
                current_weather.wind_speed_kmh,
                current_weather.precip_1h_mm,
            )
        else:
            new_score, new_label = first.fire_risk_score, first.fire_risk_label

        slots = [
            first.model_copy(update={
                "temp_c": current_weather.temp_c,
                "humidity": current_weather.humidity,
                "wind_kmh": current_weather.wind_speed_kmh,
                "precip_mm": current_weather.precip_1h_mm,
                "fire_risk_score": new_score,
                "fire_risk_label": new_label,
            }),
            *slots[1:],
        ]

    current = slots[0]
    peak = max(slots, key=lambda s: s.fire_risk_score)

    is_estimated = current.is_estimated
    source = _SOURCE_ESTIMATED if is_estimated else _SOURCE_FIREDANGER

    return FireDangerResponse(
        slots=slots,
        current_score=current.fire_risk_score,
        current_label=current.fire_risk_label,
        current_color=RISK_COLOR_MAP.get(current.fire_risk_label, "#f0a030"),
        peak_score=peak.fire_risk_score,
        peak_label=peak.fire_risk_label,
        peak_hour_label=f"{peak.date} {peak.hour_label}",
        source=source,
        is_estimated=is_estimated,
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=FireDangerResponse,
    summary="Riesgo de incendio forestal por ubicación",
)
@limiter.limit("30/minute")
async def get_incendios(
    request: Request,
    lat: LatParam,
    lon: LonParam,
) -> FireDangerResponse:
    """
    Pronóstico de riesgo de incendio forestal.

    Datos:
        - Primario: Windy fireDanger model (FWI / DSR / DC / DMC / FFMC).
        - Fallback: estimación desde parámetros GFS (temp, humedad, viento, precip).
    """
    logger.info("GET /api/incendios lat=%.2f lon=%.2f", lat, lon)

    # aggregate_current (SMN/Open-Meteo) en paralelo al fetch de Windy — solo
    # se usa para reemplazar temp/humedad/viento del slot "actual" por la
    # observación real; si falla, no debe tumbar el endpoint (Windy solo ya
    # alcanza para responder, aunque con una temperatura menos precisa).
    fire_result, current_result = await asyncio.gather(
        get_fire_danger(lat, lon),
        aggregate_current(lat, lon),
        return_exceptions=True,
    )

    if isinstance(fire_result, WindyNotConfiguredError):
        raise HTTPException(status_code=503, detail="windy_not_configured")
    if isinstance(fire_result, BaseException):
        logger.error("get_fire_danger failed: %s", fire_result)
        raise HTTPException(status_code=503, detail="fire_danger_unavailable")

    current_weather: WeatherCurrentResponse | None
    if isinstance(current_result, BaseException):
        logger.warning(
            "aggregate_current failed in /incendios — usando condiciones actuales de Windy: %s",
            current_result,
        )
        current_weather = None
    else:
        current_weather = current_result

    return _build_response(fire_result, current_weather)
