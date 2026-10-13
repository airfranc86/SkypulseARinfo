"""Phase 2b/2c: the one module that sends requests to Open-Meteo (`services/openmeteo_source.py`).

Covers the request description (`SeriesRequest.params()`), `fetch_series` (cache level and key, persistence, the
outcome, single flight, refusals, parse errors), `bind_caches`, the swappable source (`get_source`/`set_source`
with the `FakeOpenMeteoSource` of `tests/openmeteo_fake_source.py`) and the requests of the backend's public fetchers
that go through it.

The real `HttpOpenMeteoSource` (pause, budget, counter, retry) is in `test_openmeteo_source_http.py` and the values
derived from other requests (`fetch_derived`) in `test_openmeteo_derived.py`. The 429 pause, the call budget and the
counter are also pinned end to end, through every public function, in `test_openmeteo_429_pause.py`,
`test_openmeteo_budget.py` and `test_openmeteo_caracterizacion_*`.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

import app.services.openmeteo as om_module
import app.services.openmeteo_source as source_module
from app.core.cache import CacheOutcome, FetchRefused, SingleFlightCache
from app.services.openmeteo_source import (
    CacheLevel,
    CacheNotBoundError,
    HttpOpenMeteoSource,
    SeriesRequest,
    bind_caches,
    cache_key,
    fetch_series,
    fetch_series_or_raise,
    get_source,
    set_source,
)
from tests._om_payloads import _CURRENT_PAYLOAD, _DAILY_EXT_PAYLOAD, _FOG_PAYLOAD, _VISIBILITY_PAYLOAD
from tests.openmeteo_fake_source import (  # noqa: F401  (fixtures are used by name)
    LAT,
    LON,
    TZ,
    FakeOpenMeteoSource,
    SourceCall,
    clock,
    install,
    own_caches,
)
from tests.openmeteo_fake_source import parse_value as _parse_value
from tests.openmeteo_fake_source import series_key as _key
from tests.openmeteo_fake_source import series_request as _request

BACKEND_DIR = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# SeriesRequest.params(): the query that goes over the wire
# ---------------------------------------------------------------------------

_CURRENT_CSV = (
    "temperature_2m,relative_humidity_2m,apparent_temperature,surface_pressure,wind_speed_10m,"
    "wind_direction_10m,wind_gusts_10m,precipitation,cloud_cover,weather_code"
)
_NIEBLA_HOURLY_CSV = "visibility,relative_humidity_2m,dew_point_2m,temperature_2m,wind_speed_10m,weather_code"


def test_the_current_request_carries_exactly_these_params() -> None:
    assert om_module._current_request(LAT, LON).params() == {
        "latitude": LAT,
        "longitude": LON,
        "current": _CURRENT_CSV,
        "timezone": TZ,
        "wind_speed_unit": "kmh",
    }


def test_the_niebla_request_carries_exactly_these_params() -> None:
    assert om_module._niebla_request(LAT, LON).params() == {
        "latitude": LAT,
        "longitude": LON,
        "current": "visibility,weather_code",
        "hourly": _NIEBLA_HOURLY_CSV,
        "timezone": TZ,
        "forecast_days": 2,
    }


def test_the_levels_of_the_two_migrated_requests() -> None:
    assert om_module._current_request(LAT, LON).level is CacheLevel.CURRENT
    assert om_module._niebla_request(LAT, LON).level is CacheLevel.NOWCAST
    assert om_module._current_request(LAT, LON).persist is True
    assert om_module._niebla_request(LAT, LON).persist is True


def test_params_has_every_field_the_request_carries() -> None:
    request = SeriesRequest(
        lat=LAT, lon=LON, level=CacheLevel.FORECAST,
        current=("a", "b"), hourly=("c",), daily=("d", "e", "f"),
        models="gfs_seamless", forecast_days=5, wind_speed_unit_kmh=True,
    )
    assert request.params() == {
        "latitude": LAT, "longitude": LON,
        "current": "a,b", "hourly": "c", "daily": "d,e,f",
        "models": "gfs_seamless", "forecast_days": 5,
        "timezone": TZ, "wind_speed_unit": "kmh",
    }


def test_optional_parts_are_left_out_and_never_sent_empty() -> None:
    request = SeriesRequest(lat=LAT, lon=LON, level=CacheLevel.CURRENT, hourly=("c",))
    assert request.params() == {"latitude": LAT, "longitude": LON, "hourly": "c", "timezone": TZ}


@pytest.mark.parametrize(("flag", "expected"), [(True, {"wind_speed_unit": "kmh"}), (False, {})])
def test_the_wind_unit_is_sent_only_when_asked(flag: bool, expected: dict) -> None:
    params = _request(wind_speed_unit_kmh=flag).params()
    assert {k: v for k, v in params.items() if k == "wind_speed_unit"} == expected


def test_the_wire_keeps_the_exact_coordinates() -> None:
    params = _request(lat=-31.4049, lon=-64.2051).params()
    assert (params["latitude"], params["longitude"]) == (-31.4049, -64.2051)


def test_params_returns_a_new_dict_each_time_and_the_request_is_frozen() -> None:
    request = _request()
    first = request.params()
    first["latitude"] = 0.0
    assert request.params()["latitude"] == LAT
    with pytest.raises(dataclasses.FrozenInstanceError):
        request.lat = 1.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# fetch_series: cache level, key, TTL, persistence, outcome
# ---------------------------------------------------------------------------

async def test_a_request_is_fetched_once_and_then_served_from_its_cache(install) -> None:
    fake = install({"value": 1})
    first = await fetch_series(_request(), _parse_value)
    second = await fetch_series(_request(), _parse_value)
    assert first == second == {"value": 1}
    assert len(fake.calls) == 1


async def test_the_key_is_rounded_but_the_request_carries_the_exact_coordinates(install) -> None:
    fake = install({"value": 1})
    assert await fetch_series(_request(lat=-31.401, lon=-64.201), _parse_value) is not None
    assert await fetch_series(_request(lat=-31.404, lon=-64.204), _parse_value) is not None
    assert len(fake.calls) == 1                                           # same two-decimal cell
    assert (fake.calls[0].params["latitude"], fake.calls[0].params["longitude"]) == (-31.401, -64.201)
    assert list(om_module._CACHE_CURRENT._cache.keys()) == [_key(_request(lat=-31.4, lon=-64.2))]

    assert await fetch_series(_request(lat=-31.41), _parse_value) is not None
    assert len(fake.calls) == 2                                           # 0.01 degrees away is another cell


@pytest.mark.parametrize(
    ("level", "cache_name", "ttl"),
    [
        (CacheLevel.CURRENT, "_CACHE_CURRENT", 600),
        (CacheLevel.FORECAST, "_CACHE_FORECAST", 1800),
        (CacheLevel.NOWCAST, "_CACHE_NOWCAST", 900),
    ],
)
async def test_each_level_uses_its_own_cache_and_ttl(level, cache_name, ttl, install, clock) -> None:
    fake = install({"value": 1})
    request = _request(level)
    assert await fetch_series(request, _parse_value) is not None
    holders = [n for n in ("_CACHE_CURRENT", "_CACHE_FORECAST", "_CACHE_NOWCAST") if list(getattr(om_module, n)._cache)]
    assert holders == [cache_name]

    clock.advance(ttl - 1)
    assert await fetch_series(request, _parse_value) is not None
    assert len(fake.calls) == 1                                           # still fresh one second before the ttl
    clock.advance(2)
    assert await fetch_series(request, _parse_value) is not None
    assert len(fake.calls) == 2                                           # expired one second after it


async def test_the_level_picks_the_bound_cache(install, own_caches) -> None:
    install({"value": 1})
    request = _request(CacheLevel.NOWCAST)
    assert await fetch_series(request, _parse_value) is not None
    held = {level: list(cache._cache) for level, cache in own_caches.caches.items()}
    assert held == {CacheLevel.CURRENT: [], CacheLevel.FORECAST: [], CacheLevel.NOWCAST: [_key(request)]}


async def test_persist_true_hands_the_good_copy_to_the_backend_and_false_does_not(install, own_caches) -> None:
    install({"value": 1})
    kept, skipped = _request(lat=-10.0), _request(lat=-20.0, persist=False)
    assert await fetch_series(kept, _parse_value) is not None
    assert await fetch_series(skipped, _parse_value) is not None
    await own_caches.caches[CacheLevel.CURRENT].flush_persistence()
    assert own_caches.backend.saved == [_key(kept)]


async def test_persist_false_does_not_read_the_backend_when_the_fetch_fails(install, own_caches) -> None:
    install(None)
    assert await fetch_series(_request(lat=-10.0, persist=False), _parse_value) is None
    assert own_caches.backend.loaded == []
    assert await fetch_series(_request(lat=-20.0, persist=True), _parse_value) is None
    assert own_caches.backend.loaded == [_key(_request(lat=-20.0))]


async def test_the_outcome_says_whether_the_value_came_from_the_cache(install) -> None:
    install({"value": 1})
    first, second = CacheOutcome(), CacheOutcome()
    await fetch_series(_request(), _parse_value, outcome=first)
    await fetch_series(_request(), _parse_value, outcome=second)
    assert (first.hit, second.hit) == (False, True)


async def test_a_stale_copy_is_served_when_the_source_fails_after_the_ttl(install, clock) -> None:
    fake = install({"value": 1}, None)
    request = _request()
    assert await fetch_series(request, _parse_value) == {"value": 1}
    clock.advance(601)
    outcome = CacheOutcome()
    assert await fetch_series(request, _parse_value, outcome=outcome) == {"value": 1}
    assert len(fake.calls) == 2
    assert outcome.hit is True


async def test_concurrent_identical_calls_share_one_request(install) -> None:
    fake = install({"value": 1}, delay=0.02)
    results = await asyncio.gather(*(fetch_series(_request(), _parse_value) for _ in range(6)))
    assert results == [{"value": 1}] * 6
    assert len(fake.calls) == 1


async def test_a_failed_call_is_none_and_remembered_for_the_failure_window(install) -> None:
    fake = install(None)
    assert await fetch_series(_request(), _parse_value) is None
    assert await fetch_series(_request(), _parse_value) is None
    assert len(fake.calls) == 1


async def test_the_failure_message_goes_to_the_source(install) -> None:
    fake = install({"value": 1})
    await fetch_series(_request(lat=1.0), _parse_value)
    await fetch_series(_request(lat=2.0), _parse_value, failure_message="custom %s")
    assert [c.failure_message for c in fake.calls] == ["Open-Meteo fetch failed: %s", "custom %s"]
    assert all(c.log_args == () for c in fake.calls)


# ---------------------------------------------------------------------------
# fetch_series: a refusal is not a failure
# ---------------------------------------------------------------------------

async def test_a_refusal_is_none_for_that_call_only_and_is_not_remembered(install) -> None:
    fake = install(FetchRefused("budget"), {"value": 1})
    assert await fetch_series(_request(), _parse_value) is None
    assert await fetch_series(_request(), _parse_value) == {"value": 1}      # nothing was negative-cached
    assert len(fake.calls) == 2


async def test_a_refusal_serves_the_stale_copy_when_there_is_one(install, clock) -> None:
    install({"value": 1}, FetchRefused("budget"))
    await fetch_series(_request(), _parse_value)
    clock.advance(601)
    outcome = CacheOutcome()
    assert await fetch_series(_request(), _parse_value, outcome=outcome) == {"value": 1}
    assert outcome.hit is True


# ---------------------------------------------------------------------------
# fetch_series: parse errors
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "error",
    [KeyError("k"), TypeError("t"), ValueError("v"), AttributeError("a"), OverflowError("o")],
    ids=lambda e: type(e).__name__,
)
async def test_every_parse_error_is_none_with_the_same_log_message(error, install, caplog) -> None:
    fake = install({"value": 1})

    def parse(payload: dict) -> dict:
        raise error

    with caplog.at_level(logging.WARNING):
        assert await fetch_series(_request(), parse) is None
        assert await fetch_series(_request(), parse) is None                  # remembered as a failure
    assert len(fake.calls) == 1
    records = [r for r in caplog.records if r.name == source_module.logger.name]
    assert [r.getMessage() for r in records] == [
        f"Open-Meteo payload parse error: {error} [{type(error).__name__}]"
    ]
    assert records[0].exc_info is not None and records[0].exc_info[0] is type(error)


async def test_the_parse_error_message_can_be_replaced(install, caplog) -> None:
    install({"value": 1})
    with caplog.at_level(logging.WARNING):
        assert await fetch_series(_request(), lambda p: p["nope"], parse_error_message="mine: %s") is None
    assert [r.getMessage() for r in caplog.records] == ["mine: 'nope' [KeyError]"]


async def test_an_unexpected_error_of_the_parser_is_not_swallowed(install) -> None:
    install({"value": 1})

    def parse(payload: dict) -> dict:
        raise RuntimeError("a bug")

    with pytest.raises(RuntimeError, match="a bug"):
        await fetch_series(_request(), parse)


@pytest.mark.parametrize(
    "payload",
    [{"current": 5}, {"current": {"weather_code": "abc"}}, {"current": {"weather_code": 1e999}}, {}, [], {"current": None}],
    ids=[
        "current-not-an-object", "weather-code-not-a-number", "weather-code-overflow", "no-current",
        "payload-is-a-list", "current-null",
    ],
)
async def test_get_current_with_a_malformed_payload_is_none_and_never_raises(payload, install, caplog) -> None:
    fake = install(payload)
    with caplog.at_level(logging.WARNING):
        assert await om_module.get_current(LAT, LON) is None
        assert await om_module.get_current(LAT, LON) is None
    assert len(fake.calls) == 1
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 1 and messages[0].startswith("Open-Meteo payload parse error: ")


@pytest.mark.parametrize("payload", [[], "text", 5], ids=["list", "string", "number"])
async def test_the_niebla_fetch_with_a_payload_that_is_not_an_object_is_none(payload, install) -> None:
    fake = install(payload)
    assert await om_module.get_visibility_forecast(LAT, LON) is None
    assert await om_module.get_fog_inference_forecast(LAT, LON) is None
    assert len(fake.calls) == 1                                               # one shared (failed) request
    assert list(om_module._CACHE_NOWCAST._cache) == []                        # the junk was never kept as good data


async def test_the_migrated_functions_still_parse_their_good_payloads(install) -> None:
    fake = install(_CURRENT_PAYLOAD)
    current = await om_module.get_current(LAT, LON)
    assert current is not None and current.temp_c == pytest.approx(23.5)
    assert fake.calls[0].failure_message == "Open-Meteo fetch failed: %s"


async def test_the_niebla_readers_share_one_request_with_its_own_failure_message(install, monkeypatch) -> None:
    monkeypatch.setattr(om_module, "_ar_now", lambda: datetime(2024, 1, 15, 12, 30, tzinfo=om_module._AR_TZ))
    merged = {**_VISIBILITY_PAYLOAD, "hourly": {**_VISIBILITY_PAYLOAD["hourly"], **_FOG_PAYLOAD["hourly"],
                                                "visibility": [9000.0] * 24}}
    fake = install(merged)
    assert await om_module.get_visibility_forecast(LAT, LON) is not None
    assert await om_module.get_fog_inference_forecast(LAT, LON) is not None
    assert len(fake.calls) == 1
    assert fake.calls[0].failure_message == "Open-Meteo niebla combined fetch failed: %s"
    assert fake.calls[0].params == om_module._niebla_request(LAT, LON).params()


# ---------------------------------------------------------------------------
# bind_caches
# ---------------------------------------------------------------------------

async def test_an_unbound_level_fails_clearly_and_sends_nothing(install, monkeypatch) -> None:
    fake = install({"value": 1})
    monkeypatch.setattr(source_module, "_caches", {})
    with pytest.raises(CacheNotBoundError, match="FORECAST"):
        await fetch_series(_request(CacheLevel.FORECAST), _parse_value)
    assert fake.calls == []


async def test_bind_caches_binds_only_the_given_levels_and_keeps_its_own_copy(install, monkeypatch) -> None:
    fake = install({"value": 1})
    monkeypatch.setattr(source_module, "_caches", {})
    only_current = SingleFlightCache(maxsize=4, ttl=600, name="only_current")
    mapping = {CacheLevel.CURRENT: only_current}
    bind_caches(mapping)
    mapping[CacheLevel.NOWCAST] = SingleFlightCache(maxsize=4, ttl=600, name="late")   # must not leak in

    assert await fetch_series(_request(), _parse_value) == {"value": 1}
    assert list(only_current._cache) == [_key(_request())]
    with pytest.raises(CacheNotBoundError):
        await fetch_series(_request(CacheLevel.NOWCAST), _parse_value)
    assert len(fake.calls) == 1


def test_openmeteo_binds_its_three_caches_at_import() -> None:
    assert source_module._caches == {
        CacheLevel.CURRENT: om_module._CACHE_CURRENT,
        CacheLevel.FORECAST: om_module._CACHE_FORECAST,
        CacheLevel.NOWCAST: om_module._CACHE_NOWCAST,
    }


def test_the_new_modules_do_not_import_openmeteo() -> None:
    code = (
        "import sys, app.services.openmeteo_budget, app.services.openmeteo_source; "
        "print('app.services.openmeteo' in sys.modules)"
    )
    done = subprocess.run([sys.executable, "-c", code], cwd=BACKEND_DIR, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "False"


# ---------------------------------------------------------------------------
# get_source / set_source
# ---------------------------------------------------------------------------

def test_the_default_source_is_the_http_one() -> None:
    assert isinstance(get_source(), HttpOpenMeteoSource)


def test_set_source_installs_the_new_source_and_returns_the_previous_one() -> None:
    previous = get_source()
    replacement = FakeOpenMeteoSource()
    assert set_source(replacement) is previous
    assert get_source() is replacement
    assert set_source(previous) is replacement


async def test_get_current_goes_through_the_installed_source(install) -> None:
    fake = install(_CURRENT_PAYLOAD)
    current = await om_module.get_current(LAT, LON)
    assert current is not None and current.temp_c == pytest.approx(23.5)
    assert [c.params for c in fake.calls] == [om_module._current_request(LAT, LON).params()]


async def test_the_daily_fetch_reaches_the_installed_source_through_fetch_series(install) -> None:
    # Rewritten in 2c-2: it pinned `_get_json` (deleted). Same two facts, now through `fetch_series`: the source gets
    # the request's params, the failure message and the log args; and the daily fetch hands over its model.
    fake = install(None)
    request = SeriesRequest(lat=LAT, lon=LON, level=CacheLevel.FORECAST, daily=("a",))
    assert await fetch_series(request, _parse_value, failure_message="boom %s %s", log_args=("x",)) is None
    assert fake.calls == [SourceCall(request.params(), "boom %s %s", ("x",))]

    assert await om_module.get_daily_forecast_ext(LAT, LON, days=3, model="gfs_seamless") is None
    assert fake.calls[1].params["models"] == "gfs_seamless"
    assert fake.calls[1].log_args == ("gfs_seamless",)


async def test_a_refusal_from_the_source_reaches_the_daily_fetch_as_fetch_refused(install) -> None:
    # Rewritten in 2c-2: it called `_get_json` (deleted). The refusal now reaches the caller through
    # `fetch_series_or_raise`, and the public daily fetch turns it into None for this call.
    install(FetchRefused("budget"))
    with pytest.raises(FetchRefused):
        await fetch_series_or_raise(_request(), _parse_value)
    assert await om_module.get_daily_forecast_ext(LAT, LON) is None


def test_the_cache_key_rounds_the_coordinates_and_ignores_the_order() -> None:
    a = {"latitude": -31.404, "longitude": -64.196, "x": 1}
    b = {"x": 1, "longitude": -64.2, "latitude": -31.4}
    assert cache_key(a) == cache_key(b) == json.dumps({"latitude": -31.4, "longitude": -64.2, "x": 1}, sort_keys=True)


# ---------------------------------------------------------------------------
# Correction round: request validation, query order, log_args, fetch_series_or_raise
# ---------------------------------------------------------------------------

def test_a_request_without_any_variable_is_rejected() -> None:
    with pytest.raises(ValueError, match="current, hourly or daily"):
        SeriesRequest(lat=LAT, lon=LON, level=CacheLevel.CURRENT)
    with pytest.raises(ValueError, match="current, hourly or daily"):
        SeriesRequest(lat=LAT, lon=LON, level=CacheLevel.CURRENT, current=(), hourly=(), daily=())


@pytest.mark.parametrize("kind", ["current", "hourly", "daily"])
def test_one_kind_of_variable_is_enough(kind: str) -> None:
    request = SeriesRequest(lat=LAT, lon=LON, level=CacheLevel.FORECAST, **{kind: ("x",)})
    assert request.params()[kind] == "x"


def test_the_migrated_requests_keep_the_query_order_they_always_had() -> None:
    assert list(om_module._current_request(LAT, LON).params()) == [
        "latitude", "longitude", "current", "timezone", "wind_speed_unit",
    ]
    assert list(om_module._niebla_request(LAT, LON).params()) == [
        "latitude", "longitude", "current", "hourly", "timezone", "forecast_days",
    ]


async def test_log_args_reach_the_source_and_the_parse_error_log(install, caplog) -> None:
    fake = install({"value": 1})
    with caplog.at_level(logging.WARNING):
        result = await fetch_series(
            _request(), lambda p: p["nope"],
            failure_message="failed (model=%s): %s", parse_error_message="bad (model=%s): %s", log_args=("gfs",),
        )
    assert result is None
    assert fake.calls[0].failure_message == "failed (model=%s): %s"
    assert fake.calls[0].log_args == ("gfs",)
    assert [r.getMessage() for r in caplog.records] == ["bad (model=gfs): 'nope' [KeyError]"]


# ---------------------------------------------------------------------------
# Correction round: the niebla junk payload never reaches the persistent store and falls back to a good copy
# ---------------------------------------------------------------------------

_GOOD_NIEBLA = {"hourly": {"time": ["2024-01-15T12:00"]}}


async def test_the_niebla_junk_payload_is_not_handed_to_the_persistent_store(install, own_caches) -> None:
    install([])
    assert await om_module._fetch_niebla_combined(LAT, LON) is None
    await own_caches.caches[CacheLevel.NOWCAST].flush_persistence()
    assert own_caches.backend.saved == []


async def test_a_good_niebla_payload_is_handed_to_the_persistent_store(install, own_caches) -> None:
    install(_GOOD_NIEBLA)
    assert await om_module._fetch_niebla_combined(LAT, LON) == _GOOD_NIEBLA
    await own_caches.caches[CacheLevel.NOWCAST].flush_persistence()
    assert own_caches.backend.saved == [cache_key(om_module._niebla_request(LAT, LON).params())]


async def test_the_niebla_junk_payload_serves_the_persisted_copy_when_there_is_one(install, own_caches) -> None:
    key = cache_key(om_module._niebla_request(LAT, LON).params())
    own_caches.backend.stored[key] = _GOOD_NIEBLA
    install([])
    assert await om_module._fetch_niebla_combined(LAT, LON) == _GOOD_NIEBLA
    assert own_caches.backend.loaded == [key]


async def test_the_niebla_junk_payload_serves_the_stale_copy_when_there_is_one(install, clock) -> None:
    install(_GOOD_NIEBLA, [])
    assert await om_module._fetch_niebla_combined(LAT, LON) == _GOOD_NIEBLA
    clock.advance(901)
    assert await om_module._fetch_niebla_combined(LAT, LON) == _GOOD_NIEBLA


# ---------------------------------------------------------------------------
# Phase 2c-2: the daily, hourly and ECMWF hourly fetches go through the module
# ---------------------------------------------------------------------------

_DAILY_CSV = (
    "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,"
    "wind_speed_10m_max,wind_gusts_10m_max,wind_direction_10m_dominant,relative_humidity_2m_mean,"
    "uv_index_max,weather_code,sunrise,sunset,daylight_duration,cloud_cover_mean"
)
_HOURLY_CSV = (
    "temperature_2m,precipitation,precipitation_probability,wind_speed_10m,weather_code,is_day,"
    "freezing_level_height,wind_gusts_10m,cape,temperature_850hPa,relative_humidity_2m,cloud_cover,"
    "wind_direction_10m"
)
_ECMWF_HOURLY_CSV = "precipitation,wind_gusts_10m,wind_speed_10m,wind_direction_10m,weather_code,cape"
_GFS, _ECMWF = "gfs_seamless", "ecmwf_ifs025"
_HOURLY_PAYLOAD = {
    "elevation": 25.0,
    "hourly": {"time": [f"2026-10-08T{h:02d}:00" for h in range(24)], "temperature_2m": [20.0] * 24},
}
_NIEBLA_PAYLOAD = {
    **_VISIBILITY_PAYLOAD,
    "hourly": {**_VISIBILITY_PAYLOAD["hourly"], **_FOG_PAYLOAD["hourly"], "visibility": [9000.0] * 24},
}

# name -> (call(lat, lon), the request that call sends (lat, lon), a good payload for it)
_FORECAST_CASES = {
    "daily": (
        om_module.get_daily_forecast_ext, lambda a, b: om_module._daily_request(a, b, 7, None), _DAILY_EXT_PAYLOAD
    ),
    "hourly": (om_module.get_hourly_forecast_ext, lambda a, b: om_module._hourly_request(a, b, 2), _HOURLY_PAYLOAD),
    "ecmwf": (
        om_module.get_hourly_forecast_ecmwf, lambda a, b: om_module._hourly_ecmwf_request(a, b, 7), _HOURLY_PAYLOAD
    ),
}
_FORECAST_NAMES = list(_FORECAST_CASES)


def test_the_daily_request_carries_exactly_these_params() -> None:
    assert om_module._daily_request(LAT, LON, 7, None).params() == {
        "latitude": LAT, "longitude": LON, "daily": _DAILY_CSV,
        "timezone": TZ, "wind_speed_unit": "kmh", "forecast_days": 7,
    }


@pytest.mark.parametrize(("model", "sent"), [(None, {}), ("", {}), (_GFS, {"models": _GFS})])
def test_the_daily_request_sends_a_model_only_when_there_is_one(model, sent) -> None:
    params = om_module._daily_request(LAT, LON, 5, model).params()
    assert {k: v for k, v in params.items() if k == "models"} == sent
    assert (params["forecast_days"], params["daily"]) == (5, _DAILY_CSV)


def test_the_hourly_request_carries_exactly_these_params() -> None:
    assert om_module._hourly_request(LAT, LON, 3).params() == {
        "latitude": LAT, "longitude": LON, "hourly": _HOURLY_CSV,
        "timezone": TZ, "wind_speed_unit": "kmh", "forecast_days": 3,
    }


def test_the_ecmwf_hourly_request_carries_exactly_these_params() -> None:
    assert om_module._hourly_ecmwf_request(LAT, LON, 7).params() == {
        "latitude": LAT, "longitude": LON, "hourly": _ECMWF_HOURLY_CSV, "models": _ECMWF,
        "timezone": TZ, "wind_speed_unit": "kmh", "forecast_days": 7,
    }


@pytest.mark.parametrize("name", _FORECAST_NAMES)
def test_every_forecast_request_is_forecast_level_and_persisted(name) -> None:
    request = _FORECAST_CASES[name][1](LAT, LON)
    assert request.level is CacheLevel.FORECAST
    assert request.persist is True


def test_the_forecast_requests_keep_the_fixed_query_order() -> None:
    tail = ["timezone", "wind_speed_unit", "forecast_days"]
    assert list(om_module._daily_request(LAT, LON, 7, _GFS).params()) == [
        "latitude", "longitude", "daily", "models", *tail
    ]
    assert list(om_module._hourly_request(LAT, LON, 2).params()) == ["latitude", "longitude", "hourly", *tail]
    assert list(om_module._hourly_ecmwf_request(LAT, LON, 7).params()) == [
        "latitude", "longitude", "hourly", "models", *tail
    ]


@pytest.mark.parametrize("name", _FORECAST_NAMES)
async def test_a_forecast_fetch_lives_in_the_forecast_cache_and_is_handed_to_the_persistent_store(
    name, install, own_caches
) -> None:
    call, request, payload = _FORECAST_CASES[name]
    install(payload)
    assert await call(LAT, LON) is not None
    key = _key(request(LAT, LON))
    held = {level: list(cache._cache) for level, cache in own_caches.caches.items()}
    assert held == {CacheLevel.CURRENT: [], CacheLevel.FORECAST: [key], CacheLevel.NOWCAST: []}
    await own_caches.caches[CacheLevel.FORECAST].flush_persistence()
    assert own_caches.backend.saved == [key]


@pytest.mark.parametrize("name", _FORECAST_NAMES)
async def test_a_forecast_fetch_sends_the_exact_coordinates_and_shares_the_rounded_cell(name, install) -> None:
    call, _, payload = _FORECAST_CASES[name]
    fake = install(payload)
    assert await call(-31.401, -64.201) is not None
    assert await call(-31.404, -64.204) is not None
    assert len(fake.calls) == 1                                           # same two-decimal cell
    assert (fake.calls[0].params["latitude"], fake.calls[0].params["longitude"]) == (-31.401, -64.201)
    assert await call(-31.41, -64.2) is not None
    assert len(fake.calls) == 2                                           # 0.01 degrees away is another cell


@pytest.mark.parametrize("name", _FORECAST_NAMES)
async def test_a_refused_forecast_fetch_is_none_for_that_call_and_is_not_remembered(name, install) -> None:
    call, _, payload = _FORECAST_CASES[name]
    fake = install(FetchRefused("budget"), payload)
    assert await call(LAT, LON) is None
    assert await call(LAT, LON) is not None
    assert len(fake.calls) == 2


@pytest.mark.parametrize("name", _FORECAST_NAMES)
async def test_a_forecast_fetch_serves_the_stale_copy_when_the_source_refuses_after_the_ttl(
    name, install, clock
) -> None:
    call, _, payload = _FORECAST_CASES[name]
    fake = install(payload, FetchRefused("budget"))
    first = await call(LAT, LON)
    assert first is not None
    clock.advance(1801)
    assert await call(LAT, LON) is first
    assert len(fake.calls) == 2


async def test_the_raising_daily_fetch_lets_a_refusal_through_and_does_not_remember_it(install) -> None:
    fake = install(FetchRefused("budget"), _DAILY_EXT_PAYLOAD)
    with pytest.raises(FetchRefused):
        await om_module._daily_forecast_ext_or_raise(LAT, LON, 7, _GFS)
    assert await om_module._daily_forecast_ext_or_raise(LAT, LON, 7, _GFS) is not None
    assert len(fake.calls) == 2


async def test_the_daily_fetch_failure_names_the_model_in_its_log_args(install) -> None:
    fake = install(None)
    await om_module.get_daily_forecast_ext(LAT, LON, model=_GFS)
    await om_module.get_daily_forecast_ext(LAT, LON)
    message = "Open-Meteo daily_ext forecast failed (model=%s): %s"
    assert [(c.failure_message, c.log_args) for c in fake.calls] == [(message, (_GFS,)), (message, (None,))]


async def test_the_raising_daily_fetch_also_names_the_model_in_its_log_args(install) -> None:
    fake = install(None)
    await om_module._daily_forecast_ext_or_raise(LAT, LON, 7, _GFS)
    assert [(c.failure_message, c.log_args) for c in fake.calls] == [
        ("Open-Meteo daily_ext forecast failed (model=%s): %s", (_GFS,))
    ]


async def test_the_daily_fetch_labels_each_date_with_its_spanish_weekday(install) -> None:
    install({"daily": {"time": ["2024-01-15", "2024-01-20", "2024-01-21"]}})   # Monday, Saturday, Sunday
    result = await om_module.get_daily_forecast_ext(LAT, LON)
    assert result is not None
    assert result.dates == ["2024-01-15", "2024-01-20", "2024-01-21"]
    assert result.day_labels == ["lunes", "sábado", "domingo"]


async def test_the_hourly_fetches_keep_their_failure_messages(install) -> None:
    fake = install(None)
    await om_module.get_hourly_forecast_ext(LAT, LON)
    await om_module.get_hourly_forecast_ecmwf(LAT, LON)
    assert [(c.failure_message, c.log_args) for c in fake.calls] == [
        ("Open-Meteo hourly_ext forecast failed: %s", ()),
        ("Open-Meteo hourly ECMWF forecast failed: %s", ()),
    ]


async def test_the_daily_parse_error_log_names_the_model(install, caplog) -> None:
    install({"daily": None})
    with caplog.at_level(logging.WARNING):
        assert await om_module.get_daily_forecast_ext(LAT, LON, model=_GFS) is None
    (message,) = [r.getMessage() for r in caplog.records]
    assert message.startswith(f"Open-Meteo daily_ext parse error (model={_GFS}): ")
    assert message.endswith("[AttributeError]")


# --- the 2a findings: a malformed forecast payload is None, never an exception ----------------------------------

_PARSE_LOG_PREFIX = {
    "daily": "Open-Meteo daily_ext parse error (model=None): ",
    "hourly": "Open-Meteo hourly_ext parse error: ",
    "ecmwf": "Open-Meteo hourly ECMWF parse error: ",
}
# (fetch, payload, the error the parser raises on it). The AttributeError and ValueError ones of `daily` and `hourly`
# used to escape the fetch before 2c-2 (only KeyError and TypeError were caught there).
_MALFORMED = [
    ("daily", {}, "KeyError"),
    ("daily", {"daily": {"time": 5}}, "TypeError"),
    ("daily", {"daily": None}, "AttributeError"),
    ("daily", {"daily": {"time": ["not-iso"]}}, "ValueError"),
    ("hourly", {}, "KeyError"),
    ("hourly", {"hourly": {"time": 5}}, "TypeError"),
    ("hourly", {"hourly": []}, "AttributeError"),
    ("hourly", {"hourly": {"time": ["not-iso"]}}, "ValueError"),
    ("ecmwf", {}, "KeyError"),
    ("ecmwf", {"hourly": {"time": 5}}, "TypeError"),
    ("ecmwf", {"hourly": []}, "AttributeError"),
    ("ecmwf", {"hourly": {"time": ["not-iso"]}}, "ValueError"),
]


@pytest.mark.parametrize(
    ("name", "payload", "error"), _MALFORMED, ids=[f"{name}-{error}" for name, _, error in _MALFORMED]
)
async def test_a_malformed_forecast_payload_is_none_and_never_raises(name, payload, error, install, caplog) -> None:
    call, _, _ = _FORECAST_CASES[name]
    fake = install(payload)
    with caplog.at_level(logging.WARNING):
        assert await call(LAT, LON) is None
        assert await call(LAT, LON) is None                               # remembered as a failure of the key
    assert len(fake.calls) == 1
    (message,) = [r.getMessage() for r in caplog.records if r.name == source_module.logger.name]
    assert message.startswith(_PARSE_LOG_PREFIX[name]) and message.endswith(f"[{error}]")


# --- every public fetcher reaches the installed source, and openmeteo.py reaches nothing else -------------------

# name -> (call, a good payload, the requests that call must send)
_ALL_FETCHERS = {
    "current": (om_module.get_current, _CURRENT_PAYLOAD, lambda: [om_module._current_request(LAT, LON)]),
    "daily": (
        om_module.get_daily_forecast_ext, _DAILY_EXT_PAYLOAD, lambda: [om_module._daily_request(LAT, LON, 7, None)]
    ),
    "multi_model": (
        om_module.get_multi_model_daily, _DAILY_EXT_PAYLOAD,
        lambda: [om_module._daily_request(LAT, LON, 7, _GFS), om_module._daily_request(LAT, LON, 7, _ECMWF)],
    ),
    "hourly": (om_module.get_hourly_forecast_ext, _HOURLY_PAYLOAD, lambda: [om_module._hourly_request(LAT, LON, 2)]),
    "hourly_ecmwf": (
        om_module.get_hourly_forecast_ecmwf, _HOURLY_PAYLOAD, lambda: [om_module._hourly_ecmwf_request(LAT, LON, 7)]
    ),
    "visibility": (om_module.get_visibility_forecast, _NIEBLA_PAYLOAD, lambda: [om_module._niebla_request(LAT, LON)]),
    "fog": (om_module.get_fog_inference_forecast, _NIEBLA_PAYLOAD, lambda: [om_module._niebla_request(LAT, LON)]),
}


@pytest.mark.parametrize("name", list(_ALL_FETCHERS))
async def test_every_public_fetcher_reaches_the_installed_source(name, install, monkeypatch) -> None:
    monkeypatch.setattr(om_module, "_ar_now", lambda: datetime(2024, 1, 15, 12, 30, tzinfo=om_module._AR_TZ))
    call, payload, requests = _ALL_FETCHERS[name]
    fake = install(payload)
    assert await call(LAT, LON) is not None
    sent = sorted(json.dumps(c.params, sort_keys=True) for c in fake.calls)
    assert sent == sorted(json.dumps(r.params(), sort_keys=True) for r in requests())


def test_the_old_request_helpers_are_gone_from_openmeteo() -> None:
    for name in ("_get_json", "_cached_or_none", "get_source"):
        assert not hasattr(om_module, name), name


def test_openmeteo_reaches_neither_the_source_nor_the_cache_except_to_bind_the_caches() -> None:
    text = Path(om_module.__file__).read_text(encoding="utf-8")
    for needle in ("get_source", "set_source", "get_json", ".get_or_fetch("):
        assert needle not in text, needle
    assert text.count("bind_caches(") == 1
