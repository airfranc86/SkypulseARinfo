"""Cliente async para la API pública del SMN (Servicio Meteorológico Nacional)."""
from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Final

import httpx
from cachetools import TTLCache

from app.core import usage_counter
from app.core.config import settings
from app.core.http_client import get_client
from app.utils.parsing import parse_float

logger = logging.getLogger(__name__)

# Cache global para la lista completa de estaciones.
# maxsize=1 porque guardamos un único valor: el array JSON completo.
_station_cache: TTLCache = TTLCache(maxsize=1, ttl=settings.cache_ttl_seconds)
_CACHE_KEY: Final = "stations"
# Lock para evitar TOCTOU: dos requests concurrentes con cache frío
# disparando dos fetches simultáneos a SMN.
_cache_lock = asyncio.Lock()

# Caché negativo: tras un fetch fallido (timeout, HTTP, excepción o payload vacío) no se vuelve a
# golpear al host durante esta ventana. Sin esto, con el host caído cada request esperaba el timeout
# completo (y las demás, encoladas detrás del lock, uno tras otro).
_FAILURE_BACKOFF_SECONDS: Final[float] = 60.0
# Instante monotónico hasta el que se omiten los fetch (0.0 = sin backoff activo).
_failure_backoff_until: float = 0.0

# Radio de la Tierra usado en Haversine.
_EARTH_RADIUS_KM: Final[float] = 6371.0

# Fecha asignada a una estación sin `date` utilizable: no sabemos cuándo se observó → siempre vencida.
# NUNCA usar now() en su lugar: haría que datos desconocidamente viejos pasen el check de frescura.
_UNKNOWN_OBSERVATION: Final[datetime] = datetime(2000, 1, 1, tzinfo=timezone.utc)

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
    cache_hit: bool = False  # True si la lista de estaciones salió de `_station_cache`


@dataclass(frozen=True)
class _Candidate:
    """Estación evaluada contra un punto: distancia y hora de observación (UTC)."""

    station: dict
    distance_km: float
    observed_at: datetime  # `_UNKNOWN_OBSERVATION` si la fecha no es utilizable


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
    client = get_client()
    usage_counter.record("smn")
    response = await client.get(url, headers=_HEADERS, timeout=settings.http_timeout_seconds)
    response.raise_for_status()
    return response.json()


def _monotonic() -> float:
    """Reloj monotónico. Indirección para fijarlo en tests sin parchear `time.monotonic` (lo usa asyncio)."""
    return time.monotonic()


def _in_backoff() -> bool:
    return _monotonic() < _failure_backoff_until


def _start_backoff() -> None:
    global _failure_backoff_until
    _failure_backoff_until = _monotonic() + _FAILURE_BACKOFF_SECONDS


def _clear_backoff() -> None:
    global _failure_backoff_until
    _failure_backoff_until = 0.0


async def _load_stations() -> tuple[list[dict], bool] | None:
    """
    Lista de estaciones y si salió del caché. None ante fallo del fetch o backoff activo.
    Un fallo arranca el caché negativo; un éxito lo limpia.
    """
    # La lista cacheada tiene prioridad; el backoff solo evita fetches nuevos.
    if _CACHE_KEY not in _station_cache and _in_backoff():
        return None
    try:
        # Lock evita que dos coroutines con cache frío disparen dos HTTP fetches.
        async with _cache_lock:
            if _CACHE_KEY in _station_cache:
                return _station_cache[_CACHE_KEY], True
            if _in_backoff():
                # Otra coroutine falló mientras esperábamos el lock: no repetir el fetch.
                return None
            stations = await _fetch_stations(settings.smn_weather_url)
            if not stations:
                _start_backoff()
                return None
            _station_cache[_CACHE_KEY] = stations
            _clear_backoff()
            return stations, False
    except httpx.TimeoutException:
        logger.warning("SMN request timeout")
    except httpx.HTTPStatusError as exc:
        logger.warning("SMN HTTP error: %s", exc.response.status_code)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("SMN fetch failed: %s", exc)
    _start_backoff()
    return None


def _observed_at_or_unknown(station: dict) -> datetime:
    """Hora de observación UTC de la estación; `_UNKNOWN_OBSERVATION` si 'date' falta o no se parsea."""
    try:
        return _parse_observed_at(station.get("date", ""))
    except (ValueError, TypeError, AttributeError):
        return _UNKNOWN_OBSERVATION


def _evaluate(station: dict, lat: float, lon: float) -> _Candidate | None:
    """Distancia y hora de observación de una estación; None si sus coordenadas no sirven."""
    try:
        s_lat = float(station["lat"])
        s_lon = float(station["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    return _Candidate(
        station=station,
        distance_km=haversine(lat, lon, s_lat, s_lon),
        observed_at=_observed_at_or_unknown(station),
    )


def _select_station(stations: list[dict], lat: float, lon: float, now: datetime) -> _Candidate | None:
    """
    La estación más cercana entre las frescas (fecha parseable y no más vieja que
    `smn_max_age_minutes`). Si ninguna es fresca, la más cercana en general: así el aggregator
    sigue devolviendo un motivo con sentido (`smn_stale` / `smn_too_far`).
    """
    max_age = timedelta(minutes=settings.smn_max_age_minutes)
    nearest: _Candidate | None = None
    nearest_fresh: _Candidate | None = None

    for station in stations:
        candidate = _evaluate(station, lat, lon)
        if candidate is None:
            continue
        if nearest is None or candidate.distance_km < nearest.distance_km:
            nearest = candidate
        is_fresh = (now - candidate.observed_at) <= max_age
        if is_fresh and (nearest_fresh is None or candidate.distance_km < nearest_fresh.distance_km):
            nearest_fresh = candidate

    return nearest_fresh or nearest


def _build_observation(candidate: _Candidate, from_cache: bool) -> SmnObservation:
    best = candidate.station

    # Los campos meteo están anidados bajo la clave "weather" en la API actual del SMN.
    # Ejemplo: {"name": "...", "weather": {"temp": 21.2, "humidity": 81, ...}}
    weather: dict = best.get("weather") or {}

    return SmnObservation(
        station_name=best.get("name", ""),
        station_lat=float(best["lat"]),
        station_lon=float(best["lon"]),
        distance_km=candidate.distance_km,
        observed_at=candidate.observed_at,
        temp_c=parse_float(weather.get("temp")),
        humidity=parse_float(weather.get("humidity")),
        wind_speed_kmh=parse_float(weather.get("wind_speed")),
        # SMN usa "wing_deg" (typo en la API) y devuelve texto ("Noreste"), no grados.
        wind_dir_deg=parse_float(weather.get("wind_deg") or weather.get("wing_deg")),
        pressure_hpa=parse_float(weather.get("pressure") or weather.get("pres")),
        precip_1h_mm=parse_float(weather.get("precip")),
        description=weather.get("description"),
        cache_hit=from_cache,
    )


async def get_nearest_observation(lat: float, lon: float) -> SmnObservation | None:
    """
    Retorna la observación de la estación SMN más cercana a (lat, lon), prefiriendo las frescas.
    Devuelve None ante timeout, error HTTP, payload inválido o backoff activo.
    """
    loaded = await _load_stations()
    if loaded is None:
        return None
    stations, from_cache = loaded

    chosen = _select_station(stations, lat, lon, datetime.now(timezone.utc))
    if chosen is None:
        return None

    if chosen.observed_at == _UNKNOWN_OBSERVATION:
        # El aggregator lo rechazará por stale y caerá a Open-Meteo.
        logger.warning(
            "SMN: no se pudo parsear 'date' de la estación %s (valor=%r) — se trata como dato vencido",
            chosen.station.get("name"),
            chosen.station.get("date"),
        )

    return _build_observation(chosen, from_cache)
