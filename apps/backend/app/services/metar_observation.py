"""METAR observation for the dashboard "now" (FRA-320), from the Aviation Weather Center.

The nearest Argentine airport's latest METAR replaces the model reading when the airport is close
(`settings.metar_max_distance_km`) and the report is recent (`settings.metar_max_age_minutes`).

This module owns the dashboard's rules only: which airport, how a report becomes a `MetarObservation`
(SI units, humidity) and why a report is or is not used (`MetarSelection.reason`). It makes no request and
keeps no cache: the reports come from `reportes_aeronauticos.awc_metar.fetch_metar_entries`, the one AWC
request and cache per station shared with Niebla, and `latest_valid_entry` picks the report with the
highest `obsTime`.

AWC fields used: `obsTime` (epoch s), `temp`/`dewp` (°C), `wdir` (degrees or "VRB"), `wspd`/`wgst`
(kt), `wxString`, `rawOb`. Every failure returns None and is logged: the dashboard never breaks or
waits longer than `settings.metar_observation_timeout_seconds` because of the METAR. The visibility
and TAF readers live in `reportes_aeronauticos` (`metar.py`, `taf.py`); this module never uses the TAF.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.schemas.weather import MetarReason
from app.services.reportes_aeronauticos.aeropuertos import nearest_airport_with_distance
from app.services.reportes_aeronauticos.awc_metar import fetch_metar_entries, latest_valid_entry
from app.utils.parsing import parse_float

logger = logging.getLogger(__name__)

_KT_TO_KMH = 1.852


@dataclass(frozen=True)
class MetarObservation:
    """Latest METAR of one airport, in SI units."""

    icao: str
    observed_at: datetime            # UTC, from `obsTime`
    temp_c: float | None
    dewpoint_c: float | None
    humidity: float | None           # derived from temp and dewpoint (Magnus)
    wind_dir_deg: float | None       # None for variable (VRB) or calm wind
    wind_speed_kmh: float | None
    wind_gust_kmh: float | None
    wx_string: str | None            # present weather, e.g. "-RA BR", "TSRA"
    raw: str | None


@dataclass(frozen=True)
class MetarSelection:
    """Nearest airport and whether its METAR can be the dashboard "now" (`reason == "metar_ok"`)."""

    reason: MetarReason
    icao: str
    name: str
    distance_km: float
    observation: MetarObservation | None   # only set when reason == "metar_ok"


def relative_humidity(temp_c: float | None, dewpoint_c: float | None) -> float | None:
    """Relative humidity (%) by the Magnus formula, rounded and clamped to 0-100."""
    if temp_c is None or dewpoint_c is None:
        return None
    vapour = math.exp(17.625 * dewpoint_c / (243.04 + dewpoint_c))
    saturation = math.exp(17.625 * temp_c / (243.04 + temp_c))
    return float(min(100, max(0, round(100 * vapour / saturation))))


def _kt_to_kmh(value: object) -> float | None:
    knots = parse_float(value)
    return None if knots is None else round(knots * _KT_TO_KMH, 1)


def _wind_direction(wdir: object, speed_kmh: float | None) -> float | None:
    """Degrees, or None when the wind is variable ("VRB") or calm (0 kt)."""
    if speed_kmh == 0:
        return None
    degrees = parse_float(wdir)   # "VRB" does not parse
    return None if degrees is None else degrees % 360


def _parse_entry(icao: str, entry: dict, observed_at: datetime) -> MetarObservation:
    temp_c = parse_float(entry.get("temp"))
    dewpoint_c = parse_float(entry.get("dewp"))
    speed_kmh = _kt_to_kmh(entry.get("wspd"))
    wx = entry.get("wxString")
    raw = entry.get("rawOb")
    return MetarObservation(
        icao=icao,
        observed_at=observed_at,
        temp_c=temp_c,
        dewpoint_c=dewpoint_c,
        humidity=relative_humidity(temp_c, dewpoint_c),
        wind_dir_deg=_wind_direction(entry.get("wdir"), speed_kmh),
        wind_speed_kmh=speed_kmh,
        wind_gust_kmh=_kt_to_kmh(entry.get("wgst")),
        wx_string=wx if isinstance(wx, str) and wx.strip() else None,
        raw=raw if isinstance(raw, str) else None,
    )


async def fetch_latest_observation(icao: str) -> MetarObservation | None:
    """Latest METAR of `icao` as an observation, from the shared AWC list (cached there). Never raises."""
    entries = await fetch_metar_entries(icao)
    latest = None if entries is None else latest_valid_entry(entries)
    if latest is None:
        return None
    return _parse_entry(icao, latest.entry, latest.observed_at)


def classify_observation(
    distance_km: float, observation: MetarObservation | None, now: datetime
) -> MetarReason:
    """Whether the METAR can be the dashboard "now"; limits are inclusive (20.0 km / 90 min pass)."""
    if distance_km > settings.metar_max_distance_km:
        return "metar_too_far"
    if observation is None:
        return "metar_unavailable"
    if now - observation.observed_at > timedelta(minutes=settings.metar_max_age_minutes):
        return "metar_stale"
    if observation.temp_c is None or observation.dewpoint_c is None:
        return "metar_missing_fields"
    return "metar_ok"


async def get_nearest_metar_observation(
    lat: float, lon: float, now: datetime | None = None
) -> MetarSelection:
    """METAR of the nearest airport, classified; AWC is not called for an airport that is too far."""
    airport, distance_km = nearest_airport_with_distance(lat, lon)
    too_far = distance_km > settings.metar_max_distance_km
    observation = None if too_far else await fetch_latest_observation(airport.icao)
    reason = classify_observation(distance_km, observation, now or datetime.now(timezone.utc))
    if reason != "metar_ok":
        logger.info("Dashboard now: METAR %s not used (%s)", airport.icao, reason)
    return MetarSelection(
        reason=reason,
        icao=airport.icao,
        name=airport.name,
        distance_km=round(distance_km, 1),
        observation=observation if reason == "metar_ok" else None,
    )
