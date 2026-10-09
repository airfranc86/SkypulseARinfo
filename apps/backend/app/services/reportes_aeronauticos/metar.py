"""Current visibility from the METAR of the nearest Argentine airport (AWC, no API key).

The request goes out through `awc.get_source().metar(...)`; this module owns the 30-minute cache of
usable readings and the rules that decide whether a report can be shown (distance, age, `visib`).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cachetools import TTLCache

from app.core.config import settings
from app.services.reportes_aeronauticos.aeropuertos import nearest_airport_with_distance
from app.services.reportes_aeronauticos.awc import AwcError, get_source
from app.services.visibilidad import awc_visibility_m
from app.utils.parsing import parse_float

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _MetarReading:
    """Visibility of a METAR and the time (UTC) it was observed."""
    visibility_m: float
    observed_at: datetime


# METAR is refreshed every 30-60 min, so readings live 30 min.
# A reading is cached together with its observation time: its age is checked on every read.
# Failures and old reports are NEVER cached, so the next request retries.
_metar_cache: TTLCache[str, _MetarReading] = TTLCache(maxsize=64, ttl=1800)


def clear_metar_cache() -> None:
    _metar_cache.clear()


def _obs_time(entry: dict) -> datetime | None:
    """Observation time (UTC) from AWC `obsTime` (epoch seconds); None if missing or not valid."""
    seconds = parse_float(entry.get("obsTime"))
    if seconds is None or not math.isfinite(seconds):
        return None
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _is_recent(observed_at: datetime, now: datetime) -> bool:
    """True if the report is not older than `settings.metar_max_age_minutes` (inclusive: 90 min still passes)."""
    return now - observed_at <= timedelta(minutes=settings.metar_max_age_minutes)


async def _get_metar_reading(icao: str, now: datetime) -> _MetarReading | None:
    """
    Latest usable METAR of an airport: visibility (m) and observation time.

    - Source: AWC, no API key.
    - Drops (None) a report without a valid `obsTime` or older than `settings.metar_max_age_minutes`.
      The age is checked on every read, also when the data comes from the cache.
    - Only SUCCESSFUL, recent results are cached; errors and old reports allow a retry.
    - Visibility is capped at 10 km (consistent with the rest of the system).
    """
    cached = _metar_cache.get(icao)
    if cached is not None:
        if _is_recent(cached.observed_at, now):
            logger.debug("METAR cache hit: %s → %.0f m", icao, cached.visibility_m)
            return cached
        # Expired since it was cached: discard it and ask AWC again.
        _metar_cache.pop(icao, None)
        logger.info("METAR %s: cached report too old (%s) — refetching", icao, cached.observed_at)

    try:
        data = await get_source().metar(icao, hours=2, timeout=settings.metar_timeout_seconds)
    except AwcError as exc:
        # None is NOT cached: the next request retries
        logger.warning("METAR fetch failed for %s: %s", icao, exc)
        return None

    if not isinstance(data, list) or len(data) == 0 or not isinstance(data[0], dict):
        logger.info("METAR: no data for %s", icao)
        return None

    entry = data[0]
    visib_sm = entry.get("visib")
    if visib_sm is None:
        logger.info("METAR: no visib field for %s", icao)
        return None

    vis_m = awc_visibility_m(visib_sm)
    if vis_m is None:
        logger.info("METAR: unparseable visib %r for %s", visib_sm, icao)
        return None

    observed_at = _obs_time(entry)
    if observed_at is None:
        logger.info("METAR: no valid obsTime for %s — discarded", icao)
        return None
    if not _is_recent(observed_at, now):
        logger.info("METAR: report of %s too old (%s) — discarded", icao, observed_at)
        return None

    logger.info("METAR %s: visib %r → %.0f m (obs: %s)", icao, visib_sm, vis_m, observed_at)
    reading = _MetarReading(visibility_m=vis_m, observed_at=observed_at)
    _metar_cache[icao] = reading   # only recent successes are cached
    return reading


async def get_metar_visibility(icao: str, now: datetime | None = None) -> float | None:
    """
    Current visibility (meters) from an airport's METAR, or None when there is no usable data
    (failed fetch, no valid `obsTime`, or a report older than `settings.metar_max_age_minutes`).
    """
    reading = await _get_metar_reading(icao, now or datetime.now(timezone.utc))
    return reading.visibility_m if reading else None


@dataclass(frozen=True)
class MetarVisibility:
    """Result of a METAR visibility query."""
    visibility_m: float | None
    icao: str
    station_name: str
    distance_km: float
    observed_at: datetime | None   # real observation time of the METAR (UTC); None if it was discarded


async def get_nearest_metar_visibility(
    lat: float, lon: float, now: datetime | None = None
) -> MetarVisibility:
    """
    METAR visibility of the nearest airport.

    Always returns an object; `visibility_m` is None if the airport is farther than
    `settings.metar_max_distance_km` (AWC is not called) or if the METAR is unusable or old
    (see `_get_metar_reading`). The station and the distance are reported anyway.
    """
    now = now or datetime.now(timezone.utc)
    airport, dist_km = nearest_airport_with_distance(lat, lon)
    reading: _MetarReading | None = None
    if dist_km > settings.metar_max_distance_km:
        logger.info(
            "METAR %s not used: %.1f km > %.1f km", airport.icao, dist_km, settings.metar_max_distance_km
        )
    else:
        reading = await _get_metar_reading(airport.icao, now)

    return MetarVisibility(
        visibility_m=reading.visibility_m if reading else None,
        icao=airport.icao,
        station_name=airport.name,
        distance_km=round(dist_km, 1),
        observed_at=reading.observed_at if reading else None,
    )
