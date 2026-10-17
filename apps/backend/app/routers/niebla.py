"""Router para visibilidad y condiciones de niebla.

GET /api/niebla?lat=...&lon=...

Estrategia de fuentes:
  Visibilidad actual (ahora):
    1. METAR del aeropuerto más cercano (AWC, dato real) si está a <= 20 km y tiene <= 90 min
    2. Open-Meteo (fallback si el METAR falla, está lejos o es viejo)

  Pronóstico horario 12h:
    1. TAF del aeropuerto más cercano (AWC, emitido por meteorólogos)
    2. Inferencia de niebla desde NWP (OM humedad/rocío/viento)
    3. Open-Meteo campo visibility (último recurso)

Este router solo junta las fuentes por la red y devuelve lo que arma `services/niebla.py` (el armado es puro y lo comparte
el asistente de Mora).
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request

from app.core.params import LatParam, LonParam
from app.core.rate_limit import limiter
from app.schemas.niebla import NieblaResponse
from app.services import niebla as niebla_servicio
from app.services.openmeteo import (
    get_visibility_forecast,
    get_fog_inference_forecast,
)
from app.services.reportes_aeronauticos import get_nearest_metar_visibility, get_nearest_taf_hourly

logger = logging.getLogger(__name__)

router = APIRouter()


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
    Clasificación oficial METAR/SMN: Despejada (>= 10 km) / Buena (5–10 km) /
    Neblina o bruma (1–5 km) / Niebla (< 1 km).
    """
    logger.info("GET /api/niebla lat=%.4f lon=%.4f", lat, lon)

    # Lanzar todas las fuentes en paralelo
    metar_result, vis, taf_slots, fog_slots = await asyncio.gather(
        get_nearest_metar_visibility(lat, lon),
        get_visibility_forecast(lat, lon),
        get_nearest_taf_hourly(lat, lon, hours=12),
        get_fog_inference_forecast(lat, lon, hours=12),
    )

    respuesta = niebla_servicio.armar_niebla(metar_result, vis, taf_slots, fog_slots)
    # Necesitamos al menos alguna fuente de visibilidad actual
    if respuesta is None:
        raise HTTPException(status_code=503, detail="visibility_unavailable")
    return respuesta
