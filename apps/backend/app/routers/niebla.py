"""Router para visibilidad y condiciones de niebla.

GET /api/niebla?lat=...&lon=...

Estrategia de fuentes:
  Visibilidad actual (ahora):
    1. METAR del aeropuerto más cercano (AWC, dato real)
    2. Open-Meteo (fallback si METAR falla)

  Pronóstico horario 12h:
    1. TAF del aeropuerto más cercano (AWC, emitido por meteorólogos)
    2. Inferencia de niebla desde NWP (OM humedad/rocío/viento)
    3. Open-Meteo campo visibility (último recurso)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.rate_limit import limiter
from app.schemas.niebla import NieblaResponse, VisibilityHourlySlot
from app.services.openmeteo import (
    get_visibility_forecast,
    get_fog_inference_forecast,
    _classify_visibility,
)
from app.services.metar import get_nearest_metar_visibility, get_nearest_taf_hourly

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
    Pronóstico horario 12h: TAF → inferencia OM → Open-Meteo campo visibility.
    Clasificación: Despejada / Buena / Reducida / Bruma / Neblina / Niebla.
    """
    logger.info("GET /api/niebla lat=%.4f lon=%.4f", lat, lon)

    # Lanzar todas las fuentes en paralelo
    metar_result, vis, taf_slots, fog_slots = await asyncio.gather(
        get_nearest_metar_visibility(lat, lon),
        get_visibility_forecast(lat, lon),
        get_nearest_taf_hourly(lat, lon, hours=12),
        get_fog_inference_forecast(lat, lon, hours=12),
    )

    # Necesitamos al menos alguna fuente de visibilidad actual
    if metar_result.visibility_m is None and vis is None:
        raise HTTPException(status_code=503, detail="visibility_unavailable")

    # ── Visibilidad "ahora" ────────────────────────────────────────────────
    if metar_result.visibility_m is not None:
        current_m       = metar_result.visibility_m
        source          = "metar"
        metar_station   = metar_result.icao
        metar_name      = metar_result.station_name
        metar_dist      = metar_result.distance_km
        logger.info(
            "Visibilidad actual: METAR %s (%.0f km) → %.0f m",
            metar_result.icao, metar_result.distance_km, current_m,
        )
    else:
        current_m       = vis.current_m if vis else None   # type: ignore[union-attr]
        source          = "openmeteo"
        metar_station   = metar_result.icao
        metar_name      = metar_result.station_name
        metar_dist      = metar_result.distance_km
        logger.info("METAR %s no disponible — usando Open-Meteo para visibilidad actual", metar_result.icao)

    level, label, color = _classify_visibility(current_m)

    # ── Pronóstico horario 12h ─────────────────────────────────────────────
    hourly_slots: list[VisibilityHourlySlot]
    hourly_source: str

    if taf_slots:
        # Fuente primaria: TAF (meteorólogos de aviación — cubre niebla real)
        hourly_source = "taf"
        hourly_slots = [
            VisibilityHourlySlot(
                hour_label=slot.hour_label,
                visibility_m=slot.visibility_m,
                **dict(zip(
                    ["fog_level", "fog_label", "fog_color"],
                    _classify_visibility(slot.visibility_m),
                )),
            )
            for slot in taf_slots
        ]
        logger.info("Hourly source: TAF (%d slots)", len(hourly_slots))

    elif fog_slots:
        # Fallback: inferencia de niebla desde NWP (humedad/rocío/viento)
        hourly_source = "openmeteo_inference"
        hourly_slots = [
            VisibilityHourlySlot(
                hour_label=slot.hour_label,
                visibility_m=slot.visibility_m,
                **dict(zip(
                    ["fog_level", "fog_label", "fog_color"],
                    _classify_visibility(slot.visibility_m),
                )),
            )
            for slot in fog_slots
        ]
        logger.info("Hourly source: OM fog inference (%d slots)", len(hourly_slots))

    elif vis:
        # Último recurso: campo visibility directo de Open-Meteo
        hourly_source = "openmeteo"
        hourly_slots = [
            VisibilityHourlySlot(
                hour_label=lbl,
                visibility_m=m,
                **dict(zip(
                    ["fog_level", "fog_label", "fog_color"],
                    _classify_visibility(m),
                )),
            )
            for lbl, m in zip(vis.hourly_labels, vis.hourly_m)
        ]
        logger.info("Hourly source: Open-Meteo visibility (%d slots)", len(hourly_slots))

    else:
        hourly_source = "none"
        hourly_slots  = []
        logger.warning("No hourly visibility source available for lat=%.4f lon=%.4f", lat, lon)

    return NieblaResponse(
        visibility_m=current_m,
        fog_level=level,
        fog_label=label,
        fog_color=color,
        weather_code=vis.weather_code if vis else None,
        hourly=hourly_slots,
        source=source,
        metar_station=metar_station,
        metar_station_name=metar_name,
        metar_distance_km=metar_dist,
        hourly_source=hourly_source,
    )
