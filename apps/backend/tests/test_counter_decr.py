"""Quota counter `decr`: how a reserved CheckWX unit is given back.

D1 - MemoryCounter: decr lowers the count, returns the new value, never goes below zero.
D2 - MemoryCounter: cycles stay independent; concurrent incr/decr balance out.
D3 - RedisCounter: DECR goes to the right key (default and custom namespace), no EXPIRE.
D4 - RedisCounter: Upstash down or odd answers degrade to 0 instead of raising.
D5 - Both counters floor at zero: a negative DECR is repaired in Redis (INCR back, key given a TTL).
"""
from __future__ import annotations

import asyncio

import httpx
import pytest
import respx
from httpx import Response

from app.core.counter import MemoryCounter, RedisCounter
from app.core.upstash import UpstashRedis

_FAKE_URL = "https://fake-upstash.io"
_CYCLE = "2026-06"
_KEY = f"skypulse:checkwx:counter:{_CYCLE}"
_DECR_URL = f"{_FAKE_URL}/DECR/{_KEY}"
_INCR_URL = f"{_FAKE_URL}/INCR/{_KEY}"
_EXPIRE_PREFIX = f"{_FAKE_URL}/EXPIRE/{_KEY}/"


@pytest.fixture
def mem() -> MemoryCounter:
    return MemoryCounter()


@pytest.fixture
def redis_counter() -> RedisCounter:
    return RedisCounter(UpstashRedis(_FAKE_URL, "test-token"))


# ---------------------------------------------------------------------------
# D1 / D2 - MemoryCounter
# ---------------------------------------------------------------------------

async def test_d1_memory_decr_lowers_the_count_and_returns_it(mem: MemoryCounter):
    for _ in range(3):
        await mem.incr(_CYCLE)

    assert await mem.decr(_CYCLE) == 2
    assert await mem.get(_CYCLE) == 2


async def test_d1_memory_decr_never_goes_below_zero(mem: MemoryCounter):
    assert await mem.decr(_CYCLE) == 0
    assert await mem.get(_CYCLE) == 0


async def test_d2_memory_decr_keeps_cycles_independent(mem: MemoryCounter):
    await mem.incr("2026-06")
    await mem.incr("2026-07")
    await mem.incr("2026-07")

    await mem.decr("2026-07")

    assert await mem.get("2026-06") == 1
    assert await mem.get("2026-07") == 1


async def test_d2_memory_concurrent_incr_and_decr_balance_out(mem: MemoryCounter):
    for _ in range(50):
        await mem.incr(_CYCLE)
    await asyncio.gather(
        *[mem.incr(_CYCLE) for _ in range(50)],
        *[mem.decr(_CYCLE) for _ in range(50)],
    )
    assert await mem.get(_CYCLE) == 50


# ---------------------------------------------------------------------------
# D3 - RedisCounter: REST endpoint
# ---------------------------------------------------------------------------

async def test_d3_redis_decr_calls_decr_on_the_counter_key(redis_counter: RedisCounter):
    with respx.mock(assert_all_called=False) as router:
        decr_route = router.post(_DECR_URL).mock(return_value=Response(200, json={"result": 4}))
        expire_route = router.post(url__startswith=f"{_FAKE_URL}/EXPIRE/").mock(
            return_value=Response(200, json={"result": 1})
        )
        result = await redis_counter.decr(_CYCLE)

    assert result == 4
    assert decr_route.called
    assert not expire_route.called


async def test_d3_redis_decr_honours_the_namespace():
    counter = RedisCounter(UpstashRedis(_FAKE_URL, "test-token"), namespace="other")
    with respx.mock(assert_all_called=False) as router:
        route = router.post(f"{_FAKE_URL}/DECR/skypulse:other:counter:{_CYCLE}").mock(
            return_value=Response(200, json={"result": 0})
        )
        await counter.decr(_CYCLE)

    assert route.called


# ---------------------------------------------------------------------------
# D4 - RedisCounter: degraded Upstash must not raise
# ---------------------------------------------------------------------------

async def test_d4_redis_decr_degrades_to_zero_when_upstash_is_down(redis_counter: RedisCounter):
    with respx.mock(assert_all_called=False) as router:
        router.post(_DECR_URL).mock(side_effect=httpx.ConnectError("Name or service not known"))
        assert await redis_counter.decr(_CYCLE) == 0


async def test_d4_redis_decr_degrades_to_zero_on_an_upstash_error_status(redis_counter: RedisCounter):
    with respx.mock(assert_all_called=False) as router:
        router.post(_DECR_URL).mock(return_value=Response(500, json={"error": "boom"}))
        assert await redis_counter.decr(_CYCLE) == 0


async def test_d4_redis_decr_degrades_to_zero_on_an_unexpected_answer(redis_counter: RedisCounter):
    with respx.mock(assert_all_called=False) as router:
        router.post(_DECR_URL).mock(return_value=Response(200, json={"result": None}))
        assert await redis_counter.decr(_CYCLE) == 0


# ---------------------------------------------------------------------------
# D5 - floor at zero in both implementations
# ---------------------------------------------------------------------------

async def test_d5_redis_decr_repairs_a_negative_result(redis_counter: RedisCounter):
    """The key was gone (expired at midnight, evicted): DECR created it at -1 with no TTL."""
    with respx.mock(assert_all_called=False) as router:
        router.post(_DECR_URL).mock(return_value=Response(200, json={"result": -1}))
        incr_route = router.post(_INCR_URL).mock(return_value=Response(200, json={"result": 0}))
        expire_route = router.post(url__startswith=_EXPIRE_PREFIX).mock(
            return_value=Response(200, json={"result": 1})
        )
        result = await redis_counter.decr(_CYCLE)

    assert result == 0
    assert incr_route.call_count == 1  # back to zero
    assert expire_route.call_count == 1  # and it can no longer live forever
    ttl = int(expire_route.calls.last.request.url.path.rsplit("/", 1)[-1])
    assert 1 <= ttl <= 86_400


async def test_d5_redis_decr_leaves_a_non_negative_result_alone(redis_counter: RedisCounter):
    with respx.mock(assert_all_called=False) as router:
        router.post(_DECR_URL).mock(return_value=Response(200, json={"result": 0}))
        incr_route = router.post(_INCR_URL).mock(return_value=Response(200, json={"result": 1}))
        expire_route = router.post(url__startswith=_EXPIRE_PREFIX).mock(
            return_value=Response(200, json={"result": 1})
        )
        assert await redis_counter.decr(_CYCLE) == 0

    assert not incr_route.called and not expire_route.called


@pytest.mark.parametrize("broken", ["incr", "expire"])
async def test_d5_a_failing_repair_never_raises(redis_counter: RedisCounter, broken: str):
    with respx.mock(assert_all_called=False) as router:
        router.post(_DECR_URL).mock(return_value=Response(200, json={"result": -1}))
        down = httpx.ConnectError("Name or service not known")
        if broken == "incr":
            router.post(_INCR_URL).mock(side_effect=down)
        else:
            router.post(_INCR_URL).mock(return_value=Response(200, json={"result": 0}))
            router.post(url__startswith=_EXPIRE_PREFIX).mock(side_effect=down)
        assert await redis_counter.decr(_CYCLE) == 0


async def test_d5_both_counters_report_zero_when_there_was_nothing_to_give_back(
    mem: MemoryCounter, redis_counter: RedisCounter
):
    with respx.mock(assert_all_called=False) as router:
        router.post(_DECR_URL).mock(return_value=Response(200, json={"result": -1}))
        router.post(_INCR_URL).mock(return_value=Response(200, json={"result": 0}))
        router.post(url__startswith=_EXPIRE_PREFIX).mock(return_value=Response(200, json={"result": 1}))
        assert await redis_counter.decr(_CYCLE) == await mem.decr(_CYCLE) == 0

