"""Current visibility from the METAR of the nearest Argentine airport (AWC, no API key).

The reports come from `awc_metar.fetch_metar_entries`, the one AWC request and cache shared with the
dashboard "now"; this module owns the rules that decide whether the latest report can be shown
(distance, age, `visib`) and how its visibility is read.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.services.reportes_aeronauticos.aeropuertos import nearest_airport_with_distance
from app.services.reportes_aeronauticos.awc_metar import fetch_metar_entries, latest_valid_entry
from app.services.visibilidad import awc_visibility_m

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _MetarReading:
    """Visibility of a METAR and the time (UTC) it was observed."""
    visibility_m: float
    observed_at: datetime


def _is_recent(observed_at: datetime, now: datetime) -> bool:
    """True if the report is not older than `settings.metar_max_age_minutes` (inclusive: 90 min still passes)."""
    return now - observed_at <= timedelta(minutes=settings.metar_max_age_minutes)


async def _get_metar_reading(icao: str, now: datetime) -> _MetarReading | None:
    """
    Latest usable METAR of an airport: visibility (m) and observation time.

    - Source: the shared AWC list (`fetch_metar_entries`); the report is the one with the highest `obsTime`.
    - Drops (None) a missing or failed list, a latest report without `visib`, or one older than
      `settings.metar_max_age_minutes`. The age is checked on every read, also when the list is cached.
    - Visibility is capped at 10 km (consistent with the rest of the system).
    """
    entries = await fetch_metar_entries(icao)
    if entries is None:
        logger.info("METAR: no data for %s", icao)
        return None

    latest = latest_valid_entry(entries)
    if latest is None:
        logger.info("METAR: no valid obsTime for %s — discarded", icao)
        return None

    visib_sm = latest.entry.get("visib")
    if visib_sm is None:
        logger.info("METAR: no visib field for %s", icao)
        return None

    vis_m = awc_visibility_m(visib_sm)
    if vis_m is None:
        logger.info("METAR: unparseable visib %r for %s", visib_sm, icao)
        return None

    observed_at = latest.observed_at
    if not _is_recent(observed_at, now):
        logger.info("METAR: report of %s too old (%s) — discarded", icao, observed_at)
        return None

    logger.info("METAR %s: visib %r → %.0f m (obs: %s)", icao, visib_sm, vis_m, observed_at)
    return _MetarReading(visibility_m=vis_m, observed_at=observed_at)


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
