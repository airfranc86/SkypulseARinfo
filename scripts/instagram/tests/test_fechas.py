"""Dates: target day in Argentina time, Spanish names, window validation."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from fechas import (
    AR_TZ,
    MAX_DAYS_AHEAD,
    format_long_date,
    parse_iso_date,
    resolve_target_date,
    today_ar,
)

NOW = datetime(2026, 10, 6, 19, 0, tzinfo=AR_TZ)


def test_default_target_is_tomorrow() -> None:
    assert resolve_target_date(days=1, explicit=None, now=NOW) == date(2026, 10, 7)


def test_two_days_is_the_day_after_tomorrow() -> None:
    assert resolve_target_date(days=2, explicit=None, now=NOW) == date(2026, 10, 8)


def test_explicit_date_overrides_days() -> None:
    assert resolve_target_date(days=1, explicit=date(2026, 10, 10), now=NOW) == date(2026, 10, 10)


def test_today_is_taken_from_argentina_time_not_utc() -> None:
    # 23:30 in Buenos Aires is already the next day in UTC; the report must still use the AR date.
    late = datetime(2026, 10, 6, 23, 30, tzinfo=AR_TZ)
    assert late.astimezone(timezone.utc).date() == date(2026, 10, 7)
    assert today_ar(late) == date(2026, 10, 6)
    assert resolve_target_date(days=1, explicit=None, now=late) == date(2026, 10, 7)


def test_a_utc_clock_is_converted_to_argentina_time() -> None:
    utc_now = datetime(2026, 10, 7, 1, 0, tzinfo=timezone.utc)  # 22:00 of the 6th in Buenos Aires
    assert today_ar(utc_now) == date(2026, 10, 6)


def test_naive_clock_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone"):
        today_ar(datetime(2026, 10, 6, 19, 0))


def test_default_clock_is_the_real_now() -> None:
    assert abs((today_ar() - datetime.now(AR_TZ).date()).days) <= 1


def test_explicit_date_in_the_past_is_rejected() -> None:
    with pytest.raises(ValueError, match="past"):
        resolve_target_date(days=1, explicit=date(2026, 10, 5), now=NOW)


def test_explicit_date_beyond_the_forecast_window_is_rejected() -> None:
    last = NOW.date() + timedelta(days=MAX_DAYS_AHEAD)
    assert resolve_target_date(days=1, explicit=last, now=NOW) == last
    with pytest.raises(ValueError, match="window"):
        resolve_target_date(days=1, explicit=last + timedelta(days=1), now=NOW)


def test_parse_iso_date() -> None:
    assert parse_iso_date("2026-10-07") == date(2026, 10, 7)


@pytest.mark.parametrize("text", ["2026-13-01", "07/10/2026", "mañana", "", "2026-10-7x"])
def test_parse_iso_date_rejects_garbage(text: str) -> None:
    with pytest.raises(ValueError, match="AAAA-MM-DD"):
        parse_iso_date(text)


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 10, 7), "miércoles 7 de octubre"),
        (date(2026, 10, 10), "sábado 10 de octubre"),
        (date(2026, 11, 1), "domingo 1 de noviembre"),
        (date(2027, 1, 4), "lunes 4 de enero"),
    ],
)
def test_format_long_date(day: date, expected: str) -> None:
    assert format_long_date(day) == expected
