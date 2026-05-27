"""Cliente async para la API FDSN de EMSC (seismicportal.eu) — sismos en Argentina.

EMSC incluye datos de la red NSNA (Red Sismológica Nacional Argentina / INPRES),
lo que permite obtener eventos con menor latencia que USGS para el territorio argentino.
El formato text (pipe-delimited) se usa porque el formato geojson retorna HTTP 400.
"""
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

_CACHE_KEY: Final = "emsc_ar_recent"
_event_cache: TTLCache = TTLCache(maxsize=1, ttl=settings.cache_ttl_earthquakes_seconds)
_cache_lock = asyncio.Lock()

_EMSC_URL: Final = "https://www.seismicportal.eu/fdsnws/event/1/query"

_AR_BBOX = {
    "minlatitude": -55,
    "maxlatitude": -21,
    "minlongitude": -76,
    "maxlongitude": -53,
}


async def _fetch_emsc() -> list[list[str]]:
    """HTTP GET a EMSC FDSN en formato text. Retorna lista de filas parseadas.

    Formato de columnas (0-indexed):
    0=EventID, 1=Time, 2=Latitude, 3=Longitude, 4=Depth/km,
    5=Author, 6=Catalog, 7=Contributor, 8=ContribID,
    9=MagType, 10=Magnitude, 11=MagAuthor, 12=EventLocationName
    """
    starttime = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
    params = {
        **_AR_BBOX,
        "format": "text",
        "minmagnitude": 2.0,
        "orderby": "time",
        "limit": 100,
        "starttime": starttime,
    }
    client = get_client()
    resp = await client.get(
        _EMSC_URL,
        params=params,
        timeout=settings.http_timeout_seconds,
    )
    resp.raise_for_status()

    rows: list[list[str]] = []
    for line in resp.text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 13:
            rows.append(parts)
    return rows


def _parse_emsc_row(parts: list[str], user_lat: float, user_lon: float) -> EarthquakeEvent | None:
    """Convierte una fila EMSC text a EarthquakeEvent. None si el payload es inválido."""
    try:
        event_id = parts[0]
        time_str = parts[1]
        ev_lat = float(parts[2])
        ev_lon = float(parts[3])
        depth_km = float(parts[4])
        magnitude = float(parts[10])
        place = parts[12]

        # EMSC time puede ser: "2026-05-26T21:27:44.5", "2026-05-26T21:27:44" o "2026-05-26T21:27"
        time_clean = time_str.split(".")[0].strip()  # elimina fracción de segundos
        if len(time_clean) == 16:  # "YYYY-MM-DDTHH:MM"
            occurred_at = datetime.strptime(time_clean, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
        else:  # "YYYY-MM-DDTHH:MM:SS"
            occurred_at = datetime.strptime(time_clean, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)

        distance_km = haversine(user_lat, user_lon, ev_lat, ev_lon)
        event_url = f"https://www.seismicportal.eu/eventdetails.html?unid={event_id}"

        return EarthquakeEvent(
            id=f"emsc-{event_id}",
            place=place,
            magnitude=round(magnitude, 1),
            depth_km=round(abs(depth_km), 1),
            occurred_at=occurred_at,
            lat=round(ev_lat, 4),
            lon=round(ev_lon, 4),
            distance_km=round(distance_km, 1),
            usgs_url=event_url,
            source="emsc",
        )
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        logger.warning("EMSC: error parseando fila [%s]: %s", parts[0] if parts else "?", exc)
        return None


async def get_recent_earthquakes(
    user_lat: float,
    user_lon: float,
    radius_km: float = 500.0,
) -> EarthquakesResponse:
    """
    Sismos recientes (≥ 2.0) en Argentina desde EMSC.
    Incluye datos de la red NSNA/INPRES con menor latencia que USGS.
    Ante error HTTP: retorna lista vacía (degradación controlada).
    """
    rows: list[list[str]] = []
    try:
        async with _cache_lock:
            if _CACHE_KEY in _event_cache:
                rows = _event_cache[_CACHE_KEY]
            else:
                rows = await _fetch_emsc()
                _event_cache[_CACHE_KEY] = rows
    except HttpxTimeout:
        logger.warning("EMSC request timeout")
    except HTTPStatusError as exc:
        logger.warning("EMSC HTTP error: %s", exc.response.status_code)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("EMSC fetch failed: %s", exc)

    events: list[EarthquakeEvent] = []
    for row in rows:
        ev = _parse_emsc_row(row, user_lat, user_lon)
        if ev is None:
            continue
        if ev.distance_km > radius_km:
            continue
        # EMSC usa nombres en mayúsculas: "SAN JUAN, ARGENTINA"
        if "ARGENTINA" not in ev.place.upper():
            continue
        events.append(ev)

    events.sort(key=lambda e: e.occurred_at, reverse=True)
    return EarthquakesResponse(total=len(events), radius_km=radius_km, events=events)
