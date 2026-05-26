"""Router para riesgo de incendio forestal por ubicación.

GET /api/incendios?lat=...&lon=...

Fuente primaria: Windy fireDanger model (FWI).
Fallback: estimación a partir de GFS (temperatura, humedad, viento, precipitación).
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.rate_limit import limiter
from app.schemas.incendios import FireDangerResponse, FireDangerSlot, RISK_COLOR_MAP
from app.services.fire_danger import get_fire_danger, FireDangerEntry
from app.services.windy import WindyNotConfiguredError

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Parámetros de coordenadas (bbox Argentina)
# ---------------------------------------------------------------------------

LatParam = Annotated[
    float,
    Query(ge=-55, le=-21, description="Latitud (Argentina: -55 a -21)"),
]
LonParam = Annotated[
    float,
    Query(ge=-74, le=-53, description="Longitud (Argentina: -74 a -53)"),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SOURCE_FIREDANGER = "windy_firedanger"
_SOURCE_ESTIMATED  = "windy_gfs_estimated"


def _build_response(entries: list[FireDangerEntry]) -> FireDangerResponse:
    """Construye FireDangerResponse a partir de la lista de entries."""
    if not entries:
        raise HTTPException(status_code=503, detail="fire_danger_unavailable")

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
        for e in entries
    ]

    current = slots[0]
    peak = max(slots, key=lambda s: s.fire_risk_score)

    is_estimated = entries[0].is_estimated
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
    logger.info("GET /api/incendios lat=%.4f lon=%.4f", lat, lon)

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
