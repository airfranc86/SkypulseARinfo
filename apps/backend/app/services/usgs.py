"""Cliente async para la API FDSN de USGS — sismos en Argentina."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Final

from cachetools import TTLCache
from httpx import HTTPStatusError, TimeoutException as HttpxTimeout

from app.core.config import settings
from app.core.http_client import get_client
from app.schemas.earthquakes import EarthquakeEvent, EarthquakesResponse
from app.services.smn import haversine

logger = logging.getLogger(__name__)

_CACHE_KEY: Final = "usgs_ar_recent"
_event_cache: TTLCache = TTLCache(maxsize=1, ttl=settings.cache_ttl_earthquakes_seconds)
_cache_lock = asyncio.Lock()

_AR_BBOX = {
    "minlatitude": -55,
    "maxlatitude": -21,
    "minlongitude": -76,   # era -74; ampliado para incluir franja costera chilena percibida en AR
    "maxlongitude": -53,
}


async def _fetch_usgs() -> list[dict]:
    """HTTP GET a USGS FDSN. Retorna lista de features GeoJSON."""
    # starttime explícito: últimas 24h — garantiza que eventos recientes
    # siempre estén incluidos sin depender del default de USGS.
    starttime = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")
    params = {
        **_AR_BBOX,
        "format": "geojson",
        "minmagnitude": 2.5,
        "orderby": "time",
        "limit": 100,
        "starttime": starttime,
    }
    client = get_client()
    resp = await client.get(
        settings.usgs_base_url,
        params=params,
        timeout=settings.http_timeout_seconds,
    )
    resp.raise_for_status()
    return resp.json().get("features", [])


def _parse_event(feature: dict, user_lat: float, user_lon: float) -> EarthquakeEvent | None:
    """Convierte un feature GeoJSON de USGS a EarthquakeEvent. None si el payload es inválido."""
    try:
        props = feature["properties"]
        coords = feature["geometry"]["coordinates"]  # [lon, lat, depth_km]
        ev_lon = float(coords[0])
        ev_lat = float(coords[1])
        depth_km = float(coords[2])
        magnitude = float(props["mag"])
        time_ms = int(props["time"])
        occurred_at = datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc)
        distance_km = haversine(user_lat, user_lon, ev_lat, ev_lon)
        return EarthquakeEvent(
            id=feature["id"],
            place=props.get("place", ""),
            magnitude=round(magnitude, 1),
            depth_km=round(abs(depth_km), 1),
            occurred_at=occurred_at,
            lat=round(ev_lat, 4),
            lon=round(ev_lon, 4),
            distance_km=round(distance_km, 1),
            usgs_url=props.get("url", ""),
        )
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        logger.warning("USGS: error parseando feature %s: %s", feature.get("id"), exc)
        return None


async def get_recent_earthquakes(
    user_lat: float,
    user_lon: float,
    radius_km: float = 500.0,
) -> EarthquakesResponse:
    """
    Sismos recientes (≥ 2.5, bbox AR) dentro de radius_km del usuario.
    Usa TTLCache para no repetir el fetch a USGS en cada request.
    Ante error HTTP: retorna lista vacía (degradación controlada, no 503).
    """
    features: list[dict] = []
    try:
        async with _cache_lock:
            if _CACHE_KEY in _event_cache:
                features = _event_cache[_CACHE_KEY]
            else:
                features = await _fetch_usgs()
                _event_cache[_CACHE_KEY] = features
    except HttpxTimeout:
        logger.warning("USGS request timeout")
    except HTTPStatusError as exc:
        logger.warning("USGS HTTP error: %s", exc.response.status_code)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("USGS fetch failed: %s", exc)

    events: list[EarthquakeEvent] = []
    for f in features:
        ev = _parse_event(f, user_lat, user_lon)
        if ev is None:
            continue
        if ev.distance_km > radius_km:
            continue
        # USGS siempre incluye el país en el campo place ("10 km NW of San Juan, Argentina").
        # Filtramos para mostrar solo eventos en Argentina y excluir la actividad chilena
        # que dominaría la lista por la alta sismicidad del Pacífico.
        place_lower = ev.place.lower()
        if "argentina" not in place_lower:
            continue
        events.append(ev)

    # Ordenar por fecha descendente (más reciente primero) — un monitor de
    # sismos debe mostrar lo último, no el más cercano.
    events.sort(key=lambda e: e.occurred_at, reverse=True)

    return EarthquakesResponse(total=len(events), radius_km=radius_km, events=events)
