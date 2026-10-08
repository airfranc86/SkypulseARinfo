"""Integration: the dashboard "now" uses the nearby METAR (FRA-320) and fails open to the model."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from httpx import AsyncClient

from app.core.rate_limit import limiter
from app.schemas.weather import SourceMeta, WeatherCurrentResponse
from app.services.metar_observation import AWC_METAR_URL
from app.services.openmeteo import OpenMeteoCurrent
from tests.test_dashboard_integration import _daily_ext, _hourly, _multi_model

pytestmark = [pytest.mark.integration, pytest.mark.live_current_observation]

ROSARIO = (-32.95, -60.65)               # SAAR ~13 km
SANTIAGO_DEL_ESTERO = (-27.78, -64.27)   # no airport within 20 km
QUILMES = (-34.72, -58.25)               # SABE ~23.5 km: inside the old 30 km limit, beyond the 20 km one


@pytest.fixture(autouse=True)
def fresh_rate_limit():
    """/dashboard allows 30 req/min and the limiter is shared by the whole session: the dashboard
    test files already use almost all of it, so this module starts and ends with a clean budget."""
    limiter.reset()
    yield
    limiter.reset()


def _model_time() -> datetime:
    return datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=5)


def _model_current(lat: float, lon: float, observed_at: datetime) -> WeatherCurrentResponse:
    meta = SourceMeta(
        source="openmeteo",
        reason="smn_disabled",
        fetched_at=datetime.now(timezone.utc),
        observed_at=observed_at,
    )
    return WeatherCurrentResponse(
        lat=lat, lon=lon, temp_c=15.0, feels_like_c=14.0, humidity=70.0,
        wind_speed_kmh=12.0, wind_dir_deg=180.0, wind_dir_cardinal="S",
        pressure_hpa=1010.0, precip_1h_mm=0.0, cloud_cover=20.0,
        description=None, weather_code=1, meta=meta,
    )


def _om_current(observed_at: datetime) -> OpenMeteoCurrent:
    return OpenMeteoCurrent(
        temp_c=15.0, feels_like_c=14.0, humidity=70.0, wind_speed_kmh=12.0, wind_dir_deg=180.0,
        pressure_hpa=1010.0, precip_1h_mm=0.0, cloud_cover=20.0, weather_code=1,
        description=None, fetched_at=datetime.now(timezone.utc), observed_at=observed_at,
        wind_gust_kmh=24.0,
    )


async def _get_dashboard(client: AsyncClient, lat: float, lon: float, observed_at: datetime):
    daily = _daily_ext()
    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock,
              return_value=_model_current(lat, lon, observed_at)),
        patch("app.routers.weather.get_openmeteo_current", new_callable=AsyncMock,
              return_value=_om_current(observed_at)),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock,
              return_value=_multi_model(daily)),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock,
              return_value=_hourly()),
    ):
        return await client.get(f"/api/weather/dashboard?lat={lat}&lon={lon}")


def _metar(obs_time: datetime) -> list[dict]:
    return [{
        "icaoId": "SAAR", "obsTime": int(obs_time.timestamp()), "temp": 22, "dewp": 11,
        "wdir": "VRB", "wspd": 4, "wgst": 20, "wxString": "-RA",
        "rawOb": "METAR SAAR ... VRB04G20KT -RA 22/11 Q1013",
    }]


async def test_dashboard_uses_a_fresh_nearby_metar(async_client: AsyncClient):
    model_time = _model_time()
    obs_time = model_time - timedelta(minutes=10)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(AWC_METAR_URL).mock(return_value=httpx.Response(200, json=_metar(obs_time)))
        response = await _get_dashboard(async_client, *ROSARIO, model_time)

    assert response.status_code == 200
    current = response.json()["current"]
    assert current["source"] == "metar"
    assert current["source_reason"] == "metar_ok"
    assert current["temp_c"] == 22.0
    assert current["humidity"] == 50.0
    assert current["wind_speed_kmh"] == pytest.approx(7.4)
    assert current["wind_gust_kmh"] == pytest.approx(37.0)
    assert current["wind_dir_deg"] is None
    assert current["wind_dir_cardinal"] is None
    assert current["model_temp_c"] == 15.0
    assert current["station"]["icao"] == "SAAR"
    assert current["station"]["name"] == "Rosario"
    assert datetime.fromisoformat(current["observed_at"]) == obs_time
    codes = [n["code"] for n in current["notices"]]
    assert codes == ["model_temp_differs", "reported_phenomenon"]
    assert current["notices"][1] == {"code": "reported_phenomenon", "kind": "rain", "wx": "-RA"}


async def test_dashboard_far_from_airports_uses_the_model_with_its_real_time(
    async_client: AsyncClient,
):
    model_time = _model_time()
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(AWC_METAR_URL).mock(return_value=httpx.Response(200, json=[]))
        response = await _get_dashboard(async_client, *SANTIAGO_DEL_ESTERO, model_time)

    assert response.status_code == 200
    current = response.json()["current"]
    assert current["source"] == "openmeteo"
    assert current["source_reason"] == "metar_too_far"
    assert datetime.fromisoformat(current["observed_at"]) == model_time
    assert current["wind_gust_kmh"] == 24.0
    assert current["station"] is None
    assert current["model_temp_c"] is None
    assert current["notices"] == []
    assert route.call_count == 0


async def test_dashboard_between_20_and_30_km_from_an_airport_no_longer_gets_a_metar(
    async_client: AsyncClient,
):
    model_time = _model_time()
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(AWC_METAR_URL).mock(
            return_value=httpx.Response(200, json=_metar(model_time - timedelta(minutes=10)))
        )
        response = await _get_dashboard(async_client, *QUILMES, model_time)

    assert response.status_code == 200
    current = response.json()["current"]
    assert current["source"] == "openmeteo"
    assert current["source_reason"] == "metar_too_far"
    assert current["station"] is None
    assert route.call_count == 0


async def test_dashboard_with_awc_down_still_answers(async_client: AsyncClient):
    model_time = _model_time()
    with respx.mock(assert_all_called=False) as mock:
        mock.get(AWC_METAR_URL).mock(side_effect=httpx.ConnectError("down"))
        response = await _get_dashboard(async_client, *ROSARIO, model_time)

    assert response.status_code == 200
    current = response.json()["current"]
    assert current["source"] == "openmeteo"
    assert current["source_reason"] == "metar_unavailable"
    assert current["temp_c"] == 15.0


async def test_dashboard_survives_an_unexpected_metar_error(async_client: AsyncClient):
    with patch("app.routers.weather.get_nearest_metar_observation", new_callable=AsyncMock,
               side_effect=RuntimeError("boom")):
        response = await _get_dashboard(async_client, *ROSARIO, _model_time())

    assert response.status_code == 200
    assert response.json()["current"]["source"] == "openmeteo"
    assert response.json()["current"]["source_reason"] == "metar_unavailable"


async def test_dashboard_survives_a_blend_error(async_client: AsyncClient):
    model_time = _model_time()
    with (
        respx.mock(assert_all_called=False) as mock,
        patch("app.routers.weather.blend_current", side_effect=ValueError("bad")),
    ):
        mock.get(AWC_METAR_URL).mock(return_value=httpx.Response(200, json=_metar(model_time)))
        response = await _get_dashboard(async_client, *ROSARIO, model_time)

    assert response.status_code == 200
    current = response.json()["current"]
    assert current["source"] == "openmeteo"
    assert current["temp_c"] == 15.0
