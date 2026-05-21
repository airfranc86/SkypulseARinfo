"""Router para el monitor de sismos — datos USGS FDSN."""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.core.rate_limit import limiter
from app.schemas.earthquakes import EarthquakesResponse
from app.services.usgs import get_recent_earthquakes

logger = logging.getLogger(__name__)

router = APIRouter()

_LAT = Annotated[float, Query(ge=-55, le=-21, description="Latitud (Argentina: -55 a -21)")]
_LON = Annotated[float, Query(ge=-74, le=-53, description="Longitud (Argentina: -74 a -53)")]


@router.get(
    "/recent",
    response_model=EarthquakesResponse,
    summary="Sismos recientes en Argentina",
    description=(
        "Retorna sismos ≥ 2.5 registrados por USGS en el territorio argentino, "
        "filtrados por radio desde la ubicación del usuario y ordenados por proximidad."
    ),
)
@limiter.limit("30/minute")
async def get_recent(
    request: Request,
    lat: _LAT,
    lon: _LON,
    radius_km: Annotated[
        float,
        Query(ge=50, le=2000, description="Radio de búsqueda en km (50–2000)"),
    ] = 500.0,
) -> EarthquakesResponse:
    logger.info("GET /earthquakes/recent lat=%.2f lon=%.2f radius=%.0f", lat, lon, radius_km)
    return await get_recent_earthquakes(lat, lon, radius_km)
