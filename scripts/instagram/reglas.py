"""Pure rules of the daily report (no I/O): variant, alerts, critical windows and sky text.

Product decisions (FRA-326, confirmed by the product owner):

- Wind alert: the ECMWF daily gust is >= 50 km/h, from any direction, saying where it comes from.
- Storm: weather code 95-99 or a high / severe convective risk. Always qualitative: never a hail
  percentage.
- Heavy rain: more than 15 mm in the day, with the figure the report shows (`shown_rain_mm`: the
  bound when the daily total and the ECMWF hours contradict each other).
- Variant: ``Alerta`` when any of the three holds, ``Estandar`` otherwise.
- Hierarchy on the plate: wind alert, storm, rain (probability, mm, critical window), then the
  temperatures and the sky.
- Dense fog (night notice only): visibility strictly under 500 m in some hour of the day. It is a
  model datum, so it is always worded as possible ("Niebla densa posible").
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from tipos import Franja, ReportData

Variante = Literal["Alerta", "Estandar"]
Window = tuple[int, int]  # (start hour, end hour); 24 means midnight

# Label shown to people; the file names keep the accent-free value.
VARIANT_LABEL: dict[str, str] = {"Alerta": "Alerta", "Estandar": "Estándar"}

GUST_ALERT_KMH = 50.0  # inclusive
HEAVY_RAIN_MM = 15.0  # strictly above
# A day "rains" when the anchor model gives strictly more than this. Mirrors
# `RAIN_VOTE_THRESHOLD_MM` of the backend (a test guards against drift) so the plates agree with
# the 7-day row of the web.
RAIN_THRESHOLD_MM = 0.9
STORM_CODES = range(95, 100)  # WMO thunderstorm codes 95-99
STORM_RISKS = frozenset({"high", "severe"})
STORM_TEXT = "Tormenta fuerte posible, según el modelo"
# Dense fog of the night notice: an hour with visibility strictly under this (metres).
FOG_VISIBILITY_M = 500.0
FOG_TEXT = "Niebla densa posible"

# Critical windows: contiguous 3 h slots around the peak whose value is at least this fraction of it.
RAIN_WINDOW_MIN_PEAK_MM = 0.1
RAIN_WINDOW_FRACTION = 0.5
# Gusts have a high baseline all day, so half of the peak would cover almost the whole day: the
# window of the strongest gusts is tighter.
GUST_WINDOW_MIN_PEAK_KMH = 1.0
GUST_WINDOW_FRACTION = 0.8
_EPSILON = 1e-9  # float noise guard for the ">= fraction of the peak" comparison

# Same 8 sectors as the backend (`int((deg % 360 + 22.5) / 45) % 8`), spelled in Spanish.
_ORIGINS = (
    "del norte", "del noreste", "del este", "del sudeste",
    "del sur", "del sudoeste", "del oeste", "del noroeste",
)

# Text of the sky by icon (day and night variants share the text).
_SKY_TEXT = {
    "clear-day": "Despejado",
    "partly-cloudy-day": "Parcialmente nublado",
    "overcast": "Cubierto",
    "fog": "Niebla",
    "overcast-drizzle": "Llovizna",
    "partly-cloudy-day-rain": "Lluvia leve",
    "rain": "Lluvia",
    "sleet": "Lluvia helada",
    "partly-cloudy-day-snow": "Nieve leve",
    "snow": "Nieve",
    "thunderstorms": "Tormenta",
    "hail": "Tormenta",  # qualitative on purpose: hail is never quantified
}


def round_half_up(value: float) -> int:
    """Whole number, halves toward +infinity (like JavaScript's `Math.round`)."""
    return math.floor(value + 0.5)


# ---------------------------------------------------------------------------
# Alerts and variant
# ---------------------------------------------------------------------------

def has_wind_alert(data: ReportData) -> bool:
    return data.wind_gust_max is not None and data.wind_gust_max >= GUST_ALERT_KMH


def has_storm(data: ReportData) -> bool:
    by_code = data.weather_code is not None and data.weather_code in STORM_CODES
    return by_code or data.convective_risk in STORM_RISKS


def shown_rain_mm(data: ReportData) -> float | None:
    """The rain figure the report shows: the bound ("hasta X mm") when there is one, else the total."""
    return data.precip_bound_mm if data.precip_bound_mm is not None else data.precip_sum


def has_heavy_rain(data: ReportData) -> bool:
    shown = shown_rain_mm(data)
    return shown is not None and shown > HEAVY_RAIN_MM


def variante(data: ReportData) -> Variante:
    """``Alerta`` if there is a wind alert, a storm or heavy rain; ``Estandar`` otherwise."""
    if has_wind_alert(data) or has_storm(data) or has_heavy_rain(data):
        return "Alerta"
    return "Estandar"


# ---------------------------------------------------------------------------
# Wind origin
# ---------------------------------------------------------------------------

def wind_origin(deg: float | None) -> str | None:
    """Where the wind comes from, in 8 points (``del sudoeste``); None without direction."""
    if deg is None:
        return None
    return _ORIGINS[int((deg % 360 + 22.5) / 45) % 8]


# ---------------------------------------------------------------------------
# Critical windows
# ---------------------------------------------------------------------------

def critical_window(
    slots: Sequence[Franja],
    metric: Callable[[Franja], float | None],
    *,
    min_peak: float,
    fraction: float,
) -> Window | None:
    """Contiguous slots around the slot with the highest `metric`, from its start to its end.

    A neighbour joins while it is adjacent in time and has at least `fraction` of the peak. Only the
    window around the highest peak is returned (an equal peak later in the day does not count).
    None when no slot has a value or the peak is under `min_peak`.
    """
    ordered = sorted(slots, key=lambda slot: slot.start_hour)
    values = [metric(slot) for slot in ordered]
    present = [(index, value) for index, value in enumerate(values) if value is not None]
    if not present:
        return None
    peak_index, peak = max(present, key=lambda item: (item[1], -item[0]))
    if peak < min_peak:
        return None
    threshold = peak * fraction

    def joins(neighbour: int, current: int) -> bool:
        a, b = sorted((neighbour, current))
        value = values[neighbour]
        adjacent = ordered[a].end_hour == ordered[b].start_hour
        return adjacent and value is not None and value + _EPSILON >= threshold

    first = last = peak_index
    while first > 0 and joins(first - 1, first):
        first -= 1
    while last < len(ordered) - 1 and joins(last + 1, last):
        last += 1
    return ordered[first].start_hour, ordered[last].end_hour


def rain_window(slots: Sequence[Franja]) -> Window | None:
    """Critical rain window: slots with >= 50 % of the rainiest slot (which has >= 0.1 mm)."""
    return critical_window(
        slots,
        lambda slot: slot.precip_mm,
        min_peak=RAIN_WINDOW_MIN_PEAK_MM,
        fraction=RAIN_WINDOW_FRACTION,
    )


def gust_window(slots: Sequence[Franja]) -> Window | None:
    """Window of the strongest gusts of the day."""
    return critical_window(
        slots,
        lambda slot: slot.gust_kmh,
        min_peak=GUST_WINDOW_MIN_PEAK_KMH,
        fraction=GUST_WINDOW_FRACTION,
    )


def format_window(window: Window) -> str:
    """``07:00 a 10:00 hs``; the end at midnight is written ``00:00``."""
    start, end = window
    return f"{start:02d}:00 a {end % 24:02d}:00 hs"


# ---------------------------------------------------------------------------
# Dense fog (night notice)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Fog:
    """Hours of the day with visibility under ``FOG_VISIBILITY_M``: the first, the last and the minimum."""

    first_hour: int  # 0-23, local time
    last_hour: int
    min_visibility_m: int


def dense_fog(hours: Sequence[tuple[int, float]]) -> Fog | None:
    """Dense fog of a day given ``(hour, visibility in metres)`` pairs; None when no hour is under 500 m.

    The range goes from the first to the last foggy hour (a clear hour in between does not split it).
    """
    foggy = sorted((hour, metres) for hour, metres in hours if metres < FOG_VISIBILITY_M)
    if not foggy:
        return None
    return Fog(
        first_hour=foggy[0][0],
        last_hour=foggy[-1][0],
        min_visibility_m=round_half_up(min(metres for _, metres in foggy)),
    )


def format_fog_hours(fog: Fog) -> str:
    """``04:00 a 09:00 hs``; a single foggy hour is ``06:00 hs``."""
    if fog.first_hour == fog.last_hour:
        return f"{fog.first_hour:02d}:00 hs"
    return f"{fog.first_hour:02d}:00 a {fog.last_hour:02d}:00 hs"


# ---------------------------------------------------------------------------
# Sky
# ---------------------------------------------------------------------------

def sky_text(icon: str | None) -> str | None:
    """Spanish text for a sky icon; None when the icon is unknown (nothing is invented)."""
    if not icon:
        return None
    return _SKY_TEXT.get(icon.replace("-night", "-day"))


# ---------------------------------------------------------------------------
# Assessment of one day
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WindAlert:
    gust_kmh: int
    origin: str | None
    window: str | None


@dataclass(frozen=True)
class RainInfo:
    prob_pct: int | None
    mm: float
    window: str | None
    heavy: bool
    bound: bool = False  # `mm` is a bound ("hasta"): the daily total and the hours contradict each other


@dataclass(frozen=True)
class Assessment:
    """What the plate and the caption say about one city, in hierarchy order."""

    variante: Variante
    wind: WindAlert | None
    storm: bool
    rain: RainInfo | None  # only when the day rains (> 0.9 mm)
    dry: bool  # the amount is known and it does not rain
    sky: str | None


def _wind_alert(data: ReportData) -> WindAlert | None:
    if not has_wind_alert(data) or data.wind_gust_max is None:
        return None
    window = gust_window(data.slots)
    return WindAlert(
        gust_kmh=round_half_up(data.wind_gust_max),
        origin=wind_origin(data.wind_dir_deg),
        window=None if window is None else format_window(window),
    )


def _rain_info(data: ReportData) -> RainInfo | None:
    shown = shown_rain_mm(data)
    if shown is None or shown <= RAIN_THRESHOLD_MM:
        return None
    window = rain_window(data.slots)
    return RainInfo(
        prob_pct=None if data.precip_prob is None else round_half_up(data.precip_prob),
        mm=round(shown, 1),
        window=None if window is None else format_window(window),
        heavy=has_heavy_rain(data),
        bound=data.precip_bound_mm is not None,
    )


def _is_dry(data: ReportData) -> bool:
    shown = shown_rain_mm(data)
    return shown is not None and shown <= RAIN_THRESHOLD_MM


def assess(data: ReportData) -> Assessment:
    """Apply every rule to one day."""
    return Assessment(
        variante=variante(data),
        wind=_wind_alert(data),
        storm=has_storm(data),
        rain=_rain_info(data),
        dry=_is_dry(data),
        sky=sky_text(data.icon),
    )
