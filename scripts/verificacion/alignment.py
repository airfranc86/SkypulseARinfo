"""Data-driven choice of the window the SMN uses for its daily Tmax/Tmin.

The SMN does not document the window. Given daily SMN observations and an hourly
temperature series for the same station, each candidate window is scored by the MAE
between its Tmax/Tmin and the SMN values, separately for Tmax and Tmin.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from aggregation import (
    DEFAULT_MIN_VALID_HOURS,
    HourlyIndex,
    HourlySeries,
    Window,
    extremes_from_index,
    index_series,
)
from regtemp import DailyObs


def _window_name(start_hour: int, day_offset: int) -> str:
    prefix = "" if day_offset == 0 else f"D{day_offset:+d} "
    return f"{prefix}{start_hour:02d}Z"


def candidate_windows(
    step_hours: int = 3, day_offsets: Sequence[int] = (0,), length_hours: int = 24
) -> tuple[Window, ...]:
    """Windows starting every ``step_hours`` UTC hours, for each day offset."""
    if not 1 <= step_hours <= 24:
        raise ValueError(f"step_hours must be in 1..24, got {step_hours}")
    return tuple(
        Window(_window_name(h, offset), h, length_hours, offset)
        for offset in day_offsets
        for h in range(0, 24, step_hours)
    )


DEFAULT_WINDOWS: tuple[Window, ...] = candidate_windows()


@dataclass(frozen=True)
class WindowScore:
    """MAE of one window against SMN values over ``n`` compared days."""

    window: Window
    mae: float | None
    n: int


@dataclass(frozen=True)
class AlignmentResult:
    """Windows ranked by MAE (best first), separately for Tmax and Tmin."""

    tmax: tuple[WindowScore, ...]
    tmin: tuple[WindowScore, ...]

    @property
    def best_tmax(self) -> WindowScore | None:
        return _best(self.tmax)

    @property
    def best_tmin(self) -> WindowScore | None:
        return _best(self.tmin)


def _best(scores: tuple[WindowScore, ...]) -> WindowScore | None:
    return scores[0] if scores and scores[0].n > 0 else None


def _obs_by_date(observations: Iterable[DailyObs]) -> dict[dt.date, DailyObs]:
    by_date: dict[dt.date, DailyObs] = {}
    for obs in observations:
        if obs.date in by_date:
            raise ValueError(f"duplicate observation for {obs.date.isoformat()}")
        by_date[obs.date] = obs
    return by_date


def _score(
    window: Window,
    hourly: HourlyIndex,
    obs_by_date: dict[dt.date, DailyObs],
    min_valid_hours: int,
) -> tuple[WindowScore, WindowScore]:
    extremes = {e.date: e for e in extremes_from_index(hourly, window, min_valid_hours)}
    diffs: dict[str, list[float]] = {"tmax": [], "tmin": []}
    for date, obs in obs_by_date.items():
        ext = extremes.get(date)
        if ext is None:
            continue
        for variable, observed, predicted in (
            ("tmax", obs.tmax, ext.tmax),
            ("tmin", obs.tmin, ext.tmin),
        ):
            if observed is not None and predicted is not None:
                diffs[variable].append(abs(predicted - observed))
    return (_to_score(window, diffs["tmax"]), _to_score(window, diffs["tmin"]))


def _to_score(window: Window, diffs: list[float]) -> WindowScore:
    n = len(diffs)
    return WindowScore(window, sum(diffs) / n if n else None, n)


def _rank_key(score: WindowScore) -> tuple[bool, float, int, int]:
    return (
        score.mae is None,
        score.mae if score.mae is not None else 0.0,
        score.window.day_offset,
        score.window.start_hour_utc,
    )


def rank_windows(
    observations: Iterable[DailyObs],
    series: HourlySeries,
    windows: Sequence[Window] = DEFAULT_WINDOWS,
    min_valid_hours: int = DEFAULT_MIN_VALID_HOURS,
) -> AlignmentResult:
    """Rank candidate windows by MAE against the SMN daily Tmax and Tmin.

    ``observations`` must belong to a single station (one entry per date) and ``series``
    to the same station. Windows with no comparable day are ranked last with ``mae=None``.
    """
    if not windows:
        raise ValueError("windows must not be empty")
    obs_by_date = _obs_by_date(observations)
    hourly = index_series(series)
    scored = [_score(w, hourly, obs_by_date, min_valid_hours) for w in windows]
    return AlignmentResult(
        tmax=tuple(sorted((s[0] for s in scored), key=_rank_key)),
        tmin=tuple(sorted((s[1] for s in scored), key=_rank_key)),
    )
