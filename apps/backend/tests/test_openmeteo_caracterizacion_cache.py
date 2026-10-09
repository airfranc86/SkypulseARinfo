"""Characterization (phase 2a): caches of the Open-Meteo requests.

Pins, per function: which of the three caches holds its result, how long an entry lives in memory (600 / 1800 /
900 s, 15 s for a failure), the shape of the cache key, whether the result is persisted, and what comes back (None)
when the payload is malformed or the call budget refuses one of the multi-model requests. Production code is not
touched: every assertion here passes against the current code.

Several tests here look at private cache objects and TTL stores on purpose (there is no other way to see the
cache level or the key). Those structure-coupled tests are rewritten on purpose in phase 2b, when the cache level
becomes a parameter of the request; the behavior-level ones (call counts, results, what goes to Redis) should
survive that change untouched.
"""
from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, NamedTuple

import httpx
import pytest
import respx
from cachetools import TTLCache

import app.services.openmeteo as om_module
from app.core import upstash
from app.core.client_context import reset_client_key, set_client_key
from app.core.config import settings
from app.core.rate_limit_pause import openmeteo_pause as pause
from app.core.upstash import UpstashRedis
from app.services.openmeteo import (
    get_current,
    get_daily_forecast_ext,
    get_fog_inference_forecast,
    get_hourly_forecast_ecmwf,
    get_hourly_forecast_ext,
    get_multi_model_daily,
    get_visibility_forecast,
)
from app.services.openmeteo_budget import _reset_budget_for_tests, budget_refusals
from tests.conftest import FAKE_UPSTASH_TOKEN, FAKE_UPSTASH_URL, FakeClock, FakeUpstash
from tests._om_payloads import (
    _CURRENT_PAYLOAD,
    _DAILY_EXT_PAYLOAD,
    _FOG_PAYLOAD,
    _VISIBILITY_PAYLOAD,
    OM_URL,
)

LAT, LON = -31.4, -64.2
_PREFIX = "skypulse:om_last_good:"

_HOURLY_PAYLOAD = {
    "elevation": 25.0,
    "hourly": {"time": [f"2026-10-08T{h:02d}:00" for h in range(24)], "temperature_2m": [20.0] * 24},
}
_CACHES = ("_CACHE_CURRENT", "_CACHE_FORECAST", "_CACHE_NOWCAST")


class Case(NamedTuple):
    call: Callable[[float, float], Awaitable[Any]]
    payload: dict
    requests: int        # HTTP requests one logical call sends
    cache: str           # the cache that holds the result
    ttl: int             # in-memory lifetime of a good entry, seconds
    store: str           # name of the persistent store behind that cache
    persisted: int       # keys it leaves in Redis


CASES = {
    "current": Case(lambda a, b: get_current(a, b), _CURRENT_PAYLOAD, 1, "_CACHE_CURRENT", 600, "om_current", 1),
    "daily": Case(
        lambda a, b: get_daily_forecast_ext(a, b), _DAILY_EXT_PAYLOAD, 1, "_CACHE_FORECAST", 1800, "om_forecast", 1,
    ),
    "multi_model": Case(
        lambda a, b: get_multi_model_daily(a, b), _DAILY_EXT_PAYLOAD, 2, "_CACHE_FORECAST", 1800, "om_forecast", 2,
    ),
    "hourly": Case(
        lambda a, b: get_hourly_forecast_ext(a, b), _HOURLY_PAYLOAD, 1, "_CACHE_FORECAST", 1800, "om_forecast", 1,
    ),
    "hourly_ecmwf": Case(
        lambda a, b: get_hourly_forecast_ecmwf(a, b), _HOURLY_PAYLOAD, 1, "_CACHE_FORECAST", 1800, "om_forecast", 1,
    ),
    "visibility": Case(
        lambda a, b: get_visibility_forecast(a, b), _VISIBILITY_PAYLOAD, 1, "_CACHE_NOWCAST", 900, "om_nowcast", 1,
    ),
    "fog": Case(
        lambda a, b: get_fog_inference_forecast(a, b), _FOG_PAYLOAD, 1, "_CACHE_NOWCAST", 900, "om_nowcast", 1,
    ),
}
_NAMES = list(CASES)


@pytest.fixture(autouse=True)
def fixed_argentine_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """The niebla payloads are dated 2024-01-15: with the real clock the fog reader would have no hours to show."""
    monkeypatch.setattr(om_module, "_ar_now", lambda: datetime(2024, 1, 15, 12, 30, tzinfo=om_module._AR_TZ))


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """The retry of `fetch_with_retry` does not really wait."""
    monkeypatch.setattr("app.core.http_client._backoff_delay", lambda attempt: 0.0)


@pytest.fixture
def om():
    with respx.mock(assert_all_called=False) as router:
        yield router.get(OM_URL)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    """Give the fresh, failure and stale stores of the three caches a clock the test drives (same ttl as the real)."""
    fake = FakeClock()
    for cache_name in _CACHES:
        cache = getattr(om_module, cache_name)
        for store in ("_cache", "_failure_cache", "_stale_cache"):
            old = getattr(cache, store)
            monkeypatch.setattr(cache, store, TTLCache(maxsize=old.maxsize, ttl=old.ttl, timer=fake))
    return fake


@pytest.fixture
def world():
    """Open-Meteo and a stateful fake Upstash on one router; the Upstash handle is configured."""
    fake = FakeUpstash()
    with respx.mock(assert_all_called=False) as router:
        router.post(url__startswith=FAKE_UPSTASH_URL).mock(side_effect=fake.handle)
        route = router.get(OM_URL)
        upstash.configure_redis(UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN))
        try:
            yield SimpleNamespace(fake=fake, om=route)
        finally:
            upstash.configure_redis(None)


def _held(cache_name: str) -> list[str]:
    return list(getattr(om_module, cache_name)._cache.keys())


# ---------------------------------------------------------------------------
# In-memory lifetime: 600 / 1800 / 900 s fresh, 15 s for a failure
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", _NAMES)
async def test_a_good_entry_is_served_until_its_ttl_and_fetched_again_after_it(name, om, clock) -> None:
    case = CASES[name]
    om.mock(return_value=httpx.Response(200, json=case.payload))
    assert await case.call(LAT, LON) is not None
    assert om.call_count == case.requests

    clock.advance(case.ttl - 1)
    assert await case.call(LAT, LON) is not None
    assert om.call_count == case.requests          # still fresh one second before the ttl

    clock.advance(2)
    assert await case.call(LAT, LON) is not None
    assert om.call_count == 2 * case.requests      # expired one second after it


@pytest.mark.parametrize("name", _NAMES)
async def test_a_failure_is_remembered_for_fifteen_seconds(name, om, clock) -> None:
    case = CASES[name]
    om.mock(return_value=httpx.Response(503))      # a 5xx: it is retried, but it does not open the 429 pause
    assert await case.call(LAT, LON) is None
    failed_calls = om.call_count
    assert failed_calls == 2 * case.requests

    clock.advance(14)
    assert await case.call(LAT, LON) is None
    assert om.call_count == failed_calls           # served from the failure memory, no request

    clock.advance(2)
    assert await case.call(LAT, LON) is None
    assert om.call_count == 2 * failed_calls       # the memory expired: it goes out again


# ---------------------------------------------------------------------------
# Key shape
# ---------------------------------------------------------------------------

def _key_of(request: httpx.Request) -> str:
    """The cache key a request implies: its query with lat/lon rounded to 2 decimals and forecast_days as an int."""
    params: dict[str, Any] = {}
    for name, value in request.url.params.items():
        if name in ("latitude", "longitude"):
            params[name] = round(float(value), 2)
        elif name == "forecast_days":
            params[name] = int(value)
        else:
            params[name] = value
    return json.dumps(params, sort_keys=True)


_MULTI_MODEL_KEY = json.dumps(
    {"latitude": -31.4, "longitude": -64.2, "forecast_days": 7, "models": "gfs_seamless,ecmwf_ifs025"},
    sort_keys=True,
)


@pytest.mark.parametrize("name", _NAMES)
async def test_the_key_is_the_canonical_query_of_the_request(name, om) -> None:
    case = CASES[name]
    om.mock(return_value=httpx.Response(200, json=case.payload))
    assert await case.call(-31.404, -64.196) is not None
    expected = {_key_of(call.request) for call in om.calls}
    if name == "multi_model":
        expected.add(_MULTI_MODEL_KEY)             # the consensus has a synthetic key besides the two model keys
    assert set(_held(case.cache)) == expected
    for key in _held(case.cache):                   # the point of the request was rounded to its two-decimal cell
        assert (json.loads(key)["latitude"], json.loads(key)["longitude"]) == (-31.4, -64.2)


@pytest.mark.parametrize("name", _NAMES)
async def test_coordinates_within_the_same_two_decimal_cell_share_the_entry(name, om) -> None:
    case = CASES[name]
    om.mock(return_value=httpx.Response(200, json=case.payload))
    first = await case.call(-31.401, -64.201)
    second = await case.call(-31.404, -64.204)
    assert first is not None and second is not None
    assert om.call_count == case.requests

    assert await case.call(-31.41, -64.2) is not None                # 0.01 degrees away is another cell
    assert om.call_count == 2 * case.requests


async def test_the_request_carries_the_unrounded_coordinates_even_though_the_key_is_rounded(om) -> None:
    """Current behavior, not a requirement; phase 2b may change it on purpose."""
    om.mock(return_value=httpx.Response(200, json=_CURRENT_PAYLOAD))
    assert await get_current(-31.401, -64.201) is not None
    assert dict(om.calls[0].request.url.params)["latitude"] == "-31.401"
    assert dict(om.calls[0].request.url.params)["longitude"] == "-64.201"


async def test_model_and_days_tell_daily_entries_apart(om) -> None:
    om.mock(return_value=httpx.Response(200, json=_DAILY_EXT_PAYLOAD))
    variants = [
        {},
        {"model": "gfs_seamless"},
        {"model": "ecmwf_ifs025"},
        {"days": 5},
    ]
    for _ in range(2):
        for variant in variants:
            assert await get_daily_forecast_ext(LAT, LON, **variant) is not None
    assert om.call_count == 4                       # each variant fetched once, then served from the cache
    assert len(_held("_CACHE_FORECAST")) == 4


# ---------------------------------------------------------------------------
# Persistence: every function keeps its last good copy in Redis, except the multi-model consensus
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", _NAMES)
async def test_what_is_persisted_and_under_which_store(name, world) -> None:
    case = CASES[name]
    world.om.mock(return_value=httpx.Response(200, json=case.payload))
    assert await case.call(LAT, LON) is not None
    for cache_name in _CACHES:
        await getattr(om_module, cache_name).flush_persistence()
    keys = [k for k in world.fake.strings if k.startswith(_PREFIX)]
    assert len(keys) == case.persisted
    assert all(f":{case.store}:" in key for key in keys)


async def test_the_multi_model_consensus_is_never_handed_to_the_store(world, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redis would show only 2 keys even if the consensus were saved (it cannot be encoded), so watch the save calls."""
    handed: list[str] = []
    real_save = om_module._STORE_FORECAST.save

    async def spy(key: str, value) -> None:
        handed.append(key)
        await real_save(key, value)

    monkeypatch.setattr(om_module._STORE_FORECAST, "save", spy)
    world.om.mock(return_value=httpx.Response(200, json=_DAILY_EXT_PAYLOAD))
    assert await get_multi_model_daily(LAT, LON) is not None
    await om_module._CACHE_FORECAST.flush_persistence()
    assert len(handed) == 2                      # the two models, which are the source of the consensus
    assert _MULTI_MODEL_KEY not in handed


# ---------------------------------------------------------------------------
# None on failure
# ---------------------------------------------------------------------------

# Only the malformed payloads that RETURN None are pinned. Others RAISE today instead of returning None, and are
# deliberately NOT pinned (they look like bugs, not behavior to preserve):
#   get_current             {"current": 5}                        -> AttributeError
#   get_current             {"current": {"weather_code": "abc"}}  -> ValueError
#   get_daily_forecast_ext  {"daily": null}                       -> AttributeError
#   get_daily_forecast_ext  {"daily": {"time": ["not-iso"]}}      -> ValueError
#   get_hourly_forecast_ext {"hourly": []}                        -> raises (only KeyError/TypeError are caught)
@pytest.mark.parametrize(
    ("name", "payload"),
    [
        ("current", {}),                              # no "current"
        ("current", []),                              # not an object
        ("daily", {}),                                # no "daily"
        ("daily", {"daily": {"time": 5}}),            # a "time" that cannot be iterated
        ("hourly", {}),
        ("hourly_ecmwf", {}),
    ],
    ids=["current-missing", "current-not-an-object", "daily-missing", "daily-bad-time", "hourly", "hourly-ecmwf"],
)
async def test_a_malformed_payload_is_none_and_remembered_as_a_failure(name, payload, om, clock) -> None:
    case = CASES[name]
    om.mock(return_value=httpx.Response(200, json=payload))
    assert await case.call(LAT, LON) is None
    assert om.call_count == 1                         # a 200 is not retried
    assert await case.call(LAT, LON) is None
    assert om.call_count == 1                         # and the None is served from the failure memory


async def test_multi_model_with_a_refused_model_is_none_and_is_not_remembered_as_a_failure(
    om, openmeteo_budget_clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "openmeteo_calls_per_client_per_minute", 1)   # room for ONE of the two requests
    om.mock(return_value=httpx.Response(200, json=_DAILY_EXT_PAYLOAD))
    token = set_client_key("alice")
    try:
        assert await get_multi_model_daily(LAT, LON) is None
        assert om.call_count == 1
        assert budget_refusals() == {"client": 1, "global": 0}
        assert pause.allow_request() is True                                    # a refusal never opens the pause

        monkeypatch.setattr(settings, "openmeteo_calls_per_client_per_minute", 100)
        _reset_budget_for_tests()
        result = await get_multi_model_daily(LAT, LON)
        assert result is not None and len(result.models) == 2                   # the refusal was not remembered
        assert om.call_count == 2                                               # only the refused model went out
    finally:
        reset_client_key(token)
