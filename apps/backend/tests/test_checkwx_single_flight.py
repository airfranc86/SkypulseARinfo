"""CheckWX single-flight, success/failure caching and cache sizing.

F1 - N concurrent requests for one (kind, icao) share ONE upstream call and ONE quota unit.
F2 - Distinct stations still call upstream separately and in parallel.
F3 - A caller that goes away does not break or double-spend the shared call.
F4 - A failed fetch is remembered for the short failure TTL (no upstream call, no quota unit).
F5 - Success TTLs per kind; an expired copy is never served when CheckWX fails (no stale).
F6 - Cache sizes: ordinary traffic with many distinct stations does not evict itself.
F7 - One overall deadline bounds a flight; waiters get the failure and the unit follows the refund rules.
F8 - Flight lifecycle: a never-retrieved exception is consumed, a cancelled flight never poisons a station.
"""
from __future__ import annotations

import asyncio
import gc
import time
from functools import partial

import httpx
import pytest

from app.core.counter import MemoryCounter, current_cycle
from app.services import checkwx as checkwx_svc
from tests.conftest import FakeCheckWX, FakeClock, checkwx_payload
from tests.test_checkwx_quota_exact import YieldingCounter

pytestmark = pytest.mark.usefixtures("checkwx_counter", "checkwx_roomy_bucket")


async def _units(counter: MemoryCounter) -> int:
    return await counter.get(current_cycle())


# ---------------------------------------------------------------------------
# F1 - one call, one unit
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["metar", "taf"])
async def test_f1_concurrent_requests_for_one_station_make_one_call_and_one_unit(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter, kind: str
):
    checkwx_upstream.delay = 0.05

    results = await asyncio.gather(*(checkwx_svc.fetch_metar("SAEZ", kind=kind) for _ in range(25)))

    assert checkwx_upstream.count() == 1
    assert await _units(checkwx_counter) == 1
    assert all(r == checkwx_payload(kind, "SAEZ") for r in results)


async def test_f1_metar_and_taf_of_one_station_are_separate_flights(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter
):
    checkwx_upstream.delay = 0.02

    await asyncio.gather(
        checkwx_svc.fetch_metar("SAEZ", kind="metar"),
        checkwx_svc.fetch_metar("SAEZ", kind="taf"),
    )

    assert checkwx_upstream.count("metar", "SAEZ") == 1
    assert checkwx_upstream.count("taf", "SAEZ") == 1
    assert await _units(checkwx_counter) == 2


async def test_f1_a_finished_flight_is_forgotten_and_the_next_request_hits_the_cache(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter
):
    await asyncio.gather(*(checkwx_svc.fetch_metar("SAEZ", kind="metar") for _ in range(5)))
    await checkwx_svc.fetch_metar("SAEZ", kind="metar")

    assert checkwx_upstream.count() == 1
    assert await _units(checkwx_counter) == 1
    assert checkwx_svc._inflight == {}


# ---------------------------------------------------------------------------
# F2 - distinct stations
# ---------------------------------------------------------------------------

async def test_f2_distinct_stations_make_separate_parallel_calls(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter
):
    checkwx_upstream.delay = 0.05
    icaos = ["SAEZ", "SACO", "SAWH", "LEMD", "KJFK"]

    await asyncio.gather(*(checkwx_svc.fetch_metar(i, kind="metar") for i in icaos))

    assert sorted(i for _, i in checkwx_upstream.calls) == sorted(icaos)
    assert await _units(checkwx_counter) == len(icaos)
    assert checkwx_upstream.max_active == len(icaos)  # nothing serialised the network calls


# ---------------------------------------------------------------------------
# F3 - callers that go away
# ---------------------------------------------------------------------------

async def test_f3_cancelling_the_first_caller_does_not_break_the_shared_call(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter
):
    checkwx_upstream.delay = 0.05
    first = asyncio.create_task(checkwx_svc.fetch_metar("SAEZ", kind="metar"))
    await asyncio.sleep(0.01)
    second = asyncio.create_task(checkwx_svc.fetch_metar("SAEZ", kind="metar"))
    await asyncio.sleep(0.01)

    first.cancel()
    result = await second

    assert result == checkwx_payload("metar", "SAEZ")
    assert checkwx_upstream.count() == 1
    assert await _units(checkwx_counter) == 1


async def test_f3_when_every_caller_goes_away_the_call_still_lands_in_the_cache(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter
):
    checkwx_upstream.delay = 0.03
    caller = asyncio.create_task(checkwx_svc.fetch_metar("SAEZ", kind="metar"))
    await asyncio.sleep(0.01)
    caller.cancel()
    await asyncio.sleep(0.1)  # the detached call finishes on its own

    result = await checkwx_svc.fetch_metar("SAEZ", kind="metar")

    assert result == checkwx_payload("metar", "SAEZ")
    assert checkwx_upstream.count() == 1  # the spent unit was not wasted
    assert await _units(checkwx_counter) == 1


# ---------------------------------------------------------------------------
# F4 - failures are remembered briefly
# ---------------------------------------------------------------------------

async def test_f4_concurrent_requests_share_one_failed_call(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter
):
    checkwx_upstream.delay = 0.03
    checkwx_upstream.set("SAEZ", 503)

    results = await asyncio.gather(
        *(checkwx_svc.fetch_metar("SAEZ", kind="metar") for _ in range(10)), return_exceptions=True
    )

    assert checkwx_upstream.count() == 1
    assert all(isinstance(r, checkwx_svc.CheckWXUnavailableError) for r in results)


async def test_f4_a_failure_is_remembered_for_the_failure_ttl_then_retried(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter, checkwx_clock: FakeClock
):
    checkwx_upstream.set("SAEZ", 500)
    with pytest.raises(checkwx_svc.CheckWXUnavailableError):
        await checkwx_svc.fetch_metar("SAEZ", kind="metar")
    assert checkwx_upstream.count() == 1

    # Within the failure TTL: no upstream call and no quota unit, still a 503-type error.
    checkwx_clock.advance(checkwx_svc.settings.checkwx_failure_ttl_seconds - 1)
    with pytest.raises(checkwx_svc.CheckWXUnavailableError):
        await checkwx_svc.fetch_metar("SAEZ", kind="metar")
    assert checkwx_upstream.count() == 1
    assert await _units(checkwx_counter) == 0

    # After it: CheckWX is tried again, and recovery shows immediately.
    checkwx_clock.advance(2)
    checkwx_upstream.set("SAEZ", 200)
    result = await checkwx_svc.fetch_metar("SAEZ", kind="metar")
    assert result == checkwx_payload("metar", "SAEZ")
    assert checkwx_upstream.count() == 2
    assert await _units(checkwx_counter) == 1


async def test_f4_a_failure_does_not_block_other_stations_or_the_other_kind(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter
):
    checkwx_upstream.set("SAEZ", 500)
    with pytest.raises(checkwx_svc.CheckWXUnavailableError):
        await checkwx_svc.fetch_metar("SAEZ", kind="metar")

    assert await checkwx_svc.fetch_metar("SAEZ", kind="taf") == checkwx_payload("taf", "SAEZ")
    assert await checkwx_svc.fetch_metar("SACO", kind="metar") == checkwx_payload("metar", "SACO")


async def test_f4_failure_ttl_default_and_wiring():
    # The frontend retry policy (lib/loadError.ts, lib/retryPolicy.ts) assumes a 15 s failure window.
    assert checkwx_svc.settings.checkwx_failure_ttl_seconds == 15
    assert checkwx_svc._failures.ttl == checkwx_svc.settings.checkwx_failure_ttl_seconds


# ---------------------------------------------------------------------------
# F5 - success TTL and no stale copies
# ---------------------------------------------------------------------------

async def test_f5_success_ttl_is_per_kind(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter, checkwx_clock: FakeClock
):
    metar_ttl = checkwx_svc.settings.cache_ttl_metar_seconds
    taf_ttl = checkwx_svc.settings.cache_ttl_taf_seconds
    assert metar_ttl < taf_ttl
    await checkwx_svc.fetch_metar("SAEZ", kind="metar")
    await checkwx_svc.fetch_metar("SAEZ", kind="taf")

    checkwx_clock.advance(metar_ttl - 1)
    await checkwx_svc.fetch_metar("SAEZ", kind="metar")
    await checkwx_svc.fetch_metar("SAEZ", kind="taf")
    assert checkwx_upstream.count() == 2  # both still cached

    checkwx_clock.advance(2)  # METAR expired, TAF not yet
    await checkwx_svc.fetch_metar("SAEZ", kind="metar")
    await checkwx_svc.fetch_metar("SAEZ", kind="taf")
    assert checkwx_upstream.count("metar") == 2
    assert checkwx_upstream.count("taf") == 1

    checkwx_clock.advance(taf_ttl)
    await checkwx_svc.fetch_metar("SAEZ", kind="taf")
    assert checkwx_upstream.count("taf") == 2


async def test_f5_an_expired_copy_is_never_served_when_checkwx_fails(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter, checkwx_clock: FakeClock
):
    """Decision: no stale-while-error. A METAR older than its TTL is gone; the caller gets the 503 path."""
    await checkwx_svc.fetch_metar("SAEZ", kind="metar")
    checkwx_clock.advance(checkwx_svc.settings.cache_ttl_metar_seconds + 1)
    checkwx_upstream.set("SAEZ", 500)

    with pytest.raises(checkwx_svc.CheckWXUnavailableError):
        await checkwx_svc.fetch_metar("SAEZ", kind="metar")


async def test_f5_timeout_and_network_errors_surface_as_unavailable(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter
):
    checkwx_upstream.set("SAEZ", httpx.ReadTimeout("slow"))
    checkwx_upstream.set("SACO", httpx.ConnectError("down"))

    for icao in ("SAEZ", "SACO"):
        with pytest.raises(checkwx_svc.CheckWXUnavailableError):
            await checkwx_svc.fetch_metar(icao, kind="metar")


# ---------------------------------------------------------------------------
# F6 - cache sizes
# ---------------------------------------------------------------------------

async def test_f6_cache_sizes():
    assert checkwx_svc._metar_cache.maxsize == 256
    assert checkwx_svc._taf_cache.maxsize == 128


@pytest.mark.parametrize("kind, stations", [("metar", 200), ("taf", 100)])
async def test_f6_many_distinct_stations_do_not_evict_each_other(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter, monkeypatch, kind: str, stations: int
):
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "checkwx_daily_limit", 10_000, raising=False)
    icaos = [f"A{n:03d}" for n in range(stations)]

    for icao in icaos:
        await checkwx_svc.fetch_metar(icao, kind=kind)
    assert checkwx_upstream.count() == stations

    for icao in icaos:  # second pass: every station is still cached
        await checkwx_svc.fetch_metar(icao, kind=kind)
    assert checkwx_upstream.count() == stations
    assert await _units(checkwx_counter) == stations


# ---------------------------------------------------------------------------
# F7 - overall deadline
# ---------------------------------------------------------------------------

async def test_f7_a_request_that_never_comes_back_is_cut_by_the_deadline_and_the_unit_stays_spent(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter, monkeypatch
):
    """The request was already out when the deadline hit: CheckWX may have accepted it, so it is counted."""
    monkeypatch.setattr(checkwx_svc.settings, "checkwx_flight_deadline_seconds", 0.05, raising=False)
    checkwx_upstream.delay = 0.5
    started = time.monotonic()

    results = await asyncio.gather(
        *(checkwx_svc.fetch_metar("SAEZ", kind="metar") for _ in range(5)), return_exceptions=True
    )

    assert time.monotonic() - started < 0.4
    assert all(isinstance(r, checkwx_svc.CheckWXUnavailableError) for r in results)  # waiters get it too
    assert await _units(checkwx_counter) == 1
    assert checkwx_upstream.active == 0  # the abandoned request was cancelled, not left running
    with pytest.raises(checkwx_svc.CheckWXUnavailableError):  # and it is remembered like any failure
        await checkwx_svc.fetch_metar("SAEZ", kind="metar")
    assert checkwx_upstream.count() == 1


async def test_f7_a_slow_counter_is_cut_by_the_deadline_and_nothing_is_spent(
    checkwx_upstream: FakeCheckWX, monkeypatch
):
    monkeypatch.setattr(checkwx_svc.settings, "checkwx_flight_deadline_seconds", 0.05, raising=False)
    monkeypatch.setattr(checkwx_svc.settings, "checkwx_new_calls_per_minute", 1, raising=False)
    counter = YieldingCounter()
    counter.incr_delay = 0.5
    checkwx_svc.set_counter(counter)

    with pytest.raises(checkwx_svc.CheckWXUnavailableError):
        await checkwx_svc.fetch_metar("SAEZ", kind="metar")

    assert checkwx_upstream.count() == 0  # never reached CheckWX
    assert await _units(counter) == 0
    counter.incr_delay = 0.0
    # The one token of the global bucket came back with the cut flight.
    assert await checkwx_svc.fetch_metar("SACO", kind="metar") == checkwx_payload("metar", "SACO")


async def test_f7_the_deadline_leaves_room_for_the_http_timeout():
    assert checkwx_svc.settings.checkwx_flight_deadline_seconds == 20
    assert checkwx_svc.settings.checkwx_flight_deadline_seconds > checkwx_svc.settings.metar_timeout_seconds


# ---------------------------------------------------------------------------
# F8 - flight lifecycle
# ---------------------------------------------------------------------------

async def test_f8_a_failed_flight_nobody_awaits_leaves_no_never_retrieved_exception(
    checkwx_upstream: FakeCheckWX
):
    loop = asyncio.get_running_loop()
    reports: list[dict] = []
    loop.set_exception_handler(lambda _loop, context: reports.append(context))
    checkwx_upstream.set("SAEZ", 500)
    checkwx_upstream.delay = 0.02

    caller = asyncio.create_task(checkwx_svc.fetch_metar("SAEZ", kind="metar"))
    await asyncio.sleep(0)
    caller.cancel()  # the only requester goes away; the flight keeps going and fails
    with pytest.raises(asyncio.CancelledError):
        await caller
    await asyncio.sleep(0.1)
    del caller
    gc.collect()
    await asyncio.sleep(0)

    assert checkwx_upstream.count() == 1
    assert [r for r in reports if "never retrieved" in r.get("message", "")] == []


async def test_f8_a_flight_cancelled_before_it_starts_does_not_poison_the_station(
    checkwx_upstream: FakeCheckWX
):
    caller = asyncio.create_task(checkwx_svc.fetch_metar("SAEZ", kind="metar"))
    await asyncio.sleep(0)  # the flight exists but has not run a single step
    checkwx_svc._inflight[("metar", "SAEZ")].cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert checkwx_svc._inflight == {}  # without the cleanup this dead task would answer every request
    assert await checkwx_svc.fetch_metar("SAEZ", kind="metar") == checkwx_payload("metar", "SAEZ")


async def test_f8_consume_exception_marks_a_failed_task_as_retrieved_and_tolerates_a_cancelled_one():
    loop = asyncio.get_running_loop()
    reports: list[dict] = []
    loop.set_exception_handler(lambda _loop, context: reports.append(context))
    key = ("metar", "SAEZ")

    async def boom() -> dict:
        raise checkwx_svc.CheckWXUnavailableError("down")

    failed = asyncio.create_task(boom())  # nobody awaits it and nothing shields it
    failed.add_done_callback(partial(checkwx_svc._consume_exception, key))
    sleeper = asyncio.create_task(asyncio.sleep(10))
    sleeper.cancel()
    await asyncio.wait([failed, sleeper])
    checkwx_svc._consume_exception(key, sleeper)  # a cancelled task has no exception to read: no error
    del failed, sleeper
    gc.collect()
    await asyncio.sleep(0)

    assert [r for r in reports if "never retrieved" in r.get("message", "")] == []


async def test_f8_consume_exception_only_drops_its_own_flight():
    async def done() -> dict:
        return {}

    old = asyncio.create_task(done())
    newer = asyncio.create_task(done())
    await asyncio.gather(old, newer)
    key = ("metar", "SAEZ")
    checkwx_svc._inflight[key] = newer

    checkwx_svc._consume_exception(key, old)
    assert checkwx_svc._inflight[key] is newer  # a newer flight for the same station stays

    checkwx_svc._consume_exception(key, newer)
    assert key not in checkwx_svc._inflight
