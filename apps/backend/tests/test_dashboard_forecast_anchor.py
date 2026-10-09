"""Dashboard 7-day card with the ECMWF anchor (FRA-322, PR 1): builder and HTTP contract.

The pure rules live in test_daily_anchor.py. Here: `build_7d_forecast` wires them into the schema,
and `GET /api/weather/dashboard` serves the new fields without breaking the old ones (the production
frontend keeps working until the frontend PR is deployed).
"""
from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.core.rate_limit import limiter
from app.services.dashboard_builder import build_7d_forecast
from app.services.daily_anchor import ECMWF_KEY, GFS_KEY
from app.services.openmeteo import DailyForecastDataExt, MultiModelDailyData
from tests.test_daily_anchor import _om
from tests.test_dashboard_integration import _hourly
from tests.test_dashboard import _make_current_response

pytestmark = pytest.mark.usefixtures("frozen_ar_today")

_N = 7

# Fields the production frontend reads today: none of them may disappear.
_LEGACY_DAY_FIELDS = {
    "date", "day_label", "day_label_long", "icon", "temp_max", "temp_min", "precip_prob",
    "precip_sum", "wind_speed_max", "wind_icon", "wind_intensity", "wind_dir_dominant_deg",
    "wind_dir_cardinal", "wind_shift", "weather_code", "snow_level_m", "convective_risk",
    "confidence_pct", "confidence_label",
}


@pytest.fixture(autouse=True)
def fresh_rate_limit():
    """/dashboard allows 30 req/min for the whole session; start and end with a clean budget."""
    limiter.reset()
    yield
    limiter.reset()


def _multi(gfs: DailyForecastDataExt | None, ecmwf: DailyForecastDataExt | None, *, ecmwf_first=False):
    pairs = [(GFS_KEY, gfs), (ECMWF_KEY, ecmwf)]
    if ecmwf_first:
        pairs.reverse()
    return MultiModelDailyData(
        models={key: data for key, data in pairs if data is not None},
        consensus_pct_per_day=[100.0] * _N,
        rain_consensus_per_day=["all_agree_dry"] * _N,
    )


def _entries(gfs, ecmwf, **kwargs):
    return build_7d_forecast(_multi(gfs, ecmwf, ecmwf_first=kwargs.pop("ecmwf_first", False)),
                             snow_level_m=None, **kwargs)


# ---------------------------------------------------------------------------
# build_7d_forecast
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ecmwf_first", [False, True])
def test_row_follows_the_anchor_and_the_mean(ecmwf_first: bool) -> None:
    gfs = _om(temp_max=22.0, temp_min=10.0, precip_sum=0.0, wind=10.0, wind_dir=90.0, code=3)
    ecmwf = _om(temp_max=23.0, temp_min=11.0, precip_sum=6.0, precip_prob=75.0, wind=32.0,
                wind_dir=270.0, code=63)

    first = _entries(gfs, ecmwf, ecmwf_first=ecmwf_first)[0]

    assert (first.temp_max, first.temp_min) == (23, 11)
    assert isinstance(first.temp_max, int)
    assert first.precip_sum == 6.0
    assert first.precip_prob == 75.0
    assert first.wind_speed_max == 32.0
    assert first.wind_dir_dominant_deg == 270.0
    assert first.wind_dir_cardinal == "W"
    assert first.weather_code == 63
    assert first.icon == "rain"
    assert first.rain_disagreement is not None
    assert (first.rain_disagreement.gfs_mm, first.rain_disagreement.ecmwf_mm) == (0.0, 6.0)


def test_confidence_fields_are_deprecated_constants() -> None:
    entries = _entries(_om(precip_sum=0.0), _om(precip_sum=6.0))

    assert all(e.confidence_pct == 100 for e in entries)
    assert all(e.confidence_label == "ALTA" for e in entries)


def test_days_five_to_seven_are_a_trend_with_bands() -> None:
    entries = _entries(_om(), _om(precip_prob=45.0))

    assert [e.is_trend for e in entries] == [False, False, False, False, True, True, True]
    assert [e.rain_band for e in entries] == [None, None, None, None, "40-60", "40-60", "40-60"]


def test_each_day_carries_the_detail_of_both_models() -> None:
    entries = _entries(_om(temp_max=22.0, cloud=80.0), _om(temp_max=24.0, cloud=40.0))

    detail = entries[2].models
    assert (detail.gfs.temp_max, detail.ecmwf.temp_max) == (22, 24)
    assert (detail.gfs.cloud_cover_mean, detail.ecmwf.cloud_cover_mean) == (80.0, 40.0)


def test_selected_model_row_has_no_disagreement_but_keeps_both_details() -> None:
    gfs = _om(temp_max=20.0, precip_sum=0.0)
    ecmwf = _om(temp_max=25.0, precip_sum=6.0)

    first = _entries(gfs, ecmwf, selected_model="gfs")[0]

    assert first.temp_max == 20
    assert first.precip_sum == 0.0
    assert first.rain_disagreement is None
    assert first.models.gfs is not None and first.models.ecmwf is not None


def test_a_single_model_builds_the_week_without_mean_or_disagreement() -> None:
    entries = _entries(None, _om(temp_max=21.5, precip_sum=4.0))

    assert len(entries) == _N
    assert entries[0].temp_max == 22
    assert all(e.rain_disagreement is None for e in entries)
    assert entries[0].models.gfs is None


# ---------------------------------------------------------------------------
# GET /api/weather/dashboard
# ---------------------------------------------------------------------------

async def _get(client: AsyncClient, daily: MultiModelDailyData, query: str = ""):
    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock,
              return_value=_make_current_response()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=daily),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock,
              return_value=_hourly()),
    ):
        return await client.get(f"/api/weather/dashboard?lat=-31.4&lon=-64.2{query}")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_serves_the_new_contract_with_both_models(async_client: AsyncClient) -> None:
    gfs = _om(temp_max=22.0, temp_min=10.0, precip_sum=0.0, precip_prob=20.0, code=3)
    ecmwf = _om(temp_max=23.0, temp_min=11.0, precip_sum=6.0, precip_prob=80.0, code=63)

    response = await _get(async_client, _multi(gfs, ecmwf))

    assert response.status_code == 200
    data = response.json()
    assert data["forecast_models"] == ["gfs", "ecmwf"]
    day = data["forecast_7d"][0]
    assert _LEGACY_DAY_FIELDS <= set(day)
    assert day["temp_max"] == 23 and isinstance(day["temp_max"], int)
    assert day["temp_min"] == 11 and isinstance(day["temp_min"], int)
    assert day["precip_sum"] == 6.0
    assert day["rain_disagreement"] == {"gfs_mm": 0.0, "ecmwf_mm": 6.0}
    assert day["models"]["gfs"]["temp_max"] == 22
    assert day["models"]["ecmwf"]["precip_sum"] == 6.0
    assert day["is_trend"] is False and day["rain_band"] is None
    # deprecated, constant, so the old chip stays hidden
    assert day["confidence_pct"] == 100 and day["confidence_label"] == "ALTA"
    last = data["forecast_7d"][6]
    assert last["is_trend"] is True and last["rain_band"] == "60-100"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_anchor_does_not_depend_on_the_models_order(async_client: AsyncClient) -> None:
    gfs = _om(wind=10.0, wind_dir=90.0)
    ecmwf = _om(wind=32.0, wind_dir=270.0)

    gfs_first = (await _get(async_client, _multi(gfs, ecmwf))).json()["forecast_7d"][0]
    ecmwf_first = (await _get(async_client, _multi(gfs, ecmwf, ecmwf_first=True))).json()["forecast_7d"][0]

    assert gfs_first["wind_speed_max"] == 32.0
    assert gfs_first["wind_dir_cardinal"] == "W"
    assert gfs_first == ecmwf_first


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_reports_the_missing_model(async_client: AsyncClient) -> None:
    only_ecmwf = (await _get(async_client, _multi(None, _om()))).json()
    only_gfs = (await _get(async_client, _multi(_om(), None))).json()

    assert only_ecmwf["forecast_models"] == ["ecmwf"]
    assert only_gfs["forecast_models"] == ["gfs"]
    assert only_gfs["forecast_7d"][0]["rain_disagreement"] is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_selector_gfs_serves_the_gfs_row(async_client: AsyncClient) -> None:
    gfs = _om(temp_max=20.0, wind=10.0)
    ecmwf = _om(temp_max=25.0, wind=40.0)

    data = (await _get(async_client, _multi(gfs, ecmwf), "&model=gfs")).json()

    day = data["forecast_7d"][0]
    assert day["temp_max"] == 20
    assert day["wind_speed_max"] == 10.0
    assert day["rain_disagreement"] is None
    assert day["models"]["ecmwf"]["temp_max"] == 25
    assert data["forecast_models"] == ["gfs", "ecmwf"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_selector_of_an_unavailable_model_falls_back(async_client: AsyncClient) -> None:
    data = (await _get(async_client, _multi(None, _om(temp_max=21.0)), "&model=gfs")).json()

    assert data["forecast_7d"][0]["temp_max"] == 21
    assert data["forecast_models"] == ["ecmwf"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_sunrise_and_uv_come_from_the_ecmwf_anchor(async_client: AsyncClient) -> None:
    gfs = replace(_om(), uv_max=[1.0] * _N, sunrise=["2026-05-20T05:00"] * _N)
    ecmwf = replace(_om(), uv_max=[7.0] * _N, sunrise=["2026-05-20T07:00"] * _N)

    data = (await _get(async_client, _multi(gfs, ecmwf))).json()

    assert data["day_arc"]["sunrise"] == "2026-05-20T07:00"
    assert data["current"]["uv_index"] == 7.0
