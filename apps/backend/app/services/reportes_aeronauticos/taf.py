"""TAF (terminal aerodrome forecast) from AWC: the raw entry and the hourly visibility projection for Niebla.

The request goes out through `awc.get_source().taf(...)`. This module keeps the caches of TAF entries (one
request per station, shared by concurrent callers), tells "AWC has no TAF" (None) from "AWC failed"
(`TafFetchError`) and from "the request was refused by the AWC protection" (`TafBusyError`), and projects the
forecast periods onto round Argentine hours.

Lifetimes:

- an entry lives 60 min (`SingleFlightCache`); when a refresh fails or is refused the last good one is served
  for at most three hours counted from the fetch (the TAF validity travels in the entry);
- a failure lives 60 s, so a down AWC is neither hit nor waited on by every request;
- "AWC answered but the station has no TAF" lives 300 s in its own small cache (`_no_taf_cache`): `/api/taf`
  accepts any 4-character code, and repeating one without a TAF must not go out to AWC again.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cachetools import TTLCache

from app.core.cache import FetchRefused, SingleFlightCache
from app.core.config import settings
from app.services.reportes_aeronauticos.aeropuertos import nearest_airport
from app.services.reportes_aeronauticos.awc import AwcError, get_source
from app.services.visibilidad import awc_visibility_m

logger = logging.getLogger(__name__)

# Argentina time zone offset (no DST)
_AR_TZ = timezone(timedelta(hours=-3))

# TAFs are amended less often than METARs, so entries live 60 min. The whole AWC entry is cached, only when it
# has at least one period. A failure is remembered for a minute and a refusal (`FetchRefused`) never is.
_FRESH_TTL_SECONDS = 3600
_FAILURE_TTL_SECONDS = 60
_NO_TAF_TTL_SECONDS = 300
_STALE_TTL_SECONDS = 10800
_MAX_STATIONS = 64

_taf_cache: SingleFlightCache[dict] = SingleFlightCache(
    maxsize=_MAX_STATIONS,
    ttl=_FRESH_TTL_SECONDS,
    failure_ttl=_FAILURE_TTL_SECONDS,
    # Before, a failed refresh after the first hour was a 503. Now the last good TAF is served for up to 3 h: a TAF
    # is valid for 24-30 h and every entry carries its own validity, so a copy that old is still useful and honest.
    stale_ttl=_STALE_TTL_SECONDS,
    name="awc_taf",
)
# Stations AWC answered for with no usable TAF. A separate store: it lives 5 min, not an hour, and it is not a failure.
_no_taf_cache: TTLCache[str, bool] = TTLCache(maxsize=_MAX_STATIONS, ttl=_NO_TAF_TTL_SECONDS)
# Seconds a refused caller is told to wait when the refusal does not say (it always does for the HTTP source).
_DEFAULT_RETRY_AFTER_SECONDS = 10

# Fog phenomena recognised in TAF/METAR (WMO / ICAO)
_FOG_WX_CODES: frozenset[str] = frozenset({"FG", "MIFG", "BCFG", "FZFG", "BR"})


def clear_taf_cache() -> None:
    _taf_cache.clear()
    _no_taf_cache.clear()


@dataclass(frozen=True)
class TafHourlySlot:
    """Hourly slot derived from a TAF."""
    hour_label: str       # "14:00" in Argentina local time (UTC-3)
    visibility_m: float | None
    fog_probable: bool    # True if the weather includes FG/MIFG/BCFG/FZFG/BR


class TafFetchError(Exception):
    """AWC did not answer with a usable TAF (network, HTTP error status or invalid JSON)."""


class TafBusyError(TafFetchError):
    """A NEW request to AWC was refused (429 pause or call budget) and there is no cached TAF to answer with.

    It says nothing about the station: `retry_after` is the whole seconds to wait. Callers that only want a TAF
    when it is available (Niebla) treat it like any other `TafFetchError`; `/api/taf` answers 429 `taf_busy`.
    """

    def __init__(self, message: str, retry_after: int) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def _has_fog(wx_string: object) -> bool:
    """True if the AWC `wxString` ("-RA BR", "+TSRA FG") has any fog phenomenon.

    Compares each whole code without the intensity prefix (+/-): "BRAND" does not count.
    """
    if not isinstance(wx_string, str):
        return False
    return any(code.lstrip("+-") in _FOG_WX_CODES for code in wx_string.upper().split())


def _station_key(icao: str) -> str:
    """The cache key and the code sent to AWC: trimmed and upper-case ("saco" and "SACO" are one station)."""
    return icao.strip().upper()


def _usable_entry(data: object) -> dict | None:
    """The AWC entry when it has at least one forecast period; None when AWC has no usable TAF for the station.

    Any 200 answer without a usable first entry (empty list, other shape, no forecast periods) is "no TAF": this is
    the frozen contract of `/api/taf` (404 `taf_not_found`), remembered like any other "no TAF".
    """
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        return None
    entry = data[0]
    return entry if entry.get("fcsts") else None


async def _request_entry(code: str) -> dict | None:
    """ONE request to AWC (the cache shares it). The entry; None after remembering that the station has no TAF.

    Raises `TafFetchError` when AWC failed. A `FetchRefused` (the protection said no) passes through untouched
    so that the cache does not remember it as a failure of the station.
    """
    try:
        data = await get_source().taf(code, timeout=settings.metar_timeout_seconds)
    except AwcError as exc:
        raise TafFetchError(str(exc)) from exc

    entry = _usable_entry(data)
    if entry is None:
        logger.info("TAF: no data for %s", code)
        _no_taf_cache[code] = True
        return None
    logger.info("TAF %s: %d forecast periods cached", code, len(entry["fcsts"]))
    return entry


async def fetch_taf_entry(icao: str) -> dict | None:
    """
    Full AWC TAF entry (raw text, validity and `fcsts` periods).

    - Returns None if AWC answered but the airport has no TAF (not an error); that is remembered for 5 minutes.
    - Raises `TafFetchError` if AWC failed (remembered for a minute): so the route tells "there is no TAF" (404)
      from "we could not ask" (503).
    - Raises `TafBusyError` (a `TafFetchError`) if a new request was refused and nothing cached can answer.
    - Caches only entries with at least one period; concurrent callers of a station share one request.
    """
    code = _station_key(icao)
    if code in _no_taf_cache:
        logger.debug("TAF no-TAF memory hit: %s", code)
        return None

    try:
        entry = await _taf_cache.get_or_fetch(code, lambda: _request_entry(code))
    except FetchRefused as exc:
        raise TafBusyError(
            str(exc), retry_after=int(getattr(exc, "retry_after", _DEFAULT_RETRY_AFTER_SECONDS))
        ) from exc

    if code in _no_taf_cache:   # AWC just said "no TAF": that wins over a stale copy of an older one
        return None
    if entry is None:           # served from the failure memory: a failure, never "no TAF"
        raise TafFetchError(f"AWC failed for {code} a moment ago")
    return entry


async def get_taf_for_icao(icao: str) -> list[dict] | None:
    """
    TAF periods (fcsts) of an airport, for the hourly forecast of Niebla.

    Tolerant version: any error returns None (the caller falls back to another source).
    """
    try:
        entry = await fetch_taf_entry(icao)
    except TafBusyError as exc:
        logger.debug("TAF %s not requested: %s", icao, exc)
        return None
    except TafFetchError as exc:
        logger.warning("TAF fetch failed for %s: %s", icao, exc)
        return None
    return entry["fcsts"] if entry else None


def taf_hourly_slots(fcsts: list[dict], start_ar: datetime, hours: int) -> list[TafHourlySlot]:
    """Project TAF periods onto `hours` consecutive hourly slots starting at `start_ar` (pure, no clock)."""
    slots: list[TafHourlySlot] = []

    for h in range(hours):
        target_dt = start_ar + timedelta(hours=h)
        target_ts = target_dt.timestamp()
        hour_label = target_dt.strftime("%H:%M")

        # Find the TAF period(s) covering this timestamp.
        # If several overlap (TEMPO over FM), use the lowest visibility.
        best_vis_m: float | None = None
        fog_probable = False
        any_period_found = False

        for period in fcsts:
            try:
                tf = float(period.get("timeFrom") or 0)
                tt = float(period.get("timeTo")   or 0)
            except (TypeError, ValueError):
                continue

            if not (tf <= target_ts < tt):
                continue

            any_period_found = True

            # "6+" (6 miles or more) is worth the 10 km cap, not 6 SM = 9,656 m.
            vis_m = awc_visibility_m(period.get("visib"))
            if vis_m is not None:
                # Conservative: the lowest visibility among overlapping periods
                if best_vis_m is None or vis_m < best_vis_m:
                    best_vis_m = vis_m

            # Fog phenomena in `wxString` ("-RA BR"); AWC does not send `wxList`.
            if _has_fog(period.get("wxString")):
                fog_probable = True

        slots.append(TafHourlySlot(
            hour_label=hour_label,
            visibility_m=best_vis_m if any_period_found else None,
            fog_probable=fog_probable,
        ))

    return slots


async def get_nearest_taf_hourly(
    lat: float,
    lon: float,
    hours: int = 12,
    now: datetime | None = None,
) -> list[TafHourlySlot] | None:
    """
    Hourly visibility forecast for the next `hours` hours from the TAF of the nearest airport.

    `now` (any time zone) replaces the wall clock; the slots start at the next round Argentine hour.
    Returns None if the TAF is not available or has no visibility data.
    """
    airport = nearest_airport(lat, lon)
    fcsts = await get_taf_for_icao(airport.icao)
    if not fcsts:
        return None

    # Start at the next round Argentine hour (e.g. 02:00, 03:00…). This visually separates "now"
    # (METAR / 'Ahora' line) from the future forecast (TAF bars) and avoids labels with exact minutes.
    now_ar = now.astimezone(_AR_TZ) if now is not None else datetime.now(_AR_TZ)
    start_ar = now_ar.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

    slots = taf_hourly_slots(fcsts, start_ar, hours)

    # If no slot has visibility, the TAF has no useful data
    if all(s.visibility_m is None for s in slots):
        logger.info(
            "TAF %s: no visibility data across %d slots — returning None",
            airport.icao, hours,
        )
        return None

    return slots
