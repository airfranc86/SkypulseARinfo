"""TAF (terminal aerodrome forecast) from AWC: the raw entry and the hourly visibility projection for Niebla.

The request goes out through `awc.get_source().taf(...)`. This module keeps the 60-minute cache of
TAF entries, tells "AWC has no TAF" (None) from "AWC failed" (`TafFetchError`) and projects the
forecast periods onto round Argentine hours.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cachetools import TTLCache

from app.core.config import settings
from app.services.reportes_aeronauticos.aeropuertos import nearest_airport
from app.services.reportes_aeronauticos.awc import AwcError, get_source
from app.services.visibilidad import awc_visibility_m

logger = logging.getLogger(__name__)

# Argentina time zone offset (no DST)
_AR_TZ = timezone(timedelta(hours=-3))

# TAFs are amended less often than METARs, so entries live 60 min. The whole AWC entry is cached,
# only when it has at least one period; errors are NEVER cached, so the next request retries.
_taf_cache: TTLCache[str, dict] = TTLCache(maxsize=32, ttl=3600)

# Fog phenomena recognised in TAF/METAR (WMO / ICAO)
_FOG_WX_CODES: frozenset[str] = frozenset({"FG", "MIFG", "BCFG", "FZFG", "BR"})


def clear_taf_cache() -> None:
    _taf_cache.clear()


@dataclass(frozen=True)
class TafHourlySlot:
    """Hourly slot derived from a TAF."""
    hour_label: str       # "14:00" in Argentina local time (UTC-3)
    visibility_m: float | None
    fog_probable: bool    # True if the weather includes FG/MIFG/BCFG/FZFG/BR


class TafFetchError(Exception):
    """AWC did not answer with a usable TAF (network, HTTP error status or invalid JSON)."""


def _has_fog(wx_string: object) -> bool:
    """True if the AWC `wxString` ("-RA BR", "+TSRA FG") has any fog phenomenon.

    Compares each whole code without the intensity prefix (+/-): "BRAND" does not count.
    """
    if not isinstance(wx_string, str):
        return False
    return any(code.lstrip("+-") in _FOG_WX_CODES for code in wx_string.upper().split())


async def fetch_taf_entry(icao: str) -> dict | None:
    """
    Full AWC TAF entry (raw text, validity and `fcsts` periods).

    - Returns None if AWC answered but the airport has no TAF (not an error).
    - Raises `TafFetchError` if AWC failed: so the route tells "there is no TAF" (404) from
      "we could not ask" (503).
    - Caches only entries with at least one period; errors are NOT cached.
    """
    cached = _taf_cache.get(icao)
    if cached is not None:
        logger.debug("TAF cache hit: %s", icao)
        return cached

    try:
        data = await get_source().taf(icao, timeout=settings.metar_timeout_seconds)
    except AwcError as exc:
        raise TafFetchError(str(exc)) from exc

    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        logger.info("TAF: no data for %s", icao)
        return None

    entry = data[0]
    if not entry.get("fcsts"):
        logger.info("TAF: no fcsts for %s", icao)
        return None

    _taf_cache[icao] = entry
    logger.info("TAF %s: %d forecast periods cached", icao, len(entry["fcsts"]))
    return entry


async def get_taf_for_icao(icao: str) -> list[dict] | None:
    """
    TAF periods (fcsts) of an airport, for the hourly forecast of Niebla.

    Tolerant version: any error returns None (the caller falls back to another source).
    """
    try:
        entry = await fetch_taf_entry(icao)
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
