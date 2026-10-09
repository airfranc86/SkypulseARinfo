"""The one AWC METAR request and the one METAR cache per station.

Niebla (`metar.py`) and the dashboard "now" (`app.services.metar_observation`) both read the raw METAR
list of a station from `fetch_metar_entries`, so the two routes make ONE request to AWC per station and
window, and `metar_awc` is counted once per real request (by `awc.HttpAwcSource`).

    GET https://aviationweather.gov/api/data/metar?ids=<ICAO>&format=json&hours=3   (no key)

What is cached is the RAW list, not a derived reading: each consumer applies its own rules on every read
(Niebla: visibility, CAVOK, 20 km and 90 min; dashboard: `MetarObservation` and the reason it is or is
not used). `latest_valid_entry` is the one rule that chooses the report both of them look at.

Lifetimes (`SingleFlightCache`, no persistence):

- a usable list lives 5 minutes (AWC publishes hourly, about 4 minutes after the hour);
- a failure lives 1 minute, so a down AWC is neither hit nor waited on by every request;
- when a refresh fails the last good list is served for at most `_STALE_TTL_SECONDS`. That never lets a
  consumer accept an old report: both re-check the age of the chosen report against their own clock on
  every read (the copy is 30 minutes counted from the fetch, not from the report time).
"""
from __future__ import annotations

import logging
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.cache import SingleFlightCache
from app.core.config import settings
from app.services.reportes_aeronauticos.awc import AwcError, get_source
from app.utils.parsing import parse_float

logger = logging.getLogger(__name__)

_LOOKBACK_HOURS = 3
_FRESH_TTL_SECONDS = 300
_FAILURE_TTL_SECONDS = 60
# The copy served when AWC fails: the 30 minutes the Niebla cache used to live, and never longer than the
# age after which a METAR is discarded anyway (`settings.metar_max_age_minutes`).
_STALE_TTL_SECONDS = min(1800.0, settings.metar_max_age_minutes * 60.0)

metar_entries_cache: SingleFlightCache[tuple[dict, ...]] = SingleFlightCache(
    maxsize=64,
    ttl=_FRESH_TTL_SECONDS,
    failure_ttl=_FAILURE_TTL_SECONDS,
    stale_ttl=_STALE_TTL_SECONDS,
    name="awc_metar",
)


@dataclass(frozen=True)
class LatestMetar:
    """The report chosen from a list: its observation time (UTC) and the raw AWC entry."""

    observed_at: datetime
    entry: dict


def _obs_time(entry: dict) -> datetime | None:
    """Observation time (UTC) from AWC `obsTime` (epoch seconds); None if missing or not valid."""
    seconds = parse_float(entry.get("obsTime"))
    if seconds is None or not math.isfinite(seconds):
        return None
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def latest_valid_entry(entries: Iterable[object]) -> LatestMetar | None:
    """The report with the highest valid `obsTime` (the first one when two share it); None if none has one.

    Entries that are not dicts, or have no valid `obsTime`, are ignored: the position in the list means
    nothing (AWC lists are not guaranteed to be ordered).
    """
    dated = [
        (observed_at, entry)
        for entry in entries
        if isinstance(entry, dict) and (observed_at := _obs_time(entry)) is not None
    ]
    if not dated:
        return None
    observed_at, entry = max(dated, key=lambda pair: pair[0])
    return LatestMetar(observed_at=observed_at, entry=entry)


async def _request(icao: str) -> tuple[dict, ...] | None:
    try:
        data = await get_source().metar(
            icao, hours=_LOOKBACK_HOURS, timeout=settings.metar_observation_timeout_seconds
        )
    except AwcError as exc:   # timeout, HTTP error, invalid JSON: the consumers fall back
        logger.warning("METAR fetch failed for %s: %r", icao, exc)
        return None
    if not isinstance(data, list):
        logger.warning("METAR %s: unexpected payload type %s", icao, type(data).__name__)
        return None
    entries = tuple(entry for entry in data if isinstance(entry, dict))
    if latest_valid_entry(entries) is None:
        logger.info("METAR %s: no report with a valid obsTime in the last %s h", icao, _LOOKBACK_HOURS)
        return None
    return entries


async def fetch_metar_entries(icao: str) -> tuple[dict, ...] | None:
    """The METAR reports AWC has for `icao` (last 3 h), or None when there is nothing usable. Never raises.

    One request per station is shared by every caller: concurrent callers wait for the same request and
    later ones read the cache (5 min; a failure is remembered for 1 min). The reports are not copied: do
    not modify them.
    """
    return await metar_entries_cache.get_or_fetch(icao, lambda: _request(icao))


def clear_metar_entries_cache() -> None:
    metar_entries_cache.clear()
