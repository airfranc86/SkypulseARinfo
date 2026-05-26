"""Router para visibilidad y condiciones de niebla.

GET /api/niebla?lat=...&lon=...
Fuente: Open-Meteo (current + hourly visibility).
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.rate_limit import limiter
from app.schemas.niebla import NieblaResponse, VisibilityHourlySlot
from app.services.openmeteo import get_visibility_forecast, _classify_visibility

logger = logging.getLogger(__name__)

router = APIRouter()

LatParam = Annotated[
    float,
    Query(ge=-55, le=-21, description="Latitud (Argentina: -55 a -21)"),
]
LonParam = Annotated[
    float,
    Query(ge=-76, le=-53, description="Longitud (Argentina: -76 a -53)"),
]


@router.get(
    "",
    response_model=NieblaResponse,
    summary="Visibilidad actual y pronóstico 12h de niebla",
)
@limiter.limit("30/minute")
async def get_niebla(
    request: Request,
    lat: LatParam,
    lon: LonParam,
) -> NieblaResponse:
    """
    Visibilidad actual (metros) + pronóstico horario 12h.
    Clasificación: Despejada / Buena / Reducida / Bruma / Niebla / Niebla densa.
    """
    logger.info("GET /api/niebla lat=%.4f lon=%.4f", lat, lon)

    vis = await get_visibility_forecast(lat, lon)
    if vis is None:
        raise HTTPException(status_code=503, detail="visibility_unavailable")

    hourly_slots = [
        VisibilityHourlySlot(
            hour_label=label,
            visibility_m=m,
            **dict(zip(["fog_level", "fog_label", "fog_color"], _classify_visibility(m))),
        )
        for label, m in zip(vis.hourly_labels, vis.hourly_m)
    ]

    return NieblaResponse(
        visibility_m=vis.current_m,
        fog_level=vis.fog_level,
        fog_label=vis.fog_label,
        fog_color=vis.fog_color,
        weather_code=vis.weather_code,
        hourly=hourly_slots,
    )
