"""Router para visibilidad y condiciones de niebla.

GET /api/niebla?lat=...&lon=...

Estrategia de fuentes:
  - Visibilidad actual (current_m): METAR del aeropuerto más cercano (AWC, dato real).
    Si METAR no disponible → fallback a Open-Meteo (modelo numérico).
  - Pronóstico 12h (hourly): siempre Open-Meteo (METAR no da forecasts).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.rate_limit import limiter
from app.schemas.niebla import NieblaResponse, VisibilityHourlySlot
from app.services.openmeteo import get_visibility_forecast, _classify_visibility
from app.services.metar import get_nearest_metar_visibility

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
    summary="Visibilidad actual (METAR) y pronóstico 12h de niebla",
)
@limiter.limit("30/minute")
async def get_niebla(
    request: Request,
    lat: LatParam,
    lon: LonParam,
) -> NieblaResponse:
    """
    Visibilidad actual (metros) desde el METAR del aeropuerto argentino más cercano.
    Pronóstico horario 12h desde Open-Meteo.
    Clasificación: Despejada / Buena / Reducida / Bruma / Niebla / Niebla densa.
    """
    logger.info("GET /api/niebla lat=%.4f lon=%.4f", lat, lon)

    # Lanzar METAR + Open-Meteo en paralelo para minimizar latencia
    metar_result, vis = await asyncio.gather(
        get_nearest_metar_visibility(lat, lon),
        get_visibility_forecast(lat, lon),
    )

    if vis is None:
        raise HTTPException(status_code=503, detail="visibility_unavailable")

    # Visibilidad "ahora": preferir METAR (dato real); si falla → Open-Meteo
    if metar_result.visibility_m is not None:
        current_m = metar_result.visibility_m
        source = "metar"
        metar_station = metar_result.icao
        metar_station_name = metar_result.station_name
        metar_distance_km = metar_result.distance_km
        logger.info(
            "Visibilidad actual: METAR %s (%.0f km) → %.0f m",
            metar_result.icao, metar_result.distance_km, current_m,
        )
    else:
        current_m = vis.current_m
        source = "openmeteo"
        metar_station = metar_result.icao         # aún informamos el aeropuerto
        metar_station_name = metar_result.station_name
        metar_distance_km = metar_result.distance_km
        logger.info(
            "METAR %s no disponible — usando Open-Meteo para visibilidad actual",
            metar_result.icao,
        )

    level, label, color = _classify_visibility(current_m)

    hourly_slots = [
        VisibilityHourlySlot(
            hour_label=lbl,
            visibility_m=m,
            **dict(zip(["fog_level", "fog_label", "fog_color"], _classify_visibility(m))),
        )
        for lbl, m in zip(vis.hourly_labels, vis.hourly_m)
    ]

    return NieblaResponse(
        visibility_m=current_m,
        fog_level=level,
        fog_label=label,
        fog_color=color,
        weather_code=vis.weather_code,
        hourly=hourly_slots,
        source=source,
        metar_station=metar_station,
        metar_station_name=metar_station_name,
        metar_distance_km=metar_distance_km,
    )
