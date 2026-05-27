"""Agregador de fuentes sísmicas: EMSC (primario) + USGS (fallback).

Estrategia:
- EMSC se consulta primero: incluye red NSNA/INPRES, datos con menor latencia para Argentina.
- Si EMSC devuelve 0 eventos (posible vacío legítimo o problema temporal), se consulta USGS.
- Ambas fuentes tienen TTLCache de 5 min — el fallback no genera overhead en requests sucesivos.
"""
from __future__ import annotations

import logging

from app.schemas.earthquakes import EarthquakesResponse
from app.services import emsc as emsc_service
from app.services import usgs as usgs_service

logger = logging.getLogger(__name__)


async def get_recent_earthquakes(
    user_lat: float,
    user_lon: float,
    radius_km: float = 500.0,
) -> EarthquakesResponse:
    """
    Sismos recientes en Argentina. EMSC primario, USGS como fallback.
    Nunca lanza excepción: ante fallo de ambas fuentes retorna lista vacía.
    """
    result = await emsc_service.get_recent_earthquakes(user_lat, user_lon, radius_km)
    if result.total > 0:
        return result

    logger.info(
        "EMSC: 0 eventos para lat=%.2f lon=%.2f radius=%.0f — consultando USGS",
        user_lat,
        user_lon,
        radius_km,
    )
    return await usgs_service.get_recent_earthquakes(user_lat, user_lon, radius_km)
