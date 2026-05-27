"""Cliente METAR via Aviation Weather Center (aviationweather.gov).

GET https://aviationweather.gov/api/data/metar?ids=SAEZ&format=json&hours=2

Retorna visibilidad real medida en estaciones aeronáuticas argentinas.
Sin API key requerida. TTLCache 30 min (METAR se actualiza cada ~30-60 min).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone

from cachetools import TTLCache

from app.core.http_client import get_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Aeropuertos argentinos con coordenadas — usados para lookup del más cercano
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Airport:
    icao: str
    name: str
    lat: float
    lon: float


_AR_AIRPORTS: list[_Airport] = [
    _Airport("SAEZ", "Ezeiza",            -34.822, -58.536),
    _Airport("SABE", "Aeroparque",        -34.559, -58.416),
    _Airport("SACO", "Córdoba",           -31.323, -64.208),
    _Airport("SAME", "Mendoza",           -32.832, -68.793),
    _Airport("SARS", "Rosario",           -32.919, -60.785),
    _Airport("SANT", "Tucumán",           -26.841, -65.105),
    _Airport("SASA", "Salta",             -24.856, -65.486),
    _Airport("SASJ", "San Juan",          -31.572, -68.418),
    _Airport("SAVB", "Bariloche",         -41.151, -71.157),
    _Airport("SAWC", "Comodoro Rivadavia",-45.785, -67.499),
    _Airport("SAWG", "Río Gallegos",      -51.609, -69.313),
    _Airport("SAWO", "Neuquén",           -38.949, -68.156),
    _Airport("SAWH", "Ushuaia",           -54.843, -68.295),
    _Airport("SAAC", "Concordia",         -31.297, -57.997),
    _Airport("SAAG", "Gualeguaychú",      -33.011, -58.611),
    _Airport("SAZR", "Santa Rosa",        -36.588, -64.276),
    _Airport("SAZS", "Bariloche (alt)",   -41.151, -71.157),
    _Airport("SAVT", "Viedma",            -40.869, -63.000),
    _Airport("SAWP", "Malargüe",          -35.493, -69.574),
    _Airport("SAMR", "San Rafael",        -34.588, -68.404),
]

# ---------------------------------------------------------------------------
# Cache: key = icao, value = visibility_m | None
# TTL 30 min — METAR se actualiza cada 30-60 min
# ---------------------------------------------------------------------------

_metar_cache: TTLCache[str, float | None] = TTLCache(maxsize=64, ttl=1800)

AWC_BASE = "https://aviationweather.gov/api/data/metar"
_SM_TO_M = 1609.344   # statute miles → metros


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en km entre dos coordenadas usando la fórmula de Haversine."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def nearest_airport(lat: float, lon: float) -> _Airport:
    """Retorna el aeropuerto de la lista interna más cercano a (lat, lon)."""
    return min(_AR_AIRPORTS, key=lambda a: _haversine_km(lat, lon, a.lat, a.lon))


async def get_metar_visibility(icao: str) -> float | None:
    """
    Consulta la visibilidad actual (metros) desde el METAR de un aeropuerto ICAO.

    - Fuente: Aviation Weather Center (aviationweather.gov), sin API key.
    - Retorna None si el fetch falla, el ICAO no existe o no hay campo `visib`.
    - Los valores ≥ 10 km se normalizan a 10 000 m (mismo cap que el resto del sistema).
    """
    if icao in _metar_cache:
        logger.debug("METAR cache hit: %s → %s m", icao, _metar_cache[icao])
        return _metar_cache[icao]

    try:
        client = get_client()
        response = await client.get(
            AWC_BASE,
            params={"ids": icao, "format": "json", "hours": "2"},
            timeout=8.0,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning("METAR fetch failed for %s: %s", icao, exc)
        _metar_cache[icao] = None
        return None

    # AWC returns a list; take the most recent entry
    if not isinstance(data, list) or len(data) == 0:
        logger.info("METAR: no data for %s", icao)
        _metar_cache[icao] = None
        return None

    entry = data[0]
    visib_sm = entry.get("visib")
    if visib_sm is None:
        logger.info("METAR: no visib field for %s", icao)
        _metar_cache[icao] = None
        return None

    try:
        vis_m = float(visib_sm) * _SM_TO_M
    except (TypeError, ValueError):
        _metar_cache[icao] = None
        return None

    # Cap at 10 km — consistent with the rest of the system
    vis_m = min(vis_m, 10_000.0)
    logger.info("METAR %s: %.0f SM → %.0f m (obs: %s)", icao, float(visib_sm), vis_m, entry.get("obsTime", "?"))

    _metar_cache[icao] = vis_m
    return vis_m


@dataclass(frozen=True)
class MetarVisibility:
    """Resultado de una consulta METAR de visibilidad."""
    visibility_m: float | None
    icao: str
    station_name: str
    distance_km: float
    observed_at: datetime | None


async def get_nearest_metar_visibility(lat: float, lon: float) -> MetarVisibility:
    """
    Encuentra el aeropuerto más cercano y retorna su visibilidad METAR.
    Siempre retorna un objeto (visibility_m puede ser None si el fetch falla).
    """
    airport = nearest_airport(lat, lon)
    dist_km = _haversine_km(lat, lon, airport.lat, airport.lon)
    vis_m = await get_metar_visibility(airport.icao)

    return MetarVisibility(
        visibility_m=vis_m,
        icao=airport.icao,
        station_name=airport.name,
        distance_km=round(dist_km, 1),
        observed_at=datetime.now(timezone.utc) if vis_m is not None else None,
    )
