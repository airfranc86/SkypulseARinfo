"""Cliente async para la API pública del SMN (Servicio Meteorológico Nacional)."""
from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Final

import httpx
from cachetools import TTLCache

from app.core.config import settings
from app.utils.parsing import parse_float

logger = logging.getLogger(__name__)

# Cache global para la lista completa de estaciones.
# maxsize=1 porque guardamos un único valor: el array JSON completo.
_station_cache: TTLCache = TTLCache(maxsize=1, ttl=settings.cache_ttl_seconds)
_CACHE_KEY: Final = "stations"
# Lock para evitar TOCTOU: dos requests concurrentes con cache frío
# disparando dos fetches simultáneos a SMN.
_cache_lock = asyncio.Lock()

# Radio de la Tierra usado en Haversine.
_EARTH_RADIUS_KM: Final[float] = 6371.0

# User-Agent browser-like requerido por SMN en algunos entornos.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


@dataclass(frozen=True)
class SmnObservation:
    station_name: str
    station_lat: float
    station_lon: float
    distance_km: float
    observed_at: datetime  # siempre en UTC
    temp_c: float | None
    humidity: float | None
    wind_speed_kmh: float | None
    wind_dir_deg: float | None
    pressure_hpa: float | None
    precip_1h_mm: float | None
    description: str | None


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en km entre dos puntos usando la fórmula de Haversine."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return _EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _parse_observed_at(date_str: str) -> datetime:
    """
    Convierte el campo 'date' de SMN (formato local UTC-3) a datetime UTC.
    SMN envía: '2024-01-15 14:00' o '2024-01-15 14:00:00' (con segundos).
    Argentina = UTC-3, por lo tanto UTC = local + 3 horas.
    """
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            local_dt = datetime.strptime(date_str.strip(), fmt)
            return (local_dt + timedelta(hours=3)).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Formato de fecha SMN desconocido: {date_str!r}")


async def _fetch_stations(url: str) -> list[dict]:
    """Hace el HTTP GET a SMN y devuelve el array JSON."""
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds, headers=_HEADERS) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


async def get_nearest_observation(lat: float, lon: float) -> SmnObservation | None:
    """
    Retorna la observación de la estación SMN más cercana a (lat, lon).
    Devuelve None ante timeout, error HTTP o payload inválido.
    """
    try:
        # Lock evita que dos coroutines con cache frío disparen dos HTTP fetches.
        async with _cache_lock:
            if _CACHE_KEY in _station_cache:
                stations: list[dict] = _station_cache[_CACHE_KEY]
            else:
                stations = await _fetch_stations(settings.smn_weather_url)
                if not stations:
                    return None
                _station_cache[_CACHE_KEY] = stations

    except httpx.TimeoutException:
        logger.warning("SMN request timeout")
        return None
    except httpx.HTTPStatusError as exc:
        logger.warning("SMN HTTP error: %s", exc.response.status_code)
        return None
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("SMN fetch failed: %s", exc)
        return None

    if not stations:
        return None

    # Encontrar la estación más cercana
    best: dict | None = None
    best_dist = float("inf")

    for station in stations:
        try:
            s_lat = float(station["lat"])
            s_lon = float(station["lon"])
        except (KeyError, TypeError, ValueError):
            continue

        dist = haversine(lat, lon, s_lat, s_lon)
        if dist < best_dist:
            best_dist = dist
            best = station

    if best is None:
        return None

    try:
        observed_at = _parse_observed_at(best.get("date", ""))
    except (ValueError, TypeError):
        # Fecha no parseable → no sabemos cuándo se observó → marcar como siempre vencido.
        # El aggregator lo rechazará por stale y caerá a Windy GFS.
        # NUNCA usar now() aquí: haría que datos desconocidamente viejos pasen el check.
        logger.warning(
            "SMN: no se pudo parsear 'date' de la estación %s (valor=%r) — se trata como dato vencido",
            best.get("name"),
            best.get("date"),
        )
        observed_at = datetime(2000, 1, 1, tzinfo=timezone.utc)

    # Los campos meteo están anidados bajo la clave "weather" en la API actual del SMN.
    # Ejemplo: {"name": "...", "weather": {"temp": 21.2, "humidity": 81, ...}}
    weather: dict = best.get("weather") or {}

    return SmnObservation(
        station_name=best.get("name", ""),
        station_lat=float(best["lat"]),
        station_lon=float(best["lon"]),
        distance_km=best_dist,
        observed_at=observed_at,
        temp_c=parse_float(weather.get("temp")),
        humidity=parse_float(weather.get("humidity")),
        wind_speed_kmh=parse_float(weather.get("wind_speed")),
        # SMN usa "wing_deg" (typo en la API) y devuelve texto ("Noreste"), no grados.
        wind_dir_deg=parse_float(weather.get("wind_deg") or weather.get("wing_deg")),
        pressure_hpa=parse_float(weather.get("pressure") or weather.get("pres")),
        precip_1h_mm=parse_float(weather.get("precip")),
        description=weather.get("description"),
    )
