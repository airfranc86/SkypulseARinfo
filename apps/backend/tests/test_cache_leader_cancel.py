"""`SingleFlightCache`: when the leader of a shared flight is cancelled, the callers waiting for it retry.

A client that closes its connection cancels the task that was leading the flight. The callers of OTHER
clients that were waiting for the same key must not be handed `None` (the leader produced nothing): one of
them leads a new flight and the rest wait for that one. The cancellation itself only reaches the leader.
Everything else (success, failure, `FetchRefused`, stale copy) is untouched.
"""
from __future__ import annotations

import asyncio

import pytest

from app.core.cache import CacheOutcome, FetchRefused, SingleFlightCache


def _cache() -> SingleFlightCache[str]:
    return SingleFlightCache(maxsize=8, ttl=60, failure_ttl=15, name="leader_cancel_test")


async def _let_tasks_run(rounds: int = 5) -> None:
    for _ in range(rounds):
        await asyncio.sleep(0)


class _Flights:
    """A fetch whose first `blocking` calls never finish by themselves and the next ones return `value`."""

    def __init__(self, blocking: int, value: str = "fresh") -> None:
        self.blocking = blocking
        self.value = value
        self.calls = 0
        self.running: asyncio.Task | None = None
        self.started = asyncio.Event()

    async def fetch(self) -> str:
        self.calls += 1
        self.running = asyncio.current_task()
        self.started.set()
        if self.calls <= self.blocking:
            await asyncio.Event().wait()   # until cancelled
        return self.value


async def test_a_waiter_retries_when_the_leader_is_cancelled_and_does_not_get_none() -> None:
    cache = _cache()
    flights = _Flights(blocking=1)
    leader = asyncio.create_task(cache.get_or_fetch("k", flights.fetch))
    await flights.started.wait()
    waiter = asyncio.create_task(cache.get_or_fetch("k", flights.fetch))
    await _let_tasks_run()

    leader.cancel()

    assert await waiter == "fresh"
    assert flights.calls == 2


async def test_the_cancellation_reaches_only_the_leader() -> None:
    cache = _cache()
    flights = _Flights(blocking=1)
    leader = asyncio.create_task(cache.get_or_fetch("k", flights.fetch))
    await flights.started.wait()
    waiter = asyncio.create_task(cache.get_or_fetch("k", flights.fetch))
    await _let_tasks_run()

    leader.cancel()
    await waiter

    with pytest.raises(asyncio.CancelledError):
        await leader
    assert leader.cancelled()
    assert not waiter.cancelled()


async def test_many_waiters_share_the_one_new_flight() -> None:
    cache = _cache()
    flights = _Flights(blocking=1)
    leader = asyncio.create_task(cache.get_or_fetch("k", flights.fetch))
    await flights.started.wait()
    waiters = [asyncio.create_task(cache.get_or_fetch("k", flights.fetch)) for _ in range(4)]
    await _let_tasks_run()

    leader.cancel()
    results = await asyncio.gather(*waiters)

    assert results == ["fresh"] * 4
    assert flights.calls == 2   # the cancelled flight and ONE new one, not one per waiter


async def test_a_cancelled_flight_leaves_no_trace_of_a_failure() -> None:
    cache = _cache()
    flights = _Flights(blocking=1)
    leader = asyncio.create_task(cache.get_or_fetch("k", flights.fetch))
    await flights.started.wait()
    leader.cancel()
    with pytest.raises(asyncio.CancelledError):
        await leader

    assert len(cache._failure_cache) == 0
    assert cache.stats()["fetches"] == 0
    assert await cache.get_or_fetch("k", flights.fetch) == "fresh"   # the key is free to be fetched again


async def test_a_flight_cancelled_with_no_waiters_is_forgotten() -> None:
    cache = _cache()
    flights = _Flights(blocking=1)
    leader = asyncio.create_task(cache.get_or_fetch("k", flights.fetch))
    await flights.started.wait()
    leader.cancel()
    with pytest.raises(asyncio.CancelledError):
        await leader

    assert cache._inflight == {}


async def test_the_waiters_report_a_fetch_and_not_a_cache_hit_after_the_retry() -> None:
    cache = _cache()
    flights = _Flights(blocking=1)
    leader = asyncio.create_task(cache.get_or_fetch("k", flights.fetch))
    await flights.started.wait()
    outcome = CacheOutcome()
    waiter = asyncio.create_task(cache.get_or_fetch("k", flights.fetch, outcome=outcome))
    await _let_tasks_run()

    leader.cancel()
    await waiter

    assert outcome.hit is False


async def test_the_retried_value_is_cached_for_the_next_caller() -> None:
    cache = _cache()
    flights = _Flights(blocking=1)
    leader = asyncio.create_task(cache.get_or_fetch("k", flights.fetch))
    await flights.started.wait()
    waiter = asyncio.create_task(cache.get_or_fetch("k", flights.fetch))
    await _let_tasks_run()
    leader.cancel()
    await waiter
    calls = flights.calls

    assert await cache.get_or_fetch("k", flights.fetch) == "fresh"
    assert flights.calls == calls


async def test_if_the_new_leader_is_cancelled_too_the_next_waiter_retries_again() -> None:
    cache = _cache()
    flights = _Flights(blocking=2)
    leader = asyncio.create_task(cache.get_or_fetch("k", flights.fetch))
    await flights.started.wait()
    waiters = [asyncio.create_task(cache.get_or_fetch("k", flights.fetch)) for _ in range(2)]
    await _let_tasks_run()

    leader.cancel()
    await _let_tasks_run()
    assert flights.calls == 2          # one waiter now leads the second flight
    flights.running.cancel()           # ... and it is cancelled as well
    await _let_tasks_run()

    done = [task for task in waiters if not task.cancelled() and task.done()]
    cancelled = [task for task in waiters if task.cancelled()]
    assert len(cancelled) == 1 and len(done) == 1
    assert done[0].result() == "fresh"
    assert flights.calls == 3


async def test_a_waiter_that_is_itself_cancelled_does_not_disturb_the_flight() -> None:
    cache = _cache()
    gate = asyncio.Event()
    calls = 0

    async def fetch() -> str:
        nonlocal calls
        calls += 1
        await gate.wait()
        return "value"

    leader = asyncio.create_task(cache.get_or_fetch("k", fetch))
    await _let_tasks_run()
    waiter = asyncio.create_task(cache.get_or_fetch("k", fetch))
    await _let_tasks_run()

    waiter.cancel()
    gate.set()

    assert await leader == "value"
    assert calls == 1


# --- nothing else changed -------------------------------------------------------------------------

async def test_a_failing_fetch_still_reaches_the_waiters_as_the_same_error() -> None:
    cache = _cache()
    gate = asyncio.Event()

    async def boom() -> str:
        await gate.wait()
        raise ValueError("upstream broke")

    tasks = [asyncio.create_task(cache.get_or_fetch("k", boom)) for _ in range(3)]
    await _let_tasks_run()
    gate.set()
    results = await asyncio.gather(*tasks, return_exceptions=True)

    assert all(isinstance(result, ValueError) for result in results)
    assert len(cache._failure_cache) == 1


async def test_a_none_result_is_still_shared_and_remembered_as_a_failure() -> None:
    cache = _cache()
    gate = asyncio.Event()
    calls = 0

    async def nothing() -> str | None:
        nonlocal calls
        calls += 1
        await gate.wait()
        return None

    tasks = [asyncio.create_task(cache.get_or_fetch("k", nothing)) for _ in range(3)]
    await _let_tasks_run()
    gate.set()

    assert await asyncio.gather(*tasks) == [None, None, None]
    assert calls == 1
    assert len(cache._failure_cache) == 1


async def test_a_refusal_still_reaches_the_waiters_and_is_not_remembered() -> None:
    cache = _cache()
    gate = asyncio.Event()

    async def refused() -> str:
        await gate.wait()
        raise FetchRefused("no budget")

    tasks = [asyncio.create_task(cache.get_or_fetch("k", refused)) for _ in range(3)]
    await _let_tasks_run()
    gate.set()
    results = await asyncio.gather(*tasks, return_exceptions=True)

    assert all(isinstance(result, FetchRefused) for result in results)
    assert len(cache._failure_cache) == 0


async def test_a_stale_copy_is_still_served_to_every_caller_when_the_fetch_fails() -> None:
    cache = _cache()
    assert await cache.get_or_fetch("k", _Flights(blocking=0, value="old").fetch) == "old"
    cache._cache.clear()   # the fresh copy expired; the stale one stays
    gate = asyncio.Event()

    async def boom() -> str:
        await gate.wait()
        raise ValueError("down")

    tasks = [asyncio.create_task(cache.get_or_fetch("k", boom)) for _ in range(3)]
    await _let_tasks_run()
    gate.set()

    assert await asyncio.gather(*tasks) == ["old"] * 3


async def test_a_second_cancellation_while_the_leader_waits_for_the_lock_leaves_no_phantom_flight() -> None:
    cache = _cache()
    flights = _Flights(blocking=1)
    leader = asyncio.create_task(cache.get_or_fetch("k", flights.fetch))
    await flights.started.wait()
    waiter = asyncio.create_task(cache.get_or_fetch("k", flights.fetch))
    await _let_tasks_run()

    await cache._lock.acquire()          # somebody else holds the lock while the leader is being cancelled
    try:
        leader.cancel()
        await _let_tasks_run()
        leader.cancel()                   # a SECOND cancellation, while the leader is still finishing
        await _let_tasks_run()
    finally:
        cache._lock.release()

    with pytest.raises(asyncio.CancelledError):
        await leader
    assert await asyncio.wait_for(waiter, timeout=2.0) == "fresh"      # the waiter retried instead of hanging
    assert await asyncio.wait_for(cache.get_or_fetch("k", flights.fetch), timeout=2.0) == "fresh"
    assert cache._inflight == {}


async def test_a_double_cancelled_leader_with_no_waiters_does_not_block_the_key() -> None:
    cache = _cache()
    flights = _Flights(blocking=1)
    leader = asyncio.create_task(cache.get_or_fetch("k", flights.fetch))
    await flights.started.wait()

    await cache._lock.acquire()
    try:
        leader.cancel()
        await _let_tasks_run()
        leader.cancel()
        await _let_tasks_run()
    finally:
        cache._lock.release()
    with pytest.raises(asyncio.CancelledError):
        await leader

    assert await asyncio.wait_for(cache.get_or_fetch("k", flights.fetch), timeout=2.0) == "fresh"
