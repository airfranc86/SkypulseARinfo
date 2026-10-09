"""Phase 2b: the one module that sends requests to Open-Meteo (`services/openmeteo_source.py`).

Covers the request description (`SeriesRequest.params()`), `fetch_series` (cache level and key, persistence, the
outcome, single flight, refusals, parse errors), `bind_caches`, the swappable source (`get_source`/`set_source`
with the `FakeOpenMeteoSource` defined here) and the real `HttpOpenMeteoSource` (pause, budget, counter, retry).

The 429 pause, the call budget and the counter are also pinned end to end, through every public function, in
`test_openmeteo_429_pause.py`, `test_openmeteo_budget.py` and `test_openmeteo_caracterizacion_*`; here the module
gets its own direct tests so it does not depend on them.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import json
import logging
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx
from cachetools import TTLCache

import app.services.openmeteo as om_module
import app.services.openmeteo_source as source_module
from app.core import usage_counter
from app.core.cache import CacheOutcome, FetchRefused, SingleFlightCache
from app.core.client_context import reset_client_key, set_client_key
from app.core.config import settings
from app.core.rate_limit_pause import openmeteo_pause as pause
from app.services import openmeteo_budget
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
from tests._om_payloads import _CURRENT_PAYLOAD, _FOG_PAYLOAD, _VISIBILITY_PAYLOAD, OM_URL
from tests.conftest import FakeClock

LAT, LON = -31.4, -64.2
TZ = "America/Argentina/Buenos_Aires"
BACKEND_DIR = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# The test adapter: answers from memory, records what it was asked
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SourceCall:
    params: dict[str, object]
    failure_message: str
    log_args: tuple[object, ...]


class FakeOpenMeteoSource:
    """`OpenMeteoSource` that never touches the network, the budget, the pause or the counter.

    `answers` are served in order and the last one repeats; each is a payload, None (a failed call) or an exception
    instance (raised, for example `FetchRefused`). `respond(params)` picks the answer from the request instead.
    `delay` makes each call yield to the event loop for that long (to overlap concurrent callers).
    """

    def __init__(
        self,
        *answers: object,
        respond: Callable[[dict[str, object]], object] | None = None,
        delay: float = 0.0,
    ) -> None:
        self._answers = list(answers) or [None]
        self._respond = respond
        self._delay = delay
        self.calls: list[SourceCall] = []

    async def get_json(self, params: dict, failure_message: str, *log_args: object) -> Any:
        self.calls.append(SourceCall(dict(params), failure_message, log_args))
        position = len(self.calls) - 1
        if self._delay:
            await asyncio.sleep(self._delay)
        answer = self._respond(params) if self._respond else self._answers[min(position, len(self._answers) - 1)]
        if isinstance(answer, BaseException):
            raise answer
        return copy.deepcopy(answer)


@pytest.fixture
def install():
    """Install a `FakeOpenMeteoSource` as the active source (conftest puts the HTTP one back after the test)."""

    def _install(*answers: object, **kwargs: Any) -> FakeOpenMeteoSource:
        fake = FakeOpenMeteoSource(*answers, **kwargs)
        set_source(fake)
        return fake

    return _install


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    """Give the fresh, failure and stale stores of the three real caches a clock the test drives."""
    fake = FakeClock()
    for cache in (om_module._CACHE_CURRENT, om_module._CACHE_FORECAST, om_module._CACHE_NOWCAST):
        for store in ("_cache", "_failure_cache", "_stale_cache"):
            old = getattr(cache, store)
            monkeypatch.setattr(cache, store, TTLCache(maxsize=old.maxsize, ttl=old.ttl, timer=fake))
    return fake


class RecordingBackend:
    """Persistent backend that remembers which keys it was asked to save and to load."""

    def __init__(self) -> None:
        self.saved: list[str] = []
        self.loaded: list[str] = []
        self.stored: dict[str, object] = {}

    async def load(self, key: str) -> object | None:
        self.loaded.append(key)
        return self.stored.get(key)

    async def save(self, key: str, value: object) -> None:
        self.saved.append(key)


@pytest.fixture
def own_caches(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Three fresh caches (with a recording backend) bound in place of the real ones for this test."""
    monkeypatch.setattr(source_module, "_caches", {})
    backend = RecordingBackend()
    caches = {
        level: SingleFlightCache(maxsize=8, ttl=600, name=f"test_{level.name.lower()}", persistence=backend)
        for level in CacheLevel
    }
    bind_caches(caches)
    return SimpleNamespace(backend=backend, caches=caches)


def _parse_value(payload: dict) -> dict:
    return {"value": payload["value"]}


def _request(level: CacheLevel = CacheLevel.CURRENT, lat: float = LAT, lon: float = LON, **kwargs: Any) -> SeriesRequest:
    return SeriesRequest(lat=lat, lon=lon, level=level, current=("temperature_2m",), **kwargs)


def _key(request: SeriesRequest) -> str:
    return cache_key(request.params())


# ---------------------------------------------------------------------------
# SeriesRequest.params(): the query that goes over the wire
# ---------------------------------------------------------------------------

_CURRENT_CSV = (
    "temperature_2m,relative_humidity_2m,apparent_temperature,surface_pressure,wind_speed_10m,"
    "wind_direction_10m,wind_gusts_10m,precipitation,cloud_cover,weather_code"
)
_NIEBLA_HOURLY_CSV = "visibility,relative_humidity_2m,dew_point_2m,temperature_2m,wind_speed_10m,weather_code"


def test_the_current_request_is_exactly_what_get_current_has_always_sent() -> None:
    assert om_module._current_request(LAT, LON).params() == {
        "latitude": LAT,
        "longitude": LON,
        "current": _CURRENT_CSV,
        "timezone": TZ,
        "wind_speed_unit": "kmh",
    }


def test_the_niebla_request_is_exactly_what_the_combined_fetch_has_always_sent() -> None:
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


async def test_the_unmigrated_fetches_reach_the_installed_source_through_get_json(install) -> None:
    fake = install(None)
    assert await om_module._get_json({"a": 1}, "boom %s %s", "x") is None
    assert fake.calls == [SourceCall({"a": 1}, "boom %s %s", ("x",))]

    assert await om_module.get_daily_forecast_ext(LAT, LON, days=3, model="gfs_seamless") is None
    assert fake.calls[1].params["models"] == "gfs_seamless"
    assert fake.calls[1].log_args == ("gfs_seamless",)


async def test_a_refusal_from_the_source_reaches_the_unmigrated_fetches_as_fetch_refused(install) -> None:
    install(FetchRefused("budget"))
    with pytest.raises(FetchRefused):
        await om_module._get_json({"a": 1}, "boom %s")
    assert await om_module.get_daily_forecast_ext(LAT, LON) is None


# ---------------------------------------------------------------------------
# HttpOpenMeteoSource: pause, budget, counter, retry (direct tests of the real adapter)
# ---------------------------------------------------------------------------

PARAMS = {"latitude": LAT, "longitude": LON, "current": "temperature_2m"}


@pytest.fixture
def om():
    with respx.mock(assert_all_called=False) as router:
        yield router.get(OM_URL)


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """The retry of `fetch_with_retry` does not really wait."""
    monkeypatch.setattr("app.core.http_client._backoff_delay", lambda attempt: 0.0)


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(usage_counter, "record", calls.append)
    return calls


@pytest.fixture
def pause_clock() -> FakeClock:
    fake = FakeClock()
    pause.clock = fake
    return fake


@contextmanager
def as_client(key: str) -> Iterator[None]:
    token = set_client_key(key)
    try:
        yield
    finally:
        reset_client_key(token)


async def test_http_a_good_answer_is_the_json_and_counts_once(om, counted) -> None:
    om.mock(return_value=httpx.Response(200, json={"ok": 1}))
    assert await HttpOpenMeteoSource().get_json(PARAMS, "failed %s") == {"ok": 1}
    assert counted == ["open_meteo"]
    assert dict(om.calls[0].request.url.params) == {
        "latitude": "-31.4", "longitude": "-64.2", "current": "temperature_2m"
    }


async def test_http_uses_the_shared_client_with_the_timeout_of_the_settings(monkeypatch) -> None:
    client = MagicMock()
    client.request = AsyncMock(return_value=httpx.Response(200, json={"ok": 1}, request=httpx.Request("GET", OM_URL)))
    monkeypatch.setattr(source_module, "get_client", lambda: client)
    assert await HttpOpenMeteoSource().get_json(PARAMS, "failed %s") == {"ok": 1}
    client.request.assert_awaited_once()
    args, kwargs = client.request.await_args
    assert args == ("GET", settings.openmeteo_base_url)
    assert kwargs["params"] == PARAMS
    assert kwargs["timeout"] == settings.http_timeout_seconds


async def test_http_without_a_started_client_is_none_and_counts_nothing(monkeypatch, counted, caplog) -> None:
    def no_client() -> httpx.AsyncClient:
        raise RuntimeError("httpx client not started")

    monkeypatch.setattr(source_module, "get_client", no_client)
    with caplog.at_level(logging.WARNING):
        assert await HttpOpenMeteoSource().get_json(PARAMS, "failed %s") is None
    assert counted == []
    assert "failed httpx client not started" in caplog.text


async def test_http_a_failure_is_none_and_logs_the_message_with_its_arguments(om, counted, caplog) -> None:
    om.mock(return_value=httpx.Response(200, content=b"not json"))
    with caplog.at_level(logging.WARNING):
        assert await HttpOpenMeteoSource().get_json(PARAMS, "failed (model=%s): %s", "gfs") is None
    records = [r for r in caplog.records if r.name == source_module.logger.name]
    assert len(records) == 1 and records[0].getMessage().startswith("failed (model=gfs): ")


async def test_http_an_open_pause_sends_nothing_and_counts_nothing(om, counted, pause_clock) -> None:
    pause.trip()
    om.mock(return_value=httpx.Response(200, json={"ok": 1}))
    assert await HttpOpenMeteoSource().get_json(PARAMS, "failed %s") is None
    assert om.call_count == 0
    assert counted == []


async def test_http_an_open_pause_spends_no_budget(om, counted, pause_clock, monkeypatch) -> None:
    monkeypatch.setattr(settings, "openmeteo_calls_per_client_per_minute", 1)
    pause.trip()
    with as_client("alice"):
        assert await HttpOpenMeteoSource().get_json(PARAMS, "failed %s") is None
        assert await HttpOpenMeteoSource().get_json(PARAMS, "failed %s") is None   # a refusal would raise instead
    assert openmeteo_budget.budget_refusals() == {"client": 0, "global": 0}


async def test_http_a_refused_call_raises_fetch_refused_and_costs_nothing(om, counted, monkeypatch) -> None:
    monkeypatch.setattr(settings, "openmeteo_calls_per_client_per_minute", 1)
    om.mock(return_value=httpx.Response(200, json={"ok": 1}))
    source = HttpOpenMeteoSource()
    with as_client("alice"):
        assert await source.get_json(PARAMS, "failed %s") == {"ok": 1}
        with pytest.raises(FetchRefused):
            await source.get_json(PARAMS, "failed %s")
    assert om.call_count == 1
    assert counted == ["open_meteo"]
    assert openmeteo_budget.budget_refusals() == {"client": 1, "global": 0}
    assert pause.allow_request() is True                                          # a refusal never opens the pause


async def test_http_a_refused_half_open_probe_gives_its_slot_back(om, counted, pause_clock, monkeypatch) -> None:
    monkeypatch.setattr(settings, "openmeteo_calls_per_client_per_minute", 1)
    pause.trip()
    pause_clock.advance(10_000)                                                   # the pause is over: next is the probe
    with as_client("alice"):
        assert openmeteo_budget.admit_network_call() is True                      # spends the only token
        with pytest.raises(FetchRefused):
            await HttpOpenMeteoSource().get_json(PARAMS, "failed %s")
    assert om.call_count == 0 and counted == []
    assert pause.allow_request() is True                                          # the probe slot is free again


async def test_http_a_429_opens_the_pause_and_is_not_retried(om, counted, pause_clock) -> None:
    om.mock(return_value=httpx.Response(429, json={"error": True}))
    assert await HttpOpenMeteoSource().get_json(PARAMS, "failed %s") is None
    assert om.call_count == 1
    assert counted == ["open_meteo"]
    assert pause.remaining() == pytest.approx(120.0)


async def test_http_the_retry_after_of_a_429_sets_the_length_of_the_pause(om, counted, pause_clock) -> None:
    om.mock(return_value=httpx.Response(429, headers={"Retry-After": "45"}))
    assert await HttpOpenMeteoSource().get_json(PARAMS, "failed %s") is None
    assert pause.remaining() == pytest.approx(45.0)


async def test_http_a_retry_after_that_is_not_a_number_uses_the_default_pause(om, counted, pause_clock) -> None:
    om.mock(return_value=httpx.Response(429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}))
    assert await HttpOpenMeteoSource().get_json(PARAMS, "failed %s") is None
    assert pause.remaining() == pytest.approx(120.0)


async def test_http_a_5xx_is_retried_once_counts_once_and_does_not_open_the_pause(om, counted, pause_clock) -> None:
    om.mock(return_value=httpx.Response(503))
    assert await HttpOpenMeteoSource().get_json(PARAMS, "failed %s") is None
    assert om.call_count == 2
    assert counted == ["open_meteo"]
    assert pause.remaining() == 0.0


async def test_http_a_5xx_followed_by_a_good_answer_is_the_json(om, counted) -> None:
    om.mock(side_effect=[httpx.Response(503), httpx.Response(200, json={"ok": 1})])
    assert await HttpOpenMeteoSource().get_json(PARAMS, "failed %s") == {"ok": 1}
    assert om.call_count == 2
    assert counted == ["open_meteo"]


async def test_http_a_good_answer_closes_the_pause(om, counted, pause_clock) -> None:
    pause.trip()
    pause_clock.advance(10_000)                                                   # this call is the probe
    om.mock(return_value=httpx.Response(200, json={"ok": 1}))
    assert await HttpOpenMeteoSource().get_json(PARAMS, "failed %s") == {"ok": 1}
    assert pause.allow_request() is True and pause.allow_request() is True        # no probe left in flight
    assert pause.remaining() == 0.0


async def test_http_calls_made_outside_a_request_are_not_capped(om, counted, monkeypatch) -> None:
    monkeypatch.setattr(settings, "openmeteo_calls_per_client_per_minute", 1)
    om.mock(return_value=httpx.Response(200, json={"ok": 1}))
    source = HttpOpenMeteoSource()
    for _ in range(3):
        assert await source.get_json(PARAMS, "failed %s") == {"ok": 1}
    assert counted == ["open_meteo"] * 3


def test_the_retry_after_helper_reads_numbers_only() -> None:
    read = source_module._retry_after_seconds
    assert read(httpx.Response(429, headers={"Retry-After": "7.5"})) == 7.5
    assert read(httpx.Response(429, headers={"Retry-After": "soon"})) is None
    assert read(httpx.Response(429)) is None


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


async def test_fetch_series_or_raise_lets_a_refusal_through_and_does_not_remember_it(install) -> None:
    fake = install(FetchRefused("budget"), {"value": 1})
    with pytest.raises(FetchRefused):
        await fetch_series_or_raise(_request(), _parse_value)
    assert await fetch_series_or_raise(_request(), _parse_value) == {"value": 1}
    assert len(fake.calls) == 2


async def test_fetch_series_or_raise_serves_the_stale_copy_on_a_refusal(install, clock) -> None:
    install({"value": 1}, FetchRefused("budget"))
    await fetch_series_or_raise(_request(), _parse_value)
    clock.advance(601)
    outcome = CacheOutcome()
    assert await fetch_series_or_raise(_request(), _parse_value, outcome=outcome) == {"value": 1}
    assert outcome.hit is True


async def test_fetch_series_or_raise_is_none_for_failures_and_parse_errors_like_fetch_series(install) -> None:
    install(None)
    assert await fetch_series_or_raise(_request(lat=1.0), _parse_value) is None
    install({"value": 1})
    assert await fetch_series_or_raise(_request(lat=2.0), lambda p: p["nope"]) is None


async def test_fetch_series_or_raise_takes_the_same_options_as_fetch_series(install, own_caches, caplog) -> None:
    fake = install({"value": 1})
    outcome = CacheOutcome()
    kwargs = dict(outcome=outcome, failure_message="f %s", parse_error_message="p %s", log_args=("x",))
    assert await fetch_series_or_raise(_request(persist=False), _parse_value, **kwargs) == {"value": 1}
    await own_caches.caches[CacheLevel.CURRENT].flush_persistence()
    assert own_caches.backend.saved == []
    assert (fake.calls[0].failure_message, fake.calls[0].log_args) == ("f %s", ("x",))
    assert outcome.hit is False


async def test_the_wrapper_and_the_raising_variant_differ_only_in_the_refusal(install) -> None:
    install(FetchRefused("budget"))
    assert await fetch_series(_request(lat=1.0), _parse_value) is None
    with pytest.raises(FetchRefused):
        await fetch_series_or_raise(_request(lat=2.0), _parse_value)


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
# Correction round: a cancelled request gives back the half-open probe it holds (and only that one)
# ---------------------------------------------------------------------------

class GatedClient:
    """Shared-client double whose request starts, tells the test, and then waits until it is cancelled."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()

    async def request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        self.entered.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


async def _cancel(task: asyncio.Task) -> None:
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_http_a_cancelled_probe_gives_its_slot_back_and_still_counts_once(counted, pause_clock, monkeypatch) -> None:
    client = GatedClient()
    monkeypatch.setattr(source_module, "get_client", lambda: client)
    pause.trip()
    pause_clock.advance(10_000)                                                   # the pause is over: next is the probe
    task = asyncio.create_task(HttpOpenMeteoSource().get_json(PARAMS, "failed %s"))
    await asyncio.wait_for(client.entered.wait(), 5)
    assert pause.allow_request() is False                                         # the probe is in flight
    await _cancel(task)
    assert counted == ["open_meteo"]                                              # the cancelled call was counted once
    assert pause.allow_request() is True                                          # the next caller does not wait 15 s


async def test_http_a_cancelled_probe_does_not_release_the_probe_of_another_window(counted, pause_clock, monkeypatch) -> None:
    client = GatedClient()
    monkeypatch.setattr(source_module, "get_client", lambda: client)
    pause.trip()
    pause_clock.advance(10_000)
    task = asyncio.create_task(HttpOpenMeteoSource().get_json(PARAMS, "failed %s"))
    await asyncio.wait_for(client.entered.wait(), 5)
    pause.trip()                                                                  # another request got a 429: new pause
    pause_clock.advance(10_000)
    assert pause.allow_request() is True                                          # a second caller takes the NEW probe
    await _cancel(task)
    assert pause.allow_request() is False                                         # and the cancelled one did not free it


async def test_http_a_cancelled_call_outside_a_pause_leaves_the_pause_closed(counted, monkeypatch) -> None:
    client = GatedClient()
    monkeypatch.setattr(source_module, "get_client", lambda: client)
    task = asyncio.create_task(HttpOpenMeteoSource().get_json(PARAMS, "failed %s"))
    await asyncio.wait_for(client.entered.wait(), 5)
    await _cancel(task)
    assert counted == ["open_meteo"]
    assert pause.remaining() == 0.0 and pause.allow_request() is True and pause.allow_request() is True
