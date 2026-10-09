"""7-day card built from a stored copy that is a day old (Redis last-good copy across midnight).

`build_7d_forecast` labels every day against today's date at serve time, but the dates come from the
stored copy. A copy fetched the evening before and served after Argentine midnight starts with
yesterday: nobody got the "Hoy" label and the hero lost today's max and min. Past days are dropped.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import patch

from app.services.dashboard_builder import AR_TZ, build_7d_forecast
from app.services.daily_anchor import ECMWF_KEY, GFS_KEY
from app.services.openmeteo import DailyForecastDataExt, MultiModelDailyData
from tests.test_daily_anchor import _om

_TODAY = date(2026, 10, 9)
_NOW = datetime(2026, 10, 9, 1, 30, tzinfo=AR_TZ)


def _dates(first: date, n: int = 7) -> list[str]:
    return [(first + timedelta(days=i)).isoformat() for i in range(n)]


def _multi(dates: list[str]) -> MultiModelDailyData:
    models: dict[str, DailyForecastDataExt] = {
        GFS_KEY: _om(dates=dates, temp_max=20.0),
        ECMWF_KEY: _om(dates=dates, temp_max=24.0),
    }
    return MultiModelDailyData(
        models=models,
        consensus_pct_per_day=[100.0] * len(dates),
        rain_consensus_per_day=["all_agree_dry"] * len(dates),
    )


def _build(dates: list[str]):
    with patch("app.services.dashboard_builder.datetime") as fake:
        fake.now.return_value = _NOW
        return build_7d_forecast(_multi(dates), snow_level_m=None)


def test_a_copy_starting_yesterday_drops_the_past_day_and_today_is_first() -> None:
    entries = _build(_dates(_TODAY - timedelta(days=1)))

    assert [e.date for e in entries][0] == _TODAY.isoformat()
    assert entries[0].day_label == "Hoy"
    assert entries[1].day_label == "Mañana"
    assert len(entries) == 6


def test_a_fresh_copy_keeps_all_seven_days() -> None:
    entries = _build(_dates(_TODAY))

    assert len(entries) == 7
    assert entries[0].day_label == "Hoy"


def test_a_copy_from_two_days_ago_drops_both_past_days() -> None:
    entries = _build(_dates(_TODAY - timedelta(days=2)))

    assert entries[0].day_label == "Hoy"
    assert len(entries) == 5


def test_a_copy_with_only_past_days_gives_no_rows() -> None:
    entries = _build(_dates(_TODAY - timedelta(days=9)))

    assert entries == []


def test_the_kept_days_keep_their_own_values() -> None:
    """Dropping a past day must not shift the data: each kept row reads its own array index."""
    dates = _dates(_TODAY - timedelta(days=1))
    gfs = _om(dates=dates, temp_max=20.0)
    ecmwf = _om(dates=dates, temp_max=24.0)
    ecmwf = DailyForecastDataExt(**{**ecmwf.__dict__, "temp_max": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0]})
    multi = MultiModelDailyData(
        models={GFS_KEY: gfs, ECMWF_KEY: ecmwf},
        consensus_pct_per_day=[100.0] * 7,
        rain_consensus_per_day=["all_agree_dry"] * 7,
    )
    with patch("app.services.dashboard_builder.datetime") as fake:
        fake.now.return_value = _NOW
        entries = build_7d_forecast(multi, snow_level_m=None)

    # Today is index 1 of the stored copy: the ECMWF anchor gives 11, the mean with GFS 20 is 16.
    assert entries[0].date == _TODAY.isoformat()
    assert entries[0].temp_max == 16
