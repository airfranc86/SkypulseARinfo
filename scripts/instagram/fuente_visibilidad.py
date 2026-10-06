"""Hourly visibility for the night notice: is there dense fog tomorrow?

Rules (FRA-326, night notice):

- One extra request per city and run (``ATTEMPTS = 1``: never retried), like the ECMWF hourly rain.
  ``hourly=visibility`` in metres, local time of Argentina, the default model of Open-Meteo (the
  backend's hourly service uses that one too).
- Visibility is instantaneous: the day is the 24 values stamped 00:00 ... 23:00 of the forecast date.
  All 24 must be present; otherwise, or when the request fails, that city does not activate the fog
  and a warning names it (never an invented datum).
- The fog itself is decided by :func:`reglas.dense_fog` (under 500 m).

The backend is imported, never modified: its shared HTTP client, its retry helper and its timeout.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import backend_path  # noqa: F401  (puts apps/backend on sys.path before the app.* imports)
from app.core import usage_counter
from app.core.config import settings
from app.core.http_client import fetch_with_retry, get_client
from app.utils.parsing import parse_float

from reglas import Fog, dense_fog

logger = logging.getLogger(__name__)

VISIBILITY_VARIABLE = "visibility"  # metres, value AT the time stamp
TIMEZONE = "America/Argentina/Buenos_Aires"
FORECAST_DAYS = 7  # same horizon as the rest of the report
ATTEMPTS = 1  # one request per city and run; a lost fog check degrades to "no fog" with a warning
HOURS_PER_DAY = 24


@dataclass(frozen=True)
class HourlyVisibility:
    """Open-Meteo hourly visibility (local time); ``None`` is a missing hour."""

    times: tuple[str, ...]
    visibility_m: tuple[float | None, ...]


@dataclass(frozen=True)
class FogCheck:
    """Dense fog of one city for the day, or why it could not be checked (``aviso``)."""

    fog: Fog | None
    aviso: str | None


# ---------------------------------------------------------------------------
# Parsing and fetching
# ---------------------------------------------------------------------------

def parse_hourly_visibility(payload: object) -> HourlyVisibility | None:
    """The hourly visibility of an Open-Meteo answer; None when the answer is not usable."""
    if not isinstance(payload, dict):
        return None
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        return None
    times = hourly.get("time")
    values = hourly.get(VISIBILITY_VARIABLE)
    if not isinstance(times, list) or not isinstance(values, list):
        return None
    if not times or len(times) != len(values):
        return None
    return HourlyVisibility(times=tuple(str(t) for t in times), visibility_m=tuple(parse_float(v) for v in values))


def request_params(lat: float, lon: float, days: int = FORECAST_DAYS) -> dict[str, object]:
    return {
        "latitude": lat,
        "longitude": lon,
        "hourly": VISIBILITY_VARIABLE,
        "forecast_days": days,
        "timezone": TIMEZONE,
    }


async def fetch_visibility(lat: float, lon: float, days: int = FORECAST_DAYS) -> HourlyVisibility | None:
    """One request through the backend's shared client; None on any failure (logged)."""
    try:
        client = get_client()
        usage_counter.record("open_meteo")
        response = await fetch_with_retry(
            client,
            "GET",
            settings.openmeteo_base_url,
            max_attempts=ATTEMPTS,
            params=request_params(lat, lon, days),
            timeout=settings.http_timeout_seconds,
        )
        payload = response.json()
    except Exception as exc:  # network boundary: the caller degrades to "no fog" with a warning
        logger.warning("Open-Meteo visibilidad falló (%s, %s): %s", lat, lon, exc)
        return None
    series = parse_hourly_visibility(payload)
    if series is None:
        logger.warning("Open-Meteo visibilidad: respuesta sin visibilidad horaria (%s, %s)", lat, lon)
    return series


# ---------------------------------------------------------------------------
# Pure transformation
# ---------------------------------------------------------------------------

def day_visibility(series: HourlyVisibility, target: date) -> tuple[tuple[int, float], ...] | None:
    """``(hour, metres)`` for 00:00 ... 23:00 of `target`; None if one hour is missing."""
    by_time = dict(zip(series.times, series.visibility_m, strict=True))
    pairs: list[tuple[int, float]] = []
    for hour in range(HOURS_PER_DAY):
        value = by_time.get(f"{target.isoformat()}T{hour:02d}:00")
        if value is None:
            return None
        pairs.append((hour, value))
    return tuple(pairs)


def fog_check(series: HourlyVisibility | None, target: date, *, city_name: str) -> FogCheck:
    """Dense fog of `target`; without a complete day, no fog and a warning for the run summary."""
    if series is None:
        return FogCheck(None, f"{city_name}: sin visibilidad horaria; no se evalúa la niebla densa.")
    hours = day_visibility(series, target)
    if hours is None:
        aviso = f"{city_name}: la visibilidad horaria del {target.isoformat()} está incompleta; no se evalúa la niebla densa."
        return FogCheck(None, aviso)
    return FogCheck(dense_fog(hours), None)
