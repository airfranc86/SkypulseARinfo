"""Router para riesgo de incendio forestal por ubicación.

GET /api/incendios?lat=...&lon=...

Fuente primaria: Windy fireDanger model (FWI).
Fallback: estimación a partir de GFS (temperatura, humedad, viento, precipitación).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from app.core.params import LatParam, LonParam
from app.core.rate_limit import limiter
from app.schemas.incendios import FireDangerResponse, FireDangerSlot, RISK_COLOR_MAP
from app.services.fire_danger import get_fire_danger, closest_to_now, FireDangerEntry
from app.services.windy import WindyNotConfiguredError

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SOURCE_FIREDANGER = "windy_firedanger"
_SOURCE_ESTIMATED  = "windy_gfs_estimated"


def _build_response(entries: list[FireDangerEntry]) -> FireDangerResponse:
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

    try:
        entries = await get_fire_danger(lat, lon)
    except WindyNotConfiguredError:
        raise HTTPException(
            status_code=503,
            detail="windy_not_configured",
        )
    except Exception as exc:
        logger.error("get_fire_danger failed: %s", exc)
        raise HTTPException(status_code=503, detail="fire_danger_unavailable")

    return _build_response(entries)
