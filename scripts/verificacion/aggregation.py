"""Aggregate hourly temperature series into daily Tmax/Tmin over a configurable UTC window.

The target date of a window is the UTC date on which the window starts (shifted by
``day_offset`` days, e.g. ``-1`` for a window that starts the previous UTC day).
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

HourlySeries = Sequence[tuple[dt.datetime, float | None]]
HourlyIndex = Mapping[dt.datetime, float | None]

DEFAULT_MIN_VALID_HOURS = 20
_MAX_WINDOW_HOURS = 48
_ZERO = dt.timedelta(0)


@dataclass(frozen=True)
class Window:
    """A UTC aggregation window starting at ``start_hour_utc`` for ``length_hours``."""

    name: str
    start_hour_utc: int
    length_hours: int = 24
    day_offset: int = 0  # days added to the target date to get the window start date

    def __post_init__(self) -> None:
        if not 0 <= self.start_hour_utc <= 23:
            raise ValueError(f"start_hour_utc must be in 0..23, got {self.start_hour_utc}")
        if not 1 <= self.length_hours <= _MAX_WINDOW_HOURS:
            raise ValueError(
                f"length_hours must be in 1..{_MAX_WINDOW_HOURS}, got {self.length_hours}"
            )

    def start_for(self, target: dt.date) -> dt.datetime:
        """UTC instant where the window for ``target`` begins."""
        start_date = target + dt.timedelta(days=self.day_offset)
        return dt.datetime.combine(start_date, dt.time(self.start_hour_utc), tzinfo=dt.UTC)


@dataclass(frozen=True)
class DailyExtremes:
    """Tmax/Tmin of one target date; ``None`` if too few valid hours."""

    date: dt.date
    tmax: float | None
    tmin: float | None
    n_valid: int


def _is_valid(value: float | None) -> bool:
    return value is not None and math.isfinite(value)


def _check_timestamp(ts: dt.datetime) -> None:
    if ts.tzinfo is None or ts.utcoffset() != _ZERO:
        raise ValueError(f"timestamp must be timezone-aware UTC, got {ts!r}")
    if ts.minute or ts.second or ts.microsecond:
        raise ValueError(f"timestamp must be on the hour, got {ts!r}")


def index_series(series: HourlySeries) -> dict[dt.datetime, float | None]:
    """Validate an hourly series and index it by timestamp."""
    index: dict[dt.datetime, float | None] = {}
    for ts, value in series:
        _check_timestamp(ts)
        if ts in index:
            raise ValueError(f"duplicate timestamp {ts.isoformat()}")
        index[ts] = value
    return index


def _window_values(hourly: HourlyIndex, window: Window, target: dt.date) -> list[float]:
    start = window.start_for(target)
    values = (hourly.get(start + dt.timedelta(hours=k)) for k in range(window.length_hours))
    return [v for v in values if v is not None and _is_valid(v)]


def extremes_for_date(
    hourly: HourlyIndex, window: Window, target: dt.date, min_valid_hours: int
) -> DailyExtremes:
    """Tmax/Tmin of ``target`` using ``window``; ``None`` below ``min_valid_hours``."""
    values = _window_values(hourly, window, target)
    if len(values) < min_valid_hours:
        return DailyExtremes(target, None, None, len(values))
    return DailyExtremes(target, max(values), min(values), len(values))


def _candidate_dates(hourly: HourlyIndex, window: Window) -> list[dt.date]:
    first = min(hourly).date()
    last = max(hourly).date()
    pad = window.length_hours // 24 + 2
    low = first - dt.timedelta(days=pad + window.day_offset)
    high = last + dt.timedelta(days=1 - window.day_offset)
    return [low + dt.timedelta(days=i) for i in range((high - low).days + 1)]


def extremes_from_index(
    hourly: HourlyIndex, window: Window, min_valid_hours: int = DEFAULT_MIN_VALID_HOURS
) -> tuple[DailyExtremes, ...]:
    """Like ``daily_extremes`` for an already validated index (avoids re-indexing)."""
    if not 1 <= min_valid_hours <= window.length_hours:
        raise ValueError(
            f"min_valid_hours must be in 1..{window.length_hours}, got {min_valid_hours}"
        )
    if not hourly:
        return ()
    results = (
        extremes_for_date(hourly, window, d, min_valid_hours)
        for d in _candidate_dates(hourly, window)
    )
    return tuple(e for e in results if e.n_valid > 0)


def daily_extremes(
    series: HourlySeries, window: Window, min_valid_hours: int = DEFAULT_MIN_VALID_HOURS
) -> tuple[DailyExtremes, ...]:
    """Daily Tmax/Tmin for every target date whose window overlaps the series.

    Dates with at least one valid hour are returned, sorted by date. A date with fewer
    than ``min_valid_hours`` valid hours (missing, ``None`` or NaN) has ``None`` extremes.
    Timestamps must be timezone-aware UTC on the hour; duplicates are rejected.
    """
    return extremes_from_index(index_series(series), window, min_valid_hours)
