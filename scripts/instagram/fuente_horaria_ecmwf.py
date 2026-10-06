"""ECMWF hourly rain: the millimetres of each 3 h slot, from the same model as the daily total.

The daily total and probability of the report come from the ECMWF daily anchor (like the web's 7-day
row), but the backend's hourly service uses ``best_match`` (another model). Taking the slot rain from
it mixed two models: in Resistencia on 7/10/2026 the day added up to 1.8 mm while a best_match slot
had 24.6 mm. So the slot millimetres (which pick the "más intensa" window) come from ECMWF hourly.

Rules (FRA-326):

- One extra request per city and run (``ATTEMPTS = 1``: never retried). Any failure means "no data":
  the plate keeps the total and the probability and drops the window; it never falls back to
  best_match.
- The 24 hours of the day must all be present; otherwise the window is dropped with a warning.
- When their sum contradicts the daily total (beyond ``coherence_tolerance``), the report shows the
  greater of the two as a bound ("hasta X mm", decision of the product owner, option A) and places the
  window with the ECMWF hours. If the daily total is the greater one, the hours only place the window
  when they themselves "rain" (more than ``RAIN_THRESHOLD_MM``): a nearly dry hourly series cannot say
  when 20 mm fall. Either way a warning names both figures. Nothing falls back to best_match.

The backend is imported, never modified: its shared HTTP client, its retry helper and its timeout.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

import backend_path  # noqa: F401  (puts apps/backend on sys.path before the app.* imports)
from app.core import usage_counter
from app.core.config import settings
from app.core.http_client import fetch_with_retry, get_client
from app.services.daily_anchor import ECMWF_KEY
from app.services.hourly_slots import SLOT_HOURS
from app.utils.parsing import parse_float

from reglas import RAIN_THRESHOLD_MM

logger = logging.getLogger(__name__)

ECMWF_HOURLY_MODEL = ECMWF_KEY  # "ecmwf_ifs025", the anchor of the daily total
HOURLY_VARIABLE = "precipitation"  # mm of the hour that ENDS at the time stamp
TIMEZONE = "America/Argentina/Buenos_Aires"  # same local hours as the backend's series
FORECAST_DAYS = 7  # same horizon as the dashboard
# One request per city and run: the report runs once a day and a lost window is not worth a retry
# (Open-Meteo's free quota is shared); the plate degrades to "total without window".
ATTEMPTS = 1

# Coherence of the ECMWF hours with the ECMWF daily total. Open-Meteo builds ECMWF's hourly series
# from coarser model steps and its daily sum does not cover exactly the same 24 hours as the slots
# (00-24 h); on coherent days the gap was 0.1-0.8 mm (Córdoba, CABA, Resistencia, 6-7/10/2026).
# 0.5 mm absorbs that noise on small totals and 25 % on big ones (0.8 mm of 49.9 mm in CABA is 2 %),
# while a total that does not describe the hours (1.8 mm against 25.2 mm) is caught.
COHERENCE_MIN_MM = 0.5
COHERENCE_FRACTION = 0.25
_EPSILON = 1e-9  # float noise guard for the "<= tolerance" comparison

HOURS_PER_DAY = 24


@dataclass(frozen=True)
class EcmwfHourlyRain:
    """ECMWF hourly precipitation as Open-Meteo returns it (local time, UTC-3).

    ``precip_mm[i]`` is the rain of the hour that ENDS at ``times[i]``; ``None`` is a missing hour.
    """

    times: tuple[str, ...]
    precip_mm: tuple[float | None, ...]


@dataclass(frozen=True)
class SlotRain:
    """Rain of the eight 3 h slots of a day, or why there is none.

    ``by_start`` pairs each slot start hour (0, 3, ... 21) with its mm; ``None`` means the window must
    not be shown. ``bound_mm`` is the figure to show as "hasta X mm" when the daily total and the
    hours contradict each other (None when they agree or there are no hours). ``aviso`` explains any
    of this for the run summary.
    """

    by_start: tuple[tuple[int, float], ...] | None
    hourly_total: float | None
    aviso: str | None
    bound_mm: float | None = None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_hourly_rain(payload: object) -> EcmwfHourlyRain | None:
    """The hourly precipitation of an Open-Meteo answer; None when the answer is not usable."""
    if not isinstance(payload, dict):
        return None
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        return None
    times = hourly.get("time")
    values = hourly.get(HOURLY_VARIABLE)
    if not isinstance(times, list) or not isinstance(values, list):
        return None
    if not times or len(times) != len(values):
        return None
    return EcmwfHourlyRain(
        times=tuple(str(t) for t in times),
        precip_mm=tuple(parse_float(v) for v in values),
    )


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def request_params(lat: float, lon: float, days: int = FORECAST_DAYS) -> dict[str, object]:
    return {
        "latitude": lat,
        "longitude": lon,
        "models": ECMWF_HOURLY_MODEL,
        "hourly": HOURLY_VARIABLE,
        "forecast_days": days,
        "timezone": TIMEZONE,
    }


async def fetch_ecmwf_hourly_rain(lat: float, lon: float, days: int = FORECAST_DAYS) -> EcmwfHourlyRain | None:
    """One request to Open-Meteo through the backend's shared client; None on any failure (logged)."""
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
    except Exception as exc:  # network boundary: the caller degrades to "no window"
        logger.warning("Open-Meteo ECMWF horario falló (%s, %s): %s", lat, lon, exc)
        return None
    rain = parse_hourly_rain(payload)
    if rain is None:
        logger.warning("Open-Meteo ECMWF horario: respuesta sin lluvia horaria (%s, %s)", lat, lon)
    return rain


# ---------------------------------------------------------------------------
# Pure transformation
# ---------------------------------------------------------------------------

def day_hours(rain: EcmwfHourlyRain, target: date) -> tuple[float, ...] | None:
    """The rain of each hour of `target` (index ``h`` is ``h:00`` to ``h+1:00``); None if one is missing.

    The hour ``h`` to ``h+1`` is stamped ``h+1``: so the day is 01:00 ... 23:00 of `target` plus 00:00
    of the next date (which holds 23:00-24:00), like the backend's slots.
    """
    by_time = dict(zip(rain.times, rain.precip_mm, strict=True))
    next_day = target + timedelta(days=1)
    stamps = [f"{target.isoformat()}T{hour:02d}:00" for hour in range(1, HOURS_PER_DAY)]
    stamps.append(f"{next_day.isoformat()}T00:00")
    values = [by_time.get(stamp) for stamp in stamps]
    if any(value is None for value in values):
        return None
    return tuple(value for value in values if value is not None)


def slot_totals(hours: Sequence[float]) -> tuple[tuple[int, float], ...]:
    """Millimetres of each 3 h slot (start hour, mm), rounded like the backend's slots."""
    return tuple(
        (start, round(sum(hours[start:start + SLOT_HOURS]), 2))
        for start in range(0, HOURS_PER_DAY, SLOT_HOURS)
    )


def coherence_tolerance(daily_total: float) -> float:
    """0.5 mm or 25 % of the daily total, whichever is greater."""
    return max(COHERENCE_MIN_MM, COHERENCE_FRACTION * daily_total)


def is_coherent(hourly_total: float, daily_total: float) -> bool:
    return abs(hourly_total - daily_total) <= coherence_tolerance(daily_total) + _EPSILON


def _mm(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def ecmwf_slot_rain(
    rain: EcmwfHourlyRain | None,
    target: date,
    *,
    daily_total: float | None,
    anchor_is_ecmwf: bool,
    city_name: str,
) -> SlotRain:
    """Slot rain for the "más intensa" window, only when it agrees with the daily total."""
    omitted = "se omite la franja más intensa"
    if not anchor_is_ecmwf:
        aviso = f"{city_name}: el total diario no es de ECMWF; {omitted} (no se mezclan modelos)."
        return SlotRain(None, None, aviso)
    if rain is None:
        aviso = f"{city_name}: sin lluvia horaria de ECMWF; la placa muestra el total y la probabilidad y {omitted}."
        return SlotRain(None, None, aviso)
    hours = day_hours(rain, target)
    if hours is None:
        aviso = f"{city_name}: la lluvia horaria de ECMWF del {target.isoformat()} está incompleta; {omitted}."
        return SlotRain(None, None, aviso)
    hourly_total = round(sum(hours), 2)
    if daily_total is None:
        return SlotRain(None, hourly_total, None)  # the plate says nothing about rain
    if is_coherent(hourly_total, daily_total):
        return SlotRain(slot_totals(hours), hourly_total, None)
    return _bound_slot_rain(hours, hourly_total, daily_total, city_name)


def _bound_slot_rain(hours: Sequence[float], hourly_total: float, daily_total: float, city_name: str) -> SlotRain:
    """Contradiction: the greater figure is shown as a bound; the ECMWF hours place the window."""
    hourly_is_bound = hourly_total >= daily_total
    bound = round(max(hourly_total, daily_total), 1)
    # A daily bound over nearly dry hours: those hours cannot say when the rain falls.
    placeable = hourly_is_bound or hourly_total > RAIN_THRESHOLD_MM
    source = "horaria" if hourly_is_bound else "diaria"
    window = (
        "y la franja más intensa de ECMWF horario"
        if placeable
        else "sin franja (la suma horaria no alcanza para definirla)"
    )
    aviso = (
        f"{city_name}: la lluvia horaria de ECMWF suma {_mm(hourly_total)} mm y el total diario es "
        f"{_mm(daily_total)} mm (tolerancia {_mm(coherence_tolerance(daily_total))} mm); se muestra "
        f"'hasta {_mm(bound)} mm' usando la cota {source}, {window}."
    )
    return SlotRain(slot_totals(hours) if placeable else None, hourly_total, aviso, bound)
