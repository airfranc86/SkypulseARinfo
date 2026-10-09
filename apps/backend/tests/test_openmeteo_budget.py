"""Call budget for Open-Meteo: a share per client AND a global cap, spent in `HttpOpenMeteoSource.get_json`.

Why: the cache key rounds lat/lon to 2 decimals, so one client can ask for millions of distinct cells.
Every cell is ~5 calls to Open-Meteo; a sweep would drain the free plan and the first 429 would pause
EVERYBODY (PR #105). The budget bounds what one client can send and what the whole process can send.

B1 - The per-client cap (default 12/min): the 13th call is refused without the network, the counter or the pause.
B2 - The global cap (default 90/min), shared by all clients; the client's token comes back on a global refusal.
B3 - Outside an HTTP request (no client key) nothing is capped.
B4 - A refusal returns None so the cache serves the last good copy; it is counted by reason and logged once a minute.
B5 - One cache flight spends one token however many requests wait for it.
B6 - A scan by one client leaves another client its full share.
B7 - Settings are validated; the structure that tracks clients is bounded.
B8 - A refusal is not a failure of the cell: nothing is negative-cached, another client can refresh it.
B9 - A refused half-open probe gives its slot back.
B10 - The shared `unverified` key gets a larger dedicated share, still bounded by the global bucket.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager

import httpx
import pytest
import respx
from pydantic import ValidationError

import app.services.openmeteo as om_module
import app.services.openmeteo_budget as budget_module
from app.core import usage_counter
from app.core.cache import CacheOutcome
from app.core.client_context import reset_client_key, set_client_key
from app.core.config import Settings, settings
from app.core.rate_limit import UNVERIFIED_CLIENT_KEY
from app.core.rate_limit_pause import openmeteo_pause as pause
from app.services.openmeteo import (
    get_current,
    get_daily_forecast_ext,
    get_fog_inference_forecast,
    get_hourly_forecast_ecmwf,
    get_hourly_forecast_ext,
    get_multi_model_daily,
    get_visibility_forecast,
)
from app.services.openmeteo_budget import budget_refusals
from tests.conftest import FakeClock
from tests.test_openmeteo_cache import (
    _CURRENT_PAYLOAD,
    _DAILY_EXT_PAYLOAD,
    _FOG_PAYLOAD,
    _VISIBILITY_PAYLOAD,
    OM_URL,
)

_NO_REFUSALS = {"client": 0, "global": 0}


@pytest.fixture
def om():
    """The Open-Meteo route, answering the "current" payload by default."""
    with respx.mock(assert_all_called=False) as router:
        yield router.get(OM_URL).mock(return_value=httpx.Response(200, json=_CURRENT_PAYLOAD))


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record each `usage_counter.record` instead of sending it to Upstash."""
    calls: list[str] = []
    monkeypatch.setattr(usage_counter, "record", calls.append)
    return calls


@pytest.fixture
def set_caps(monkeypatch: pytest.MonkeyPatch):
    def _set(*, client: int | None = None, overall: int | None = None) -> None:
        if client is not None:
            monkeypatch.setattr(settings, "openmeteo_calls_per_client_per_minute", client)
        if overall is not None:
            monkeypatch.setattr(settings, "openmeteo_calls_per_minute", overall)

    return _set


@contextmanager
def as_client(key: str | None) -> Iterator[None]:
    token = set_client_key(key)
    try:
        yield
    finally:
        reset_client_key(token)


def _cell(index: int) -> tuple[float, float]:
    """A distinct cache cell per index (lat/lon are rounded to 2 decimals in the cache key)."""
    return -20.0 - index * 0.05, -60.0


async def _calls(count: int, *, start: int = 0) -> list[object]:
    """`count` fetches of distinct cells, one after the other; None marks a call that did not succeed."""
    return [await get_current(*_cell(start + i)) for i in range(count)]


def _succeeded(results: list[object]) -> list[bool]:
    return [result is not None for result in results]


# ---------------------------------------------------------------------------
# B1 - per-client cap
# ---------------------------------------------------------------------------

async def test_b1_the_13th_call_in_a_minute_from_one_client_is_refused_without_a_network_call(om, counted):
    with as_client("alice"):
        results = await _calls(13)

    assert _succeeded(results) == [True] * 12 + [False]
    assert om.call_count == 12
    assert len(counted) == 12  # the refused call was not counted as an Open-Meteo call
    assert budget_refusals() == {"client": 1, "global": 0}


async def test_b1_a_refusal_is_a_plain_none_and_never_raises(om, counted, set_caps):
    set_caps(client=1)
    with as_client("alice"):
        await _calls(1)

        assert await get_current(*_cell(1)) is None
        assert await get_daily_forecast_ext(*_cell(2)) is None
        assert await get_multi_model_daily(*_cell(3)) is None

    assert om.call_count == 1


async def test_b1_the_share_refills_with_time(om, counted, openmeteo_budget_clock: FakeClock):
    with as_client("alice"):
        await _calls(12)
        assert await get_current(*_cell(20)) is None

        openmeteo_budget_clock.advance(4)  # 12 per 60 s is one token per 5 s: 0.8 so far
        assert await get_current(*_cell(21)) is None

        openmeteo_budget_clock.advance(1.5)  # 1.1 tokens
        assert await get_current(*_cell(22)) is not None
        assert await get_current(*_cell(23)) is None


async def test_b1_a_refusal_does_not_open_the_429_pause(om, counted, set_caps):
    set_caps(client=1)
    with as_client("alice"):
        await _calls(10)

    assert pause.remaining() == 0.0
    assert pause.allow_request() is True


async def test_b1_a_refusal_leaves_the_cached_cells_of_the_client_available(om, counted, set_caps):
    set_caps(client=2)
    with as_client("alice"):
        first = await get_current(*_cell(0))
        await get_current(*_cell(1))
        assert await get_current(*_cell(2)) is None  # share spent

        assert await get_current(*_cell(0)) is first  # a cache hit needs no token
        assert om.call_count == 2


async def test_b1_the_client_share_is_not_the_global_setting(om, counted, set_caps):
    set_caps(client=3, overall=50)
    with as_client("alice"):
        results = await _calls(5)

    assert _succeeded(results) == [True, True, True, False, False]


async def test_b1_the_empty_string_is_a_client_not_an_exemption(om, counted, set_caps):
    set_caps(client=2)
    with as_client(""):
        results = await _calls(4)

    assert _succeeded(results) == [True, True, False, False]


# ---------------------------------------------------------------------------
# B2 - global cap
# ---------------------------------------------------------------------------

async def test_b2_the_global_cap_applies_across_clients(om, counted, set_caps):
    set_caps(client=5, overall=8)
    with as_client("alice"):
        assert all(_succeeded(await _calls(5)))
    with as_client("bob"):
        results = await _calls(5, start=10)

    assert _succeeded(results) == [True, True, True, False, False]
    assert om.call_count == 8
    assert budget_refusals() == {"client": 0, "global": 2}


async def test_b2_the_global_bucket_refills_with_time(om, counted, set_caps, openmeteo_budget_clock: FakeClock):
    set_caps(client=10, overall=6)  # one global token every 10 s
    with as_client("alice"):
        await _calls(6)
        assert await get_current(*_cell(10)) is None

        openmeteo_budget_clock.advance(9)
        assert await get_current(*_cell(11)) is None
        openmeteo_budget_clock.advance(2)
        assert await get_current(*_cell(12)) is not None


async def test_b2_a_client_over_its_share_does_not_spend_global_tokens(om, counted, set_caps):
    set_caps(client=3, overall=6)
    with as_client("alice"):
        await _calls(3)
        refused = await _calls(5, start=10)  # alice keeps trying
    assert not any(_succeeded(refused))

    with as_client("bob"):
        results = await _calls(3, start=20)

    assert all(_succeeded(results))  # alice left the other three global tokens alone
    assert om.call_count == 6


async def test_b2_a_global_refusal_gives_the_clients_token_back(
    om, counted, set_caps, openmeteo_budget_clock: FakeClock
):
    set_caps(client=2, overall=3)
    with as_client("alice"):
        await _calls(2)
    with as_client("bob"):
        assert await get_current(*_cell(10)) is not None  # the last global token
        assert await get_current(*_cell(11)) is None  # refused by the global bucket: not bob's fault

        openmeteo_budget_clock.advance(20)  # one global token is back (3 per 60 s)
        assert await get_current(*_cell(12)) is not None  # bob's share was never charged for the refusal


# ---------------------------------------------------------------------------
# B3 - outside an HTTP request
# ---------------------------------------------------------------------------

async def test_b3_without_a_client_key_nothing_is_capped_and_nothing_is_spent(om, counted):
    results = await _calls(300)  # scripts, scheduled jobs and plain service tests have no client key

    assert all(_succeeded(results))
    assert om.call_count == 300
    assert len(counted) == 300  # they still count: only the cap is lifted
    assert budget_refusals() == _NO_REFUSALS

    with as_client("alice"):  # and they left alice's share and the global bucket untouched
        results = await _calls(12, start=400)
    assert all(_succeeded(results))


# ---------------------------------------------------------------------------
# B4 - refusals: ordering, counting, serving the last good copy, logging
# ---------------------------------------------------------------------------

async def test_b4_a_call_during_the_pause_spends_no_budget(om, counted, set_caps):
    set_caps(client=3)
    pause_clock = FakeClock()
    pause.clock = pause_clock
    pause.trip()

    with as_client("alice"):
        during = await _calls(20)

    assert not any(_succeeded(during))
    assert om.call_count == 0
    assert counted == []
    assert budget_refusals() == _NO_REFUSALS  # the pause answered first

    pause_clock.advance(120)
    with as_client("alice"):
        after = await _calls(3, start=100)
    assert all(_succeeded(after))  # alice still had her whole share when the pause ended


@pytest.mark.parametrize(
    "name, call",
    [
        ("current", lambda: get_current(-31.4, -64.2)),
        ("daily", lambda: get_daily_forecast_ext(-31.4, -64.2)),
        ("hourly", lambda: get_hourly_forecast_ext(-31.4, -64.2)),
        ("hourly_ecmwf", lambda: get_hourly_forecast_ecmwf(-31.4, -64.2)),
        ("visibility", lambda: get_visibility_forecast(-31.4, -64.2)),
        ("fog", lambda: get_fog_inference_forecast(-31.4, -64.2)),
    ],
)
async def test_b4_every_fetch_function_goes_through_the_budget(name, call, om, counted, set_caps):
    set_caps(client=1)
    with as_client("alice"):
        assert await get_current(*_cell(0)) is not None  # the only token
        calls_before = om.call_count

        assert await call() is None

    assert om.call_count == calls_before
    assert len(counted) == 1
    assert budget_refusals()["client"] >= 1


async def test_b4_the_last_good_copy_is_served_when_the_budget_refuses(om, counted, set_caps):
    set_caps(client=3)
    om.mock(return_value=httpx.Response(200, json=_CURRENT_PAYLOAD))
    with as_client("alice"):
        first = await get_current(*_cell(0))
        assert first is not None
        om_module._CACHE_CURRENT._cache.clear()  # the fresh TTL expired; the stale copy stays
        om_module._CACHE_CURRENT._failure_cache.clear()
        await _calls(2, start=10)  # the rest of the share
        calls_before = om.call_count

        outcome = CacheOutcome()
        assert await get_current(*_cell(0), cache_outcome=outcome) is first

    assert outcome.hit is True
    assert om.call_count == calls_before
    assert budget_refusals()["client"] == 1


async def test_b4_the_multi_model_forecast_is_served_from_its_stale_copies(om, counted, set_caps):
    set_caps(client=2)
    om.mock(return_value=httpx.Response(200, json=_DAILY_EXT_PAYLOAD))
    with as_client("alice"):
        first = await get_multi_model_daily(*_cell(0))  # two calls: the whole share
        assert first is not None
        om_module._CACHE_FORECAST._cache.clear()
        om_module._CACHE_FORECAST._failure_cache.clear()
        calls_before = om.call_count

        again = await get_multi_model_daily(*_cell(0))

    assert again is not None and again.models == first.models
    assert om.call_count == calls_before
    assert budget_refusals()["client"] == 2


async def test_b4_refusals_are_counted_by_reason_and_the_counter_is_a_copy(om, counted, set_caps):
    set_caps(client=2, overall=3)
    with as_client("alice"):
        await _calls(4)  # 2 served, 2 over her share
    with as_client("bob"):
        await _calls(2, start=10)  # 1 served (the last global token), 1 refused by the global bucket

    snapshot = budget_refusals()
    assert snapshot == {"client": 2, "global": 1}

    snapshot["client"] = 99
    assert budget_refusals()["client"] == 2


async def test_b4_the_refusal_log_is_throttled_to_one_line_a_minute_without_addresses(
    om, counted, set_caps, openmeteo_budget_clock: FakeClock, caplog: pytest.LogCaptureFixture
):
    set_caps(client=1)
    caplog.set_level(logging.WARNING)

    def warnings() -> list[logging.LogRecord]:
        return [
            r for r in caplog.records
            if r.name == "app.services.openmeteo_budget" and r.levelno == logging.WARNING
        ]

    with as_client("203.0.113.9"):
        await _calls(6)  # 1 served, 5 refused
        assert len(warnings()) == 1
        assert "client=1" in warnings()[0].getMessage()  # the first refusal is reported at once

        openmeteo_budget_clock.advance(61)  # a minute later and one token back
        await _calls(2, start=10)  # 1 served, 1 refused

    assert len(warnings()) == 2
    assert "client=5" in warnings()[1].getMessage()  # the 4 suppressed refusals plus this one
    assert "global=0" in warnings()[1].getMessage()
    assert all("203.0.113.9" not in record.getMessage() for record in caplog.records)


# ---------------------------------------------------------------------------
# B5 - one flight, one token
# ---------------------------------------------------------------------------

async def test_b5_one_flight_spends_one_token_for_all_the_requests_that_wait_for_it(om, counted, set_caps):
    set_caps(client=3)

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return httpx.Response(200, json=_CURRENT_PAYLOAD)

    om.mock(side_effect=slow)
    with as_client("alice"):
        results = await asyncio.gather(*[get_current(*_cell(0)) for _ in range(20)])
        assert all(result is not None for result in results)
        assert om.call_count == 1 and len(counted) == 1

        assert await get_current(*_cell(1)) is not None  # two tokens were left
        assert await get_current(*_cell(2)) is not None
        assert await get_current(*_cell(3)) is None


async def test_b5_joining_the_flight_of_another_client_spends_nothing(om, counted, set_caps):
    set_caps(client=3)

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return httpx.Response(200, json=_CURRENT_PAYLOAD)

    om.mock(side_effect=slow)

    async def as_(key: str, index: int):
        with as_client(key):
            return await get_current(*_cell(index))

    first, second = await asyncio.gather(as_("alice", 0), as_("bob", 0))

    assert first is not None and second is not None
    assert om.call_count == 1
    with as_client("bob"):
        assert all(_succeeded(await _calls(3, start=10)))  # bob paid nothing for the shared flight


# ---------------------------------------------------------------------------
# B6 - a sweep by one client
# ---------------------------------------------------------------------------

async def test_b6_a_sweep_of_distinct_cells_does_not_stop_another_client(om, counted):
    with as_client("scanner"):
        results = await _calls(60)

    assert sum(_succeeded(results)) == 12  # the scanner got its share and no more
    assert om.call_count == 12

    with as_client("neighbour"):
        neighbour = await _calls(12, start=100)

    assert all(_succeeded(neighbour))
    assert om.call_count == 24
    assert pause.remaining() == 0.0 and pause.allow_request() is True  # no 429 was provoked
    assert budget_refusals() == {"client": 48, "global": 0}


# ---------------------------------------------------------------------------
# B7 - settings and bounds
# ---------------------------------------------------------------------------

def test_b7_the_defaults_are_12_per_client_and_90_overall():
    defaults = Settings(_env_file=None)

    assert defaults.openmeteo_calls_per_client_per_minute == 12
    assert defaults.openmeteo_calls_per_minute == 90


@pytest.mark.parametrize("name", ["openmeteo_calls_per_client_per_minute", "openmeteo_calls_per_minute"])
@pytest.mark.parametrize("value", [0, -1])
def test_b7_a_cap_below_one_is_rejected(name: str, value: int):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{name: value})


def test_b7_the_caps_come_from_the_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENMETEO_CALLS_PER_CLIENT_PER_MINUTE", "7")
    monkeypatch.setenv("OPENMETEO_CALLS_PER_MINUTE", "40")

    configured = Settings(_env_file=None)

    assert configured.openmeteo_calls_per_client_per_minute == 7
    assert configured.openmeteo_calls_per_minute == 40


async def test_b7_the_number_of_tracked_clients_is_bounded(om, counted, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(budget_module, "_MAX_TRACKED_CLIENTS", 4)

    for index in range(10):
        with as_client(f"client-{index}"):
            assert await get_current(*_cell(index)) is not None

    assert budget_module._budget().tracked_clients == 4


# ---------------------------------------------------------------------------
# B8 - a refusal is not a failure of the cell
# ---------------------------------------------------------------------------

async def test_b8_a_refused_cell_is_not_remembered_as_failed_and_another_client_fetches_it(
    om, counted, set_caps
):
    set_caps(client=1)
    with as_client("alice"):
        await _calls(1)
        assert await get_current(*_cell(1)) is None  # over her share

    assert len(om_module._CACHE_CURRENT._failure_cache) == 0
    with as_client("bob"):
        assert await get_current(*_cell(1)) is not None  # goes to the network: nobody poisoned the cell
    assert om.call_count == 2


async def test_b8_the_refused_client_gets_the_stale_copy_and_another_client_refreshes_it(
    om, counted, set_caps
):
    set_caps(client=2)
    with as_client("alice"):
        first = await get_current(*_cell(0))
        om_module._CACHE_CURRENT._cache.clear()  # the fresh TTL expired; the stale copy stays
        assert await get_current(*_cell(1)) is not None  # her second and last token
        outcome = CacheOutcome()

        assert await get_current(*_cell(0), cache_outcome=outcome) is first

    assert outcome.hit is True
    assert len(om_module._CACHE_CURRENT._failure_cache) == 0
    calls_before = om.call_count
    with as_client("bob"):
        refreshed = await get_current(*_cell(0))
    assert refreshed is not None and refreshed is not first
    assert om.call_count == calls_before + 1


async def test_b8_the_waiters_of_a_refused_flight_get_the_same_outcome(om, counted, set_caps):
    set_caps(client=1)
    with as_client("alice"):
        await _calls(1)
        results = await asyncio.gather(*[get_current(*_cell(1)) for _ in range(5)])

    assert results == [None] * 5
    assert len(om_module._CACHE_CURRENT._failure_cache) == 0
    assert om.call_count == 1
    with as_client("bob"):
        assert await get_current(*_cell(1)) is not None


async def test_b8_a_half_refused_multi_model_forecast_is_not_cached_and_another_client_gets_both_models(
    om, counted, set_caps
):
    set_caps(client=1)
    om.mock(return_value=httpx.Response(200, json=_DAILY_EXT_PAYLOAD))
    with as_client("alice"):
        assert await get_multi_model_daily(*_cell(0)) is None  # one model fetched, the other refused

    assert len(om_module._CACHE_FORECAST._failure_cache) == 0
    with as_client("bob"):
        both = await get_multi_model_daily(*_cell(0))
    assert both is not None
    assert set(both.models) == {"gfs_seamless", "ecmwf_ifs025"}  # a degraded copy was not served from the cache


async def test_b8_a_real_upstream_failure_is_still_remembered_for_the_failure_ttl(om, counted):
    om.mock(return_value=httpx.Response(404))
    assert await get_current(*_cell(0)) is None
    calls_before = om.call_count

    assert await get_current(*_cell(0)) is None

    assert om.call_count == calls_before  # served from the failure cache: no new network call
    assert len(om_module._CACHE_CURRENT._failure_cache) == 1


# ---------------------------------------------------------------------------
# B9 - a refused probe does not hold the half-open slot
# ---------------------------------------------------------------------------

async def test_b9_a_refused_probe_does_not_block_the_next_caller(om, counted, set_caps):
    set_caps(client=1)
    pause_clock = FakeClock()
    pause.clock = pause_clock
    with as_client("alice"):
        assert await get_current(*_cell(0)) is not None  # her only token
    pause.trip()
    pause_clock.advance(120)

    with as_client("alice"):
        assert await get_current(*_cell(1)) is None  # takes the probe slot, then her share refuses her
    assert budget_refusals()["client"] == 1

    with as_client("bob"):
        assert await get_current(*_cell(2)) is not None  # bob is the probe and reopens the traffic
    assert om.call_count == 2
    assert pause.remaining() == 0.0


# ---------------------------------------------------------------------------
# B10 - the shared `unverified` key
# ---------------------------------------------------------------------------

async def test_b10_the_unverified_key_gets_half_the_global_cap_and_others_keep_their_share(om, counted):
    with as_client(UNVERIFIED_CLIENT_KEY):
        results = await _calls(46)
    assert _succeeded(results) == [True] * 45 + [False]  # 90 // 2

    with as_client("alice"):
        results = await _calls(13, start=100)
    assert _succeeded(results) == [True] * 12 + [False]


async def test_b10_the_unverified_key_is_still_bounded_by_the_global_bucket(om, counted, set_caps):
    set_caps(client=3, overall=10)  # unverified share = max(10 // 2, 3) = 5
    with as_client(UNVERIFIED_CLIENT_KEY):
        results = await _calls(6)
    assert _succeeded(results) == [True] * 5 + [False]
    with as_client("alice"):
        assert all(_succeeded(await _calls(3, start=10)))  # global: 8 of 10 used
    with as_client("bob"):
        results = await _calls(3, start=20)

    assert _succeeded(results) == [True, True, False]
    assert budget_refusals()["global"] == 1


async def test_b10_the_unverified_share_is_never_below_the_ordinary_one(om, counted, set_caps):
    set_caps(client=8, overall=10)  # 10 // 2 = 5 would be less than an ordinary client's 8
    with as_client(UNVERIFIED_CLIENT_KEY):
        results = await _calls(9)

    assert _succeeded(results) == [True] * 8 + [False]


async def test_b10_the_unknown_key_is_an_ordinary_client(om, counted):
    with as_client("unknown"):
        results = await _calls(13)

    assert _succeeded(results) == [True] * 12 + [False]
