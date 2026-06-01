"""Integration tests for forecast data quality (API_Prediction.md § 6.3).

IT1 — precip_prob > 0 when OM has rain expected on a specific day
IT2 — temp_max tracks OM native daily aggregate within ±1°C tolerance
IT3 — NOT all 7 days have precip_prob==0 when OM reports rain on some days
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.schemas.weather import SourceMeta, StationMeta, WeatherCurrentResponse
from app.services.openmeteo import DailyForecastDataExt, HourlyForecastExt, MultiModelDailyData
from app.services.windy import WindyHourlyEntry


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_DATES = [
    "2026-05-20", "2026-05-21", "2026-05-22",
    "2026-05-23", "2026-05-24", "2026-05-25", "2026-05-26",
]
_N = len(_DATES)
_DAY_LABELS = ["miércoles", "jueves", "viernes", "sábado", "domingo", "lunes", "martes"]


def _meta() -> SourceMeta:
    station = StationMeta(
        name="CÓRDOBA AEROPUERTO",
        lat=-31.323,
        lon=-64.208,
        distance_km=15.2,
        observed_at=datetime.now(timezone.utc),
    )
    return SourceMeta(
        source="smn",
        reason="smn_nearby_fresh",
        station=station,
        fetched_at=datetime.now(timezone.utc),
        cache_hit=False,
    )


def _current() -> WeatherCurrentResponse:
    return WeatherCurrentResponse(
        lat=-31.4,
        lon=-64.2,
        temp_c=18.5,
        feels_like_c=17.0,
        humidity=62.0,
        wind_speed_kmh=12.0,
        wind_dir_deg=270.0,
        wind_dir_cardinal="W",
        pressure_hpa=1013.0,
        precip_1h_mm=0.0,
        cloud_cover=25.0,
        description="Despejado",
        meta=_meta(),
    )


def _daily_ext(
    *,
    temp_max: list[float | None] | None = None,
    precip_prob_max: list[float | None] | None = None,
    precip_sum: list[float | None] | None = None,
    model_name: str = "ecmwf_ifs025",
) -> DailyForecastDataExt:
    return DailyForecastDataExt(
        dates=_DATES,
        day_labels=_DAY_LABELS,
        temp_max=temp_max or [22.0] * _N,
        temp_min=[10.0] * _N,
        precip_sum=precip_sum or [0.0] * _N,
        precip_prob_max=precip_prob_max or [5.0] * _N,
        wind_speed_max=[15.0] * _N,
        wind_gusts_max=[25.0] * _N,
        humidity_mean=[60.0] * _N,
        uv_max=[4.0] * _N,
        weather_codes=[0] * _N,
        sunrise=["2026-05-20T07:00"] * _N,
        sunset=["2026-05-20T18:30"] * _N,
        daylight_seconds=[41400.0] * _N,
    )


def _multi_model(daily: DailyForecastDataExt) -> MultiModelDailyData:
    return MultiModelDailyData(
        models={"ecmwf_ifs025": daily, "gfs_seamless": daily, "icon_seamless": daily},
        consensus_pct_per_day=[100.0] * _N,
        rain_consensus_per_day=["all_agree_dry"] * _N,
    )


def _hourly() -> HourlyForecastExt:
    n = 48
    timestamps = [1716220800 + i * 3600 for i in range(n)]
    return HourlyForecastExt(
        timestamps=timestamps,
        hour_labels=[f"{i % 24:02d}:00" for i in range(n)],
        dates=["2026-05-20"] * 24 + ["2026-05-21"] * 24,
        temps_c=[18.0] * n,
        precipitations=[0.0] * n,
        precip_probs=[5.0] * n,
        wind_speeds=[12.0] * n,
        weather_codes=[0] * n,
        is_day=[True if 6 <= (i % 24) <= 20 else False for i in range(n)],
    )


def _windy_hourly_dry() -> list[WindyHourlyEntry]:
    base_ts_ms = 1716220800 * 1000
    return [
        WindyHourlyEntry(
            timestamp_ms=base_ts_ms + i * 3 * 3600 * 1000,
            timestamp_s=(base_ts_ms + i * 3 * 3600 * 1000) // 1000,
            date="2026-05-20" if i < 8 else "2026-05-21",
            hour_label=f"{(i * 3) % 24:02d}:00",
            temp_c=19.0,
            humidity=58.0,
            wind_speed_kmh=14.0,
            wind_gust_kmh=22.0,
            wind_dir_deg=180.0,
            wind_dir_cardinal="S",
            precip_3h_mm=0.0,
            cloud_cover_pct=25.0,
            dewpoint_c=11.0,
            temp_850_c=5.0,
        )
        for i in range(16)
    ]


# ---------------------------------------------------------------------------
# IT1: precip_prob > 0 on a day with expected rain
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_precip_prob_present_when_rain_expected(async_client: AsyncClient):
    """Day index 3 (jueves) has rain: OM precip_prob_max=55, precip_sum=6.9.
    forecast_7d[3].precip_prob must be > 30 — the OM value must flow through."""
    precip_prob = [0.0, 0.0, 0.0, 55.0, 0.0, 0.0, 0.0]
    precip_sum = [0.0, 0.0, 0.0, 6.9, 0.0, 0.0, 0.0]
    daily = _daily_ext(precip_prob_max=precip_prob, precip_sum=precip_sum)

    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_current()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=_multi_model(daily)),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=_hourly()),
        patch("app.routers.weather.windy_get_hourly_forecast", new_callable=AsyncMock, return_value=_windy_hourly_dry()),
    ):
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    assert response.status_code == 200
    data = response.json()
    assert data["forecast_7d"][3]["precip_prob"] > 30, (
        f"Expected precip_prob > 30 for rainy day, got {data['forecast_7d'][3]['precip_prob']}"
    )


# ---------------------------------------------------------------------------
# IT2: temp_max from OM native daily aggregate within ±1°C
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_temp_max_within_tolerance_of_om(async_client: AsyncClient):
    """temp_max in the response must track OM's temperature_2m_max within ±1°C.
    Windy snapshots (19°C flat) should NOT override the true OM daily max."""
    om_temps = [24.0, 22.0, 19.5, 21.0, 23.5, 20.0, 18.0]
    daily = _daily_ext(temp_max=om_temps)

    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_current()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=_multi_model(daily)),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=_hourly()),
        patch("app.routers.weather.windy_get_hourly_forecast", new_callable=AsyncMock, return_value=_windy_hourly_dry()),
    ):
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    assert response.status_code == 200
    forecast = response.json()["forecast_7d"]
    for i, expected in enumerate(om_temps):
        actual = forecast[i]["temp_max"]
        assert abs(actual - expected) <= 1.0, (
            f"Day {i}: temp_max={actual} deviates more than 1°C from OM value {expected}"
        )


# ---------------------------------------------------------------------------
# IT3: never all-zero precip_prob when OM reports rain on some days
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_no_zero_precip_prob_for_full_week_when_rain_expected(async_client: AsyncClient):
    """When OM has precip_sum>0 on some days AND precip_prob_max>0, the 7-day
    forecast must NOT return all zeros for precip_prob — that was the original bug."""
    precip_prob = [0.0, 0.0, 40.0, 0.0, 35.0, 0.0, 0.0]
    precip_sum = [0.0, 0.0, 4.5, 0.0, 2.1, 0.0, 0.0]
    daily = _daily_ext(precip_prob_max=precip_prob, precip_sum=precip_sum)

    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_current()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=_multi_model(daily)),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=_hourly()),
        patch("app.routers.weather.windy_get_hourly_forecast", new_callable=AsyncMock, return_value=_windy_hourly_dry()),
    ):
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    assert response.status_code == 200
    forecast = response.json()["forecast_7d"]
    all_probs = [day["precip_prob"] for day in forecast]
    rainy_day_probs = [all_probs[2], all_probs[4]]  # days with precip_sum > 0
    assert any(p > 0 for p in rainy_day_probs), (
        f"All precip_prob values are zero even though OM reports rain: {all_probs}"
    )
