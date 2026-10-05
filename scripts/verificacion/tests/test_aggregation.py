"""Tests for hourly -> daily Tmax/Tmin aggregation."""

from __future__ import annotations

import datetime as dt

import pytest

from aggregation import DailyExtremes, Window, daily_extremes

UTC = dt.UTC


def hourly(
    start: dt.datetime, values: list[float | None]
) -> list[tuple[dt.datetime, float | None]]:
    return [(start + dt.timedelta(hours=i), v) for i, v in enumerate(values)]


D = dt.date(2026, 3, 10)
MIDNIGHT = dt.datetime(2026, 3, 10, 0, tzinfo=UTC)


def test_full_day_window_from_midnight() -> None:
    series = hourly(MIDNIGHT, [float(h) for h in range(24)])

    result = daily_extremes(series, Window("00Z", 0))

    assert result == (DailyExtremes(D, tmax=23.0, tmin=0.0, n_valid=24),)


def test_window_crossing_utc_midnight() -> None:
    # 12Z..23Z of day D at 10.0 and 00Z..11Z of day D+1 at 5.0.
    series = hourly(dt.datetime(2026, 3, 10, 12, tzinfo=UTC), [10.0] * 12 + [5.0] * 12)

    result = daily_extremes(series, Window("12Z", 12))

    assert result == (DailyExtremes(D, tmax=10.0, tmin=5.0, n_valid=24),)


def test_target_date_is_the_utc_date_where_window_starts() -> None:
    series = hourly(dt.datetime(2026, 3, 10, 21, tzinfo=UTC), [1.0] * 24)

    result = daily_extremes(series, Window("21Z", 21))

    assert [e.date for e in result] == [D]


def test_minimum_valid_hours_default_is_20() -> None:
    ok = hourly(MIDNIGHT, [1.0] * 20 + [None] * 4)
    short = hourly(MIDNIGHT, [1.0] * 19 + [None] * 5)

    assert daily_extremes(ok, Window("00Z", 0))[0].tmax == 1.0
    too_few = daily_extremes(short, Window("00Z", 0))[0]
    assert (too_few.tmax, too_few.tmin, too_few.n_valid) == (None, None, 19)


def test_minimum_valid_hours_is_configurable() -> None:
    series = hourly(MIDNIGHT, [1.0] * 23 + [None])

    strict = daily_extremes(series, Window("00Z", 0), min_valid_hours=24)[0]
    relaxed = daily_extremes(series, Window("00Z", 0), min_valid_hours=12)[0]

    assert strict.tmax is None
    assert relaxed.tmax == 1.0


def test_none_and_nan_hours_do_not_count_as_valid() -> None:
    series = hourly(MIDNIGHT, [5.0] * 22 + [None, float("nan")])

    result = daily_extremes(series, Window("00Z", 0))[0]

    assert result.n_valid == 22


def test_missing_hours_in_series_count_as_invalid() -> None:
    series = hourly(MIDNIGHT, [float(h) for h in range(24)])
    series = [item for item in series if item[0].hour not in (3, 4, 5, 6, 7)]

    result = daily_extremes(series, Window("00Z", 0))[0]

    assert result.n_valid == 19
    assert result.tmax is None


def test_window_extending_past_series_end_is_none() -> None:
    series = hourly(MIDNIGHT, [1.0] * 24)

    result = daily_extremes(series, Window("12Z", 12))

    # D-1 (covers D 00Z..11Z) and D (covers D 12Z..23Z) each see only 12 valid hours.
    assert [(e.date, e.n_valid) for e in result] == [(D - dt.timedelta(days=1), 12), (D, 12)]
    assert all(e.tmax is None and e.tmin is None for e in result)


def test_day_offset_moves_window_start_to_previous_day() -> None:
    series = hourly(dt.datetime(2026, 3, 9, 21, tzinfo=UTC), [2.0] * 24)

    result = daily_extremes(series, Window("D-1 21Z", 21, day_offset=-1))

    assert result == (DailyExtremes(D, tmax=2.0, tmin=2.0, n_valid=24),)


def test_shorter_window_length() -> None:
    series = hourly(MIDNIGHT, [float(h) for h in range(24)])

    result = daily_extremes(series, Window("06-12", 6, length_hours=6), min_valid_hours=6)

    assert result[0].tmax == 11.0
    assert result[0].tmin == 6.0


def test_input_series_is_not_mutated() -> None:
    series = hourly(MIDNIGHT, [float(h) for h in range(24)])
    snapshot = list(series)

    daily_extremes(series, Window("00Z", 0))

    assert series == snapshot


def test_naive_datetime_rejected() -> None:
    series = [(dt.datetime(2026, 3, 10, 0), 1.0)]

    with pytest.raises(ValueError, match="UTC"):
        daily_extremes(series, Window("00Z", 0))


def test_non_utc_offset_rejected() -> None:
    zone = dt.timezone(dt.timedelta(hours=-3))
    series = [(dt.datetime(2026, 3, 10, 0, tzinfo=zone), 1.0)]

    with pytest.raises(ValueError, match="UTC"):
        daily_extremes(series, Window("00Z", 0))


def test_duplicate_timestamps_rejected() -> None:
    series = [(MIDNIGHT, 1.0), (MIDNIGHT, 2.0)]

    with pytest.raises(ValueError, match="duplicate"):
        daily_extremes(series, Window("00Z", 0))


def test_non_hourly_timestamp_rejected() -> None:
    series = [(MIDNIGHT + dt.timedelta(minutes=30), 1.0)]

    with pytest.raises(ValueError, match="hour"):
        daily_extremes(series, Window("00Z", 0))


@pytest.mark.parametrize("start_hour", [-1, 24])
def test_window_start_hour_validated(start_hour: int) -> None:
    with pytest.raises(ValueError, match="start_hour_utc"):
        Window("bad", start_hour)


@pytest.mark.parametrize("length", [0, -3, 49])
def test_window_length_validated(length: int) -> None:
    with pytest.raises(ValueError, match="length_hours"):
        Window("bad", 0, length_hours=length)


def test_min_valid_hours_cannot_exceed_window_length() -> None:
    with pytest.raises(ValueError, match="min_valid_hours"):
        daily_extremes([], Window("00Z", 0), min_valid_hours=25)


def test_empty_series_returns_empty_tuple() -> None:
    assert daily_extremes([], Window("00Z", 0)) == ()
