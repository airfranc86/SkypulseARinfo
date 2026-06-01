"""Tests for field-source priority in _build_7d_forecast.

PR1 (precip_prob):
  T1 — OM primary when Windy available
  T2 — OM primary when Windy absent
  T3 — Windy fallback when OM has no data

PR2 (temp_max / temp_min):
  T4 — OM primary when Windy available
  T5 — Windy fallback when OM has no data
  T6 — both None → no crash, returns None

PR3 (Windy-primary fields):
  T7  — precip_sum uses Windy primary
  T8  — wind_speed_max uses Windy primary
  T10 — consensus averages multiple OM models
  T11 — selected_model filters OM list
"""
from __future__ import annotations

import pytest
from datetime import date

from app.routers.weather import _build_7d_forecast
from app.services.openmeteo import DailyForecastDataExt, MultiModelDailyData
from app.services.windy import WindyDailyEntry


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_DATES = ["2026-05-20", "2026-05-21", "2026-05-22",
          "2026-05-23", "2026-05-24", "2026-05-25", "2026-05-26"]
_N = len(_DATES)


def _make_om(
    *,
    temp_max: list[float | None] | None = None,
    temp_min: list[float | None] | None = None,
    precip_prob_max: list[float | None] | None = None,
    precip_sum: list[float | None] | None = None,
    wind_speed_max: list[float | None] | None = None,
    model_name: str = "ecmwf_ifs025",
) -> DailyForecastDataExt:
    return DailyForecastDataExt(
        dates=_DATES,
        day_labels=["miércoles"] * _N,
        temp_max=temp_max if temp_max is not None else [22.0] * _N,
        temp_min=temp_min if temp_min is not None else [10.0] * _N,
        precip_sum=precip_sum if precip_sum is not None else [0.0] * _N,
        precip_prob_max=precip_prob_max if precip_prob_max is not None else [5.0] * _N,
        wind_speed_max=wind_speed_max if wind_speed_max is not None else [15.0] * _N,
        wind_gusts_max=[25.0] * _N,
        humidity_mean=[60.0] * _N,
        uv_max=[4.0] * _N,
        weather_codes=[0] * _N,
        sunrise=["2026-05-20T07:00"] * _N,
        sunset=["2026-05-20T18:30"] * _N,
        daylight_seconds=[41400.0] * _N,
    )


def _make_multi(om: DailyForecastDataExt | None = None) -> MultiModelDailyData:
    m = om or _make_om()
    return MultiModelDailyData(
        models={"ecmwf_ifs025": m, "gfs_seamless": m},
        consensus_pct_per_day=[100.0] * _N,
        rain_consensus_per_day=["all_agree_dry"] * _N,
    )


def _make_windy(
    *,
    temp_max_c: float = 23.0,
    temp_min_c: float = 11.0,
    precip_prob: float = 0.0,
    precip_sum_mm: float = 0.0,
    wind_speed_max_kmh: float = 18.0,
) -> list[WindyDailyEntry]:
    return [
        WindyDailyEntry(
            date=d,
            temp_max_c=temp_max_c,
            temp_min_c=temp_min_c,
            humidity_mean=58.0,
            wind_speed_max_kmh=wind_speed_max_kmh,
            wind_speed_mean_kmh=12.0,
            wind_gust_max_kmh=27.0,
            wind_dir_cardinal="S",
            precip_sum_mm=precip_sum_mm,
            precip_prob=precip_prob,
            cloud_cover_mean=25.0,
        )
        for d in _DATES
    ]


def _first(daily_multi: MultiModelDailyData, windy: list[WindyDailyEntry] | None = None) -> object:
    """Run _build_7d_forecast and return the first day entry."""
    entries = _build_7d_forecast(daily_multi, windy, snow_level_m=None)
    return entries[0]


# ---------------------------------------------------------------------------
# T1 — precip_prob: OM primary when Windy available (Windy has 0, OM has 60)
# ---------------------------------------------------------------------------

def test_precip_prob_uses_om_when_windy_available():
    om = _make_om(precip_prob_max=[60.0] * _N)
    multi = _make_multi(om)
    windy = _make_windy(precip_prob=0.0)

    entry = _first(multi, windy)
    assert entry.precip_prob == pytest.approx(60.0), (
        "precip_prob must come from OM (primary) even when Windy is available"
    )


# ---------------------------------------------------------------------------
# T2 — precip_prob: OM primary when Windy absent
# ---------------------------------------------------------------------------

def test_precip_prob_not_zero_when_om_has_rain_forecast():
    om = _make_om(precip_prob_max=[45.0] * _N)
    multi = _make_multi(om)

    entry = _first(multi, windy=None)
    assert entry.precip_prob == pytest.approx(45.0)


# ---------------------------------------------------------------------------
# T3 — precip_prob: Windy fallback when OM has no data
# ---------------------------------------------------------------------------

def test_precip_prob_fallback_to_windy_when_om_none():
    om = _make_om(precip_prob_max=[None] * _N)
    multi = _make_multi(om)
    windy = _make_windy(precip_prob=30.0)

    entry = _first(multi, windy)
    assert entry.precip_prob == pytest.approx(30.0), (
        "When OM precip_prob_max is None, must fall back to Windy precip_prob"
    )


# ---------------------------------------------------------------------------
# T4 — temp_max: OM primary when Windy available
# ---------------------------------------------------------------------------

def test_temp_max_uses_om_not_windy_snapshots():
    om = _make_om(temp_max=[22.0] * _N)
    multi = _make_multi(om)
    windy = _make_windy(temp_max_c=18.0)  # Windy lower — should NOT win

    entry = _first(multi, windy)
    assert entry.temp_max == pytest.approx(22.0), (
        "temp_max must come from OM (native daily max), not Windy max(temp_3h snapshots)"
    )


# ---------------------------------------------------------------------------
# T5 — temp_max: Windy fallback when OM has no data
# ---------------------------------------------------------------------------

def test_temp_max_fallback_to_windy_when_om_none():
    om = _make_om(temp_max=[None] * _N)
    multi = _make_multi(om)
    windy = _make_windy(temp_max_c=19.0)

    entry = _first(multi, windy)
    assert entry.temp_max == pytest.approx(19.0), (
        "When OM temp_max is None, must fall back to Windy temp_max_c"
    )


# ---------------------------------------------------------------------------
# T6 — temp_max: both None → no crash, returns None
# ---------------------------------------------------------------------------

def test_temp_max_both_none():
    om = _make_om(temp_max=[None] * _N)
    multi = _make_multi(om)

    entry = _first(multi, windy=None)  # No Windy either
    assert entry.temp_max is None, "Both sources None → entry.temp_max must be None (no crash)"


# ---------------------------------------------------------------------------
# T7 — precip_sum: Windy primary over OM
# ---------------------------------------------------------------------------

def test_precip_sum_uses_windy_primary():
    om = _make_om(precip_sum=[2.1] * _N)
    multi = _make_multi(om)
    windy = _make_windy(precip_sum_mm=3.5)

    entry = _first(multi, windy)
    assert entry.precip_sum == pytest.approx(3.5), (
        "precip_sum must come from Windy (higher temporal resolution), not OM"
    )


# ---------------------------------------------------------------------------
# T8 — wind_speed_max: Windy primary over OM
# ---------------------------------------------------------------------------

def test_wind_speed_max_uses_windy_primary():
    om = _make_om(wind_speed_max=[32.0] * _N)
    multi = _make_multi(om)
    windy = _make_windy(wind_speed_max_kmh=45.0)

    entry = _first(multi, windy)
    assert entry.wind_speed_max == pytest.approx(45.0), (
        "wind_speed_max must come from Windy (max over 3h slots captures gusts better)"
    )


# ---------------------------------------------------------------------------
# T10 — consensus averages multiple OM models
# ---------------------------------------------------------------------------

def test_consensus_mode_averages_multiple_om_models():
    om_a = _make_om(temp_max=[20.0] * _N, model_name="ecmwf_ifs025")
    om_b = _make_om(temp_max=[22.0] * _N, model_name="gfs_seamless")
    om_c = _make_om(temp_max=[24.0] * _N, model_name="icon_seamless")
    multi = MultiModelDailyData(
        models={"ecmwf_ifs025": om_a, "gfs_seamless": om_b, "icon_seamless": om_c},
        consensus_pct_per_day=[80.0] * _N,
        rain_consensus_per_day=["all_agree_dry"] * _N,
    )

    entries = _build_7d_forecast(multi, windy_daily=None, snow_level_m=None, selected_model="consensus")
    assert entries[0].temp_max == pytest.approx(22.0), (
        "Consensus mode: mean([20, 22, 24]) == 22.0"
    )


# ---------------------------------------------------------------------------
# T11 — selected_model filters OM list to a single model
# ---------------------------------------------------------------------------

def test_selected_model_filters_om_list():
    om_ecmwf = _make_om(temp_max=[22.0] * _N)
    om_gfs   = _make_om(temp_max=[18.0] * _N)  # different value
    multi = MultiModelDailyData(
        models={"ecmwf_ifs025": om_ecmwf, "gfs_seamless": om_gfs},
        consensus_pct_per_day=[100.0] * _N,
        rain_consensus_per_day=["all_agree_dry"] * _N,
    )

    entries = _build_7d_forecast(multi, windy_daily=None, snow_level_m=None, selected_model="ecmwf")
    assert entries[0].temp_max == pytest.approx(22.0), (
        "Mode=ecmwf: only ecmwf_ifs025 contributes; gfs_seamless (18.0) must be ignored"
    )
