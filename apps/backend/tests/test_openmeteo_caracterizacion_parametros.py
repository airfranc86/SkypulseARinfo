"""Characterization (phase 2a): the exact query every Open-Meteo request of the backend sends.

Pins what goes over the wire today so a later refactor (one module behind all the requests) cannot change a
timezone, a field list, a default horizon, a unit or a model by accident. Production code is not touched: every
assertion here passes against the current code. The ECMWF hourly request is pinned in
`test_openmeteo_hourly_ecmwf.py` field by field; here it only gets the same whole-query equality as the others.

The variable lists (`current`, `daily`, `hourly`) are compared as sets of names, not as ordered strings: the order
Open-Meteo is asked in is not behavior. The exact string is pinned once, through the cache key, in
`test_openmeteo_caracterizacion_cache.py`.
"""
from __future__ import annotations

import httpx
import pytest
import respx

import app.services.openmeteo as om_module
from app.services.openmeteo import (
    get_current,
    get_daily_forecast_ext,
    get_fog_inference_forecast,
    get_hourly_forecast_ecmwf,
    get_hourly_forecast_ext,
    get_multi_model_daily,
    get_visibility_forecast,
)
from tests._om_payloads import _CURRENT_PAYLOAD, _DAILY_EXT_PAYLOAD, OM_URL

LAT, LON = -31.4, -64.2
TZ = "America/Argentina/Buenos_Aires"


def _names(csv: str) -> frozenset[str]:
    return frozenset(csv.split(","))


_CURRENT_FIELDS = _names(
    "temperature_2m,relative_humidity_2m,apparent_temperature,surface_pressure,wind_speed_10m,"
    "wind_direction_10m,wind_gusts_10m,precipitation,cloud_cover,weather_code"
)
_DAILY_FIELDS = _names(
    "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,"
    "wind_speed_10m_max,wind_gusts_10m_max,wind_direction_10m_dominant,relative_humidity_2m_mean,"
    "uv_index_max,weather_code,sunrise,sunset,daylight_duration,cloud_cover_mean"
)
_HOURLY_FIELDS = _names(
    "temperature_2m,precipitation,precipitation_probability,wind_speed_10m,weather_code,is_day,"
    "freezing_level_height,wind_gusts_10m,cape,temperature_850hPa,relative_humidity_2m,cloud_cover,"
    "wind_direction_10m"
)
_NIEBLA_HOURLY_FIELDS = _names(
    "visibility,relative_humidity_2m,dew_point_2m,temperature_2m,wind_speed_10m,weather_code"
)
_ECMWF_HOURLY_FIELDS = _names("precipitation,wind_gusts_10m,wind_speed_10m,wind_direction_10m,weather_code,cape")

_HOURLY_PAYLOAD = {
    "elevation": 25.0,
    "hourly": {"time": [f"2026-10-08T{h:02d}:00" for h in range(24)], "temperature_2m": [20.0] * 24},
}
_NIEBLA_PAYLOAD = {
    "current": {"time": "2026-10-08T12:00", "visibility": 9000.0, "weather_code": 2},
    "hourly": {
        "time": [f"2026-10-08T{h:02d}:00" for h in range(24)] + [f"2026-10-09T{h:02d}:00" for h in range(24)],
        "visibility": [9000.0] * 48,
        "relative_humidity_2m": [80.0] * 48,
        "dew_point_2m": [15.0] * 48,
        "temperature_2m": [20.0] * 48,
        "wind_speed_10m": [3.0] * 48,
        "weather_code": [0] * 48,
    },
}


@pytest.fixture
def om():
    """The Open-Meteo route; each test sets its answer."""
    with respx.mock(assert_all_called=False) as router:
        yield router.get(OM_URL)


_VARIABLE_LISTS = ("current", "daily", "hourly")


def _query(route, index: int = -1) -> dict[str, object]:
    """The query of one request the route received, as a dict; the variable lists become sets of names."""
    raw = dict(route.calls[index].request.url.params)
    return {k: (_names(v) if k in _VARIABLE_LISTS else v) for k, v in raw.items()}


# ---------------------------------------------------------------------------
# get_current
# ---------------------------------------------------------------------------

async def test_current_asks_the_full_field_list_in_kmh_and_argentine_time_without_a_model(om) -> None:
    om.mock(return_value=httpx.Response(200, json=_CURRENT_PAYLOAD))
    assert await get_current(LAT, LON) is not None
    assert om.call_count == 1
    assert _query(om) == {
        "latitude": "-31.4",
        "longitude": "-64.2",
        "current": _CURRENT_FIELDS,
        "timezone": TZ,
        "wind_speed_unit": "kmh",
    }


# ---------------------------------------------------------------------------
# Daily, single model
# ---------------------------------------------------------------------------

async def test_daily_defaults_to_seven_days_and_sends_no_model(om) -> None:
    om.mock(return_value=httpx.Response(200, json=_DAILY_EXT_PAYLOAD))
    assert await get_daily_forecast_ext(LAT, LON) is not None
    assert om.call_count == 1
    assert _query(om) == {
        "latitude": "-31.4",
        "longitude": "-64.2",
        "daily": _DAILY_FIELDS,
        "forecast_days": "7",
        "timezone": TZ,
        "wind_speed_unit": "kmh",
    }


async def test_daily_sends_the_model_and_the_days_only_when_asked(om) -> None:
    om.mock(return_value=httpx.Response(200, json=_DAILY_EXT_PAYLOAD))
    assert await get_daily_forecast_ext(LAT, LON, days=5, model="gfs_seamless") is not None
    assert _query(om) == {
        "latitude": "-31.4",
        "longitude": "-64.2",
        "daily": _DAILY_FIELDS,
        "forecast_days": "5",
        "timezone": TZ,
        "wind_speed_unit": "kmh",
        "models": "gfs_seamless",
    }


# ---------------------------------------------------------------------------
# Daily, multi model
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(("kwargs", "days"), [({}, "7"), ({"days": 4}, "4")], ids=["default", "passthrough"])
async def test_multi_model_sends_one_daily_request_per_model_with_the_same_horizon(om, kwargs, days) -> None:
    om.mock(return_value=httpx.Response(200, json=_DAILY_EXT_PAYLOAD))
    assert await get_multi_model_daily(LAT, LON, **kwargs) is not None
    assert om.call_count == 2
    queries = [_query(om, i) for i in range(2)]
    assert {q["models"] for q in queries} == {"gfs_seamless", "ecmwf_ifs025"}
    for query in queries:
        assert query == {
            "latitude": "-31.4",
            "longitude": "-64.2",
            "daily": _DAILY_FIELDS,
            "forecast_days": days,
            "timezone": TZ,
            "wind_speed_unit": "kmh",
            "models": query["models"],
        }


# ---------------------------------------------------------------------------
# Hourly, best_match
# ---------------------------------------------------------------------------

async def test_hourly_best_match_defaults_to_two_days_and_sends_no_model(om) -> None:
    om.mock(return_value=httpx.Response(200, json=_HOURLY_PAYLOAD))
    assert await get_hourly_forecast_ext(LAT, LON) is not None
    assert om.call_count == 1
    assert _query(om) == {
        "latitude": "-31.4",
        "longitude": "-64.2",
        "hourly": _HOURLY_FIELDS,
        "forecast_days": "2",
        "timezone": TZ,
        "wind_speed_unit": "kmh",
    }


async def test_hourly_best_match_passes_the_days_through(om) -> None:
    om.mock(return_value=httpx.Response(200, json=_HOURLY_PAYLOAD))
    assert await get_hourly_forecast_ext(LAT, LON, days=3) is not None
    assert _query(om)["forecast_days"] == "3"


# ---------------------------------------------------------------------------
# Hourly, ECMWF (field by field in test_openmeteo_hourly_ecmwf.py; here the whole query)
# ---------------------------------------------------------------------------

async def test_hourly_ecmwf_query_is_exactly_this_with_seven_days_by_default(om) -> None:
    om.mock(return_value=httpx.Response(200, json=_HOURLY_PAYLOAD))
    assert await get_hourly_forecast_ecmwf(LAT, LON) is not None
    assert om.call_count == 1
    assert _query(om) == {
        "latitude": "-31.4",
        "longitude": "-64.2",
        "hourly": _ECMWF_HOURLY_FIELDS,
        "models": "ecmwf_ifs025",
        "forecast_days": "7",
        "timezone": TZ,
        "wind_speed_unit": "kmh",
    }


# ---------------------------------------------------------------------------
# Niebla (visibility + fog inference share one request)
# ---------------------------------------------------------------------------

@pytest.fixture
def argentine_noon(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fix the local clock inside the payload's first day so both niebla readers have hours to show."""
    from datetime import datetime

    monkeypatch.setattr(om_module, "_ar_now", lambda: datetime(2026, 10, 8, 12, 30, tzinfo=om_module._AR_TZ))


_NIEBLA_QUERY = {
    "latitude": "-31.4",
    "longitude": "-64.2",
    "current": _names("visibility,weather_code"),
    "hourly": _NIEBLA_HOURLY_FIELDS,
    "timezone": TZ,
    "forecast_days": "2",
}


async def test_niebla_sends_current_and_hourly_for_two_days_without_unit_or_model(om, argentine_noon) -> None:
    om.mock(return_value=httpx.Response(200, json=_NIEBLA_PAYLOAD))
    assert await get_visibility_forecast(LAT, LON) is not None
    assert om.call_count == 1
    assert _query(om) == _NIEBLA_QUERY


@pytest.mark.parametrize("fog_first", [False, True], ids=["visibility-first", "fog-first"])
async def test_visibility_and_fog_inference_share_one_request(om, argentine_noon, fog_first) -> None:
    om.mock(return_value=httpx.Response(200, json=_NIEBLA_PAYLOAD))
    calls = [get_visibility_forecast, get_fog_inference_forecast]
    for call in reversed(calls) if fog_first else calls:
        assert await call(LAT, LON) is not None
    assert om.call_count == 1
    assert _query(om) == _NIEBLA_QUERY
