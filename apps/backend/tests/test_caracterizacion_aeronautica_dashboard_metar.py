"""Characterization of the METAR block of GET /api/weather/dashboard (the "now" in `current`).

AWC is mocked with respx; the rest of the dashboard is patched like test_dashboard_current_observation
does. The clock of the router and of `app.services.metar_observation` is frozen, so the METAR ages, the
`possible_change` notice and every `observed_at` are deterministic. Only the fields that come from (or
depend on) the METAR are compared, as literal JSON. No cache TTLs, lookback windows, timeouts or number
of AWC requests are pinned.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from httpx import AsyncClient

from app.schemas.weather import SourceMeta, WeatherCurrentResponse
from app.services.metar_observation import AWC_METAR_URL
from app.services.openmeteo import OpenMeteoCurrent
from tests.helpers_caracterizacion_aeronautica import (
    FROZEN_NOW,
    awc_metar,
    freeze_clock,
    minutes_before,
    reset_aeronautical_state,
)
from tests.hourly_fixtures import AR, make_hourly
from tests.test_dashboard_integration import _daily_ext, _multi_model

pytestmark = [pytest.mark.integration, pytest.mark.live_current_observation]

ROSARIO = (-32.95, -60.65)               # SAAR, 13.1 km
SANTIAGO_DEL_ESTERO = (-27.78, -64.27)   # no airport within 20 km (SANT is ~100 km away)
QUILMES = (-34.72, -58.25)               # SABE, 23.5 km

MODEL_TIME = FROZEN_NOW - timedelta(minutes=5)

# `current` fields that come from the METAR or are replaced by it.
METAR_FIELDS = (
    "temp_c", "feels_like_c", "humidity", "wind_speed_kmh", "wind_dir_deg", "wind_dir_cardinal",
    "wind_gust_kmh", "wind_intensity", "source", "source_reason", "observed_at", "station",
    "model_temp_c", "notices",
)
STATION_SAAR = {"icao": "SAAR", "name": "Rosario", "distance_km": 13.1}

# `current` when the METAR is not used: the Open-Meteo model of the fixtures below, with its own time.
MODEL_CURRENT = {
    "temp_c": 15.0,
    "feels_like_c": 14.0,
    "humidity": 70.0,
    "wind_speed_kmh": 12.0,
    "wind_dir_deg": 180.0,
    "wind_dir_cardinal": "S",
    "wind_gust_kmh": 24.0,
    "wind_intensity": "leve",
    "source": "openmeteo",
    "observed_at": "2026-10-08T14:55:00Z",
    "station": None,
    "model_temp_c": None,
    "notices": [],
}

REPORT = {"temp": 18, "dewp": 12, "wdir": 270, "wspd": 10, "wgst": 18, "wxString": "-RA"}


@pytest.fixture(autouse=True)
def _state(monkeypatch):
    reset_aeronautical_state()
    freeze_clock(monkeypatch, FROZEN_NOW, "app.routers.weather", "app.services.metar_observation")
    yield
    reset_aeronautical_state()


def _model_current(lat: float, lon: float, weather_code: int) -> WeatherCurrentResponse:
    meta = SourceMeta(source="openmeteo", reason="smn_disabled", fetched_at=FROZEN_NOW, observed_at=MODEL_TIME)
    return WeatherCurrentResponse(
        lat=lat, lon=lon, temp_c=15.0, feels_like_c=14.0, humidity=70.0,
        wind_speed_kmh=12.0, wind_dir_deg=180.0, wind_dir_cardinal="S",
        pressure_hpa=1010.0, precip_1h_mm=0.0, cloud_cover=20.0,
        description=None, weather_code=weather_code, meta=meta,
    )


def _om_current() -> OpenMeteoCurrent:
    return OpenMeteoCurrent(
        temp_c=15.0, feels_like_c=14.0, humidity=70.0, wind_speed_kmh=12.0, wind_dir_deg=180.0,
        pressure_hpa=1010.0, precip_1h_mm=0.0, cloud_cover=20.0, weather_code=1,
        description=None, fetched_at=FROZEN_NOW, observed_at=MODEL_TIME, wind_gust_kmh=24.0,
    )


async def get_current(
    client: AsyncClient,
    location: tuple[float, float],
    awc: httpx.Response | Exception,
    *,
    weather_code: int = 1,
    rain_mm_by_hour: dict[int, float] | None = None,
) -> dict:
    """The METAR-related fields of `current` from GET /api/weather/dashboard, with AWC mocked."""
    # Hourly series of 2026-10-08 (AR): the frozen 12:00 local falls in the hour that closes at index 13.
    hourly = make_hourly(48, start=datetime(2026, 10, 8, tzinfo=AR), precipitations=rain_mm_by_hour or {})
    daily = _daily_ext()
    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_METAR_URL)
        if isinstance(awc, Exception):
            route.mock(side_effect=awc)
        else:
            route.mock(return_value=awc)
        with (
            patch("app.routers.weather.aggregate_current", new_callable=AsyncMock,
                  return_value=_model_current(*location, weather_code)),
            patch("app.routers.weather.get_openmeteo_current", new_callable=AsyncMock, return_value=_om_current()),
            patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock,
                  return_value=_multi_model(daily)),
            patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=hourly),
        ):
            response = await client.get(f"/api/weather/dashboard?lat={location[0]}&lon={location[1]}")

    assert response.status_code == 200
    current = response.json()["current"]
    return {field: current[field] for field in METAR_FIELDS}


def metar(minutes_old: float, icao: str = "SAAR", **fields: object) -> httpx.Response:
    return httpx.Response(200, json=awc_metar(minutes_before(FROZEN_NOW, minutes_old), icao, **fields))


def model_with_reason(reason: str) -> dict:
    return MODEL_CURRENT | {"source_reason": reason}


# ---------------------------------------------------------------------------
# metar_ok
# ---------------------------------------------------------------------------

async def test_fresh_nearby_metar_replaces_the_model(async_client: AsyncClient) -> None:
    current = await get_current(async_client, ROSARIO, metar(10, **REPORT))

    assert current == {
        "temp_c": 18.0,
        "feels_like_c": 18.0,
        "humidity": 68.0,
        "wind_speed_kmh": 18.5,
        "wind_dir_deg": 270.0,
        "wind_dir_cardinal": "W",
        "wind_gust_kmh": 33.3,
        "wind_intensity": "leve",
        "source": "metar",
        "source_reason": "metar_ok",
        "observed_at": "2026-10-08T14:50:00Z",
        "station": STATION_SAAR,
        "model_temp_c": 15.0,
        "notices": [{"code": "reported_phenomenon", "kind": "rain", "wx": "-RA"}],
    }


async def test_metar_exactly_90_minutes_old_is_still_used(async_client: AsyncClient) -> None:
    current = await get_current(async_client, ROSARIO, metar(90, **REPORT))

    assert current["source"] == "metar"
    assert current["source_reason"] == "metar_ok"
    assert current["observed_at"] == "2026-10-08T13:30:00Z"
    assert current["temp_c"] == 18.0


async def test_the_latest_report_by_obs_time_wins_whatever_the_order(async_client: AsyncClient) -> None:
    reports = (
        awc_metar(minutes_before(FROZEN_NOW, 70), "SAAR", temp=1, dewp=0, wspd=1)
        + awc_metar(minutes_before(FROZEN_NOW, 20), "SAAR", temp=19, dewp=13, wspd=5, wdir=350)
        + awc_metar(minutes_before(FROZEN_NOW, 50), "SAAR", temp=3, dewp=2)
    )

    current = await get_current(async_client, ROSARIO, httpx.Response(200, json=reports))

    assert current == {
        "temp_c": 19.0,
        "feels_like_c": 19.0,
        "humidity": 68.0,
        "wind_speed_kmh": 9.3,
        "wind_dir_deg": 350.0,
        "wind_dir_cardinal": "N",
        "wind_gust_kmh": None,
        "wind_intensity": "leve",
        "source": "metar",
        "source_reason": "metar_ok",
        "observed_at": "2026-10-08T14:40:00Z",
        "station": STATION_SAAR,
        "model_temp_c": 15.0,
        "notices": [],
    }


async def test_calm_wind_has_no_direction_and_old_report_warns_about_wind_and_temperature(
    async_client: AsyncClient,
) -> None:
    current = await get_current(async_client, ROSARIO, metar(45, temp=22, dewp=21, wdir=0, wspd=0))

    assert current == {
        "temp_c": 22.0,
        "feels_like_c": 22.0,
        "humidity": 94.0,
        "wind_speed_kmh": 0.0,
        "wind_dir_deg": None,
        "wind_dir_cardinal": None,
        "wind_gust_kmh": None,
        "wind_intensity": "leve",
        "source": "metar",
        "source_reason": "metar_ok",
        "observed_at": "2026-10-08T14:15:00Z",
        "station": STATION_SAAR,
        "model_temp_c": 15.0,
        "notices": [
            {"code": "model_temp_differs", "model_temp_c": 15.0},
            {
                "code": "possible_change",
                "reasons": ["wind"],
                "model_wind_speed_kmh": 12.0,
                "model_wind_gust_kmh": 24.0,
                "model_precip_1h_mm": 0.0,
                "model_weather_code": 1,
            },
        ],
    }


async def test_old_report_with_a_reported_storm_keeps_both_notices(async_client: AsyncClient) -> None:
    current = await get_current(
        async_client, ROSARIO, metar(45, temp=14, dewp=10, wdir=90, wspd=2, wxString="TSRA")
    )

    assert current["notices"] == [
        {
            "code": "possible_change",
            "reasons": ["wind"],
            "model_wind_speed_kmh": 12.0,
            "model_wind_gust_kmh": 24.0,
            "model_precip_1h_mm": 0.0,
            "model_weather_code": 1,
        },
        {"code": "reported_phenomenon", "kind": "storm", "wx": "TSRA"},
    ]
    assert (current["temp_c"], current["humidity"], current["wind_speed_kmh"]) == (14.0, 77.0, 3.7)
    assert (current["wind_dir_deg"], current["wind_dir_cardinal"]) == (90.0, "E")


async def test_old_report_without_rain_or_storm_while_the_model_has_both(async_client: AsyncClient) -> None:
    current = await get_current(
        async_client, ROSARIO, metar(45, temp=15, dewp=10, wdir=200, wspd=20),
        weather_code=95, rain_mm_by_hour={13: 2.0},
    )

    assert current["wind_speed_kmh"] == 37.0
    assert current["wind_intensity"] == "moderada"
    assert current["notices"] == [
        {
            "code": "possible_change",
            "reasons": ["rain", "storm"],
            "model_wind_speed_kmh": 12.0,
            "model_wind_gust_kmh": 24.0,
            "model_precip_1h_mm": 2.0,
            "model_weather_code": 95,
        },
    ]


# ---------------------------------------------------------------------------
# Not used: the model answers, with the reason
# ---------------------------------------------------------------------------

async def test_metar_older_than_90_minutes_is_metar_stale(async_client: AsyncClient) -> None:
    current = await get_current(async_client, ROSARIO, metar(91, **REPORT))

    assert current == model_with_reason("metar_stale")


async def test_airport_beyond_20_km_is_metar_too_far(async_client: AsyncClient) -> None:
    current = await get_current(async_client, QUILMES, metar(10, "SABE", **REPORT))

    assert current == model_with_reason("metar_too_far")


async def test_no_airport_nearby_is_metar_too_far(async_client: AsyncClient) -> None:
    current = await get_current(async_client, SANTIAGO_DEL_ESTERO, metar(10, "SANT", **REPORT))

    assert current == model_with_reason("metar_too_far")


@pytest.mark.parametrize(
    "awc",
    [
        httpx.Response(200, json=[]),
        httpx.Response(200, json=[{"icaoId": "SAAR", "temp": 18, "dewp": 12}]),
        httpx.Response(500, text="boom"),
        httpx.Response(200, text="not json"),
        httpx.ConnectError("down"),
        httpx.ReadTimeout("slow"),
    ],
    ids=["empty", "no-obs-time", "http-500", "invalid-json", "connect-error", "timeout"],
)
async def test_no_usable_report_is_metar_unavailable(async_client: AsyncClient, awc) -> None:
    current = await get_current(async_client, ROSARIO, awc)

    assert current == model_with_reason("metar_unavailable")


@pytest.mark.parametrize("fields", [{"temp": 18, "wspd": 3}, {"dewp": 12, "wspd": 3}, {"wspd": 3}])
async def test_report_without_temperature_or_dewpoint_is_metar_missing_fields(
    async_client: AsyncClient, fields: dict
) -> None:
    current = await get_current(async_client, ROSARIO, metar(10, **fields))

    assert current == model_with_reason("metar_missing_fields")
