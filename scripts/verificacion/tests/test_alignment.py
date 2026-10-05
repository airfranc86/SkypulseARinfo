"""Tests for data-driven selection of the SMN Tmax/Tmin window."""

from __future__ import annotations

import datetime as dt
import random

import pytest

from aggregation import Window, daily_extremes
from alignment import DEFAULT_WINDOWS, candidate_windows, rank_windows
from regtemp import DailyObs

UTC = dt.UTC
START = dt.datetime(2026, 1, 1, 0, tzinfo=UTC)
STATION = "TEST AERO"


def noisy_series(days: int, seed: int = 7) -> list[tuple[dt.datetime, float | None]]:
    rng = random.Random(seed)
    return [(START + dt.timedelta(hours=i), rng.gauss(15.0, 5.0)) for i in range(days * 24)]


def obs_from_windows(
    series: list[tuple[dt.datetime, float | None]], tmax_window: Window, tmin_window: Window
) -> tuple[DailyObs, ...]:
    tmax = {e.date: e.tmax for e in daily_extremes(series, tmax_window)}
    tmin = {e.date: e.tmin for e in daily_extremes(series, tmin_window)}
    dates = sorted(d for d in set(tmax) & set(tmin) if tmax[d] is not None and tmin[d] is not None)
    return tuple(DailyObs(d, STATION, tmax[d], tmin[d]) for d in dates)


def test_default_candidates_are_eight_three_hourly_windows() -> None:
    assert [w.start_hour_utc for w in DEFAULT_WINDOWS] == [0, 3, 6, 9, 12, 15, 18, 21]
    assert all(w.length_hours == 24 and w.day_offset == 0 for w in DEFAULT_WINDOWS)


def test_candidate_windows_with_offsets() -> None:
    windows = candidate_windows(step_hours=6, day_offsets=(0, -1))

    assert len(windows) == 8
    assert len({w.name for w in windows}) == 8


def test_ranking_recovers_known_windows_separately_for_tmax_and_tmin() -> None:
    series = noisy_series(40)
    obs = obs_from_windows(series, Window("t", 3), Window("t", 15))

    result = rank_windows(obs, series)

    assert result.best_tmax is not None and result.best_tmin is not None
    assert result.best_tmax.window.start_hour_utc == 3
    assert result.best_tmin.window.start_hour_utc == 15
    assert result.best_tmax.mae == pytest.approx(0.0, abs=1e-9)
    assert result.best_tmin.mae == pytest.approx(0.0, abs=1e-9)
    assert result.best_tmax.n >= 38


def test_ranking_is_sorted_by_mae_ascending_and_covers_all_windows() -> None:
    series = noisy_series(40)
    obs = obs_from_windows(series, Window("t", 3), Window("t", 3))

    result = rank_windows(obs, series)

    for scores in (result.tmax, result.tmin):
        assert len(scores) == 8
        maes = [s.mae for s in scores if s.mae is not None]
        assert maes == sorted(maes)
        assert all(s.n > 0 for s in scores)


def test_ranking_recovers_window_that_starts_on_previous_day() -> None:
    series = noisy_series(40)
    known = Window("known", 21, day_offset=-1)
    obs = obs_from_windows(series, known, known)

    result = rank_windows(obs, series, candidate_windows(day_offsets=(0, -1)))

    assert result.best_tmax is not None
    assert (result.best_tmax.window.start_hour_utc, result.best_tmax.window.day_offset) == (21, -1)
    assert result.best_tmax.mae == pytest.approx(0.0, abs=1e-9)


def test_n_counts_only_days_with_both_observation_and_valid_window() -> None:
    series = noisy_series(40)
    full = obs_from_windows(series, Window("t", 3), Window("t", 3))
    obs = tuple(
        DailyObs(o.date, o.station_name, None if i % 2 else o.tmax, o.tmin)
        for i, o in enumerate(full)
    )

    result = rank_windows(obs, series)

    assert result.best_tmax is not None and result.best_tmin is not None
    assert result.best_tmax.n == len(full) // 2
    assert result.best_tmin.n == len(full)


def test_observations_outside_series_are_skipped() -> None:
    series = noisy_series(10)
    obs = obs_from_windows(series, Window("t", 3), Window("t", 3))
    far = DailyObs(dt.date(2030, 1, 1), STATION, 20.0, 10.0)

    result = rank_windows((*obs, far), series)

    assert result.best_tmax is not None
    assert result.best_tmax.n == len(obs)


def test_windows_without_comparable_days_are_ranked_last() -> None:
    series = noisy_series(10)
    obs = obs_from_windows(series, Window("t", 3), Window("t", 3))

    result = rank_windows(obs, series, (Window("none", 0, day_offset=-30), *DEFAULT_WINDOWS))

    assert result.tmax[-1].window.name == "none"
    assert result.tmax[-1].n == 0
    assert result.tmax[-1].mae is None


def test_empty_observations_give_no_best_window() -> None:
    result = rank_windows((), noisy_series(5))

    assert result.best_tmax is None
    assert result.best_tmin is None
    assert all(s.n == 0 for s in result.tmax)


def test_duplicate_observation_dates_rejected() -> None:
    obs = (
        DailyObs(dt.date(2026, 1, 5), STATION, 20.0, 10.0),
        DailyObs(dt.date(2026, 1, 5), STATION, 21.0, 11.0),
    )

    with pytest.raises(ValueError, match="duplicate"):
        rank_windows(obs, noisy_series(10))


def test_empty_window_list_rejected() -> None:
    with pytest.raises(ValueError, match="windows"):
        rank_windows((), noisy_series(5), windows=())
