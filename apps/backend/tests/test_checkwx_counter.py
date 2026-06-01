"""Tests del counter de cuota CheckWX.

C1 — MemoryCounter: 100 incr() concurrentes → resultado = 100, sin race condition
C2 — MemoryCounter: get() sobre ciclo inexistente → 0
C3 — MemoryCounter: dos ciclos independientes no se contaminan
C4 — MemoryCounter: flag de alerta — False antes de marcar, True después (idempotente)
C5 — RedisCounter: lecturas/escrituras van al endpoint REST correcto (respx mock)
"""
from __future__ import annotations

import asyncio

import pytest
import respx
from httpx import Response

from app.core.counter import MemoryCounter, RedisCounter
from app.core.upstash import UpstashRedis

_FAKE_URL = "https://fake-upstash.io"
_FAKE_TOKEN = "test-token"
_CYCLE = "2026-06"
_COUNTER_KEY = f"skypulse:checkwx:counter:{_CYCLE}"
_ALERT_KEY_80 = f"skypulse:checkwx:alert:{_CYCLE}:80"


@pytest.fixture
def mem() -> MemoryCounter:
    return MemoryCounter()


@pytest.fixture
def redis_counter() -> RedisCounter:
    redis = UpstashRedis(_FAKE_URL, _FAKE_TOKEN)
    return RedisCounter(redis)


# ---------------------------------------------------------------------------
# C1 — concurrencia
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_c1_concurrent_incr_no_race(mem: MemoryCounter):
    """100 incr() concurrentes deben sumar exactamente 100 sin race condition."""
    await asyncio.gather(*[mem.incr(_CYCLE) for _ in range(100)])
    assert await mem.get(_CYCLE) == 100


# ---------------------------------------------------------------------------
# C2 — ciclo inexistente
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_c2_get_unknown_cycle_returns_zero(mem: MemoryCounter):
    assert await mem.get("2099-01") == 0


# ---------------------------------------------------------------------------
# C3 — ciclos independientes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_c3_cycles_are_independent(mem: MemoryCounter):
    """Incrementos en ciclos distintos no se mezclan."""
    for _ in range(3):
        await mem.incr("2026-06")
    for _ in range(7):
        await mem.incr("2026-07")

    assert await mem.get("2026-06") == 3
    assert await mem.get("2026-07") == 7


# ---------------------------------------------------------------------------
# C4 — flag de alerta
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_c4_alert_flag_false_before_mark(mem: MemoryCounter):
    assert await mem.alert_already_sent(_CYCLE, 80) is False


@pytest.mark.asyncio
async def test_c4_alert_flag_true_after_mark(mem: MemoryCounter):
    await mem.mark_alert_sent(_CYCLE, 80, ttl_seconds=86400)
    assert await mem.alert_already_sent(_CYCLE, 80) is True


@pytest.mark.asyncio
async def test_c4_alert_flag_idempotent(mem: MemoryCounter):
    """mark_alert_sent() dos veces no lanza excepción y el flag sigue en True."""
    await mem.mark_alert_sent(_CYCLE, 80, ttl_seconds=86400)
    await mem.mark_alert_sent(_CYCLE, 80, ttl_seconds=86400)
    assert await mem.alert_already_sent(_CYCLE, 80) is True


@pytest.mark.asyncio
async def test_c4_different_thresholds_are_independent(mem: MemoryCounter):
    """Marcar 80% no afecta el flag de 95%."""
    await mem.mark_alert_sent(_CYCLE, 80, ttl_seconds=86400)
    assert await mem.alert_already_sent(_CYCLE, 95) is False


# ---------------------------------------------------------------------------
# C5 — RedisCounter: endpoints REST correctos
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_c5_get_returns_zero_when_key_missing(redis_counter: RedisCounter):
    """GET sobre clave inexistente (Redis devuelve null) → 0."""
    with respx.mock:
        respx.post(f"{_FAKE_URL}/GET/{_COUNTER_KEY}").mock(
            return_value=Response(200, json={"result": None})
        )
        result = await redis_counter.get(_CYCLE)
    assert result == 0


@pytest.mark.asyncio
async def test_c5_get_returns_stored_value(redis_counter: RedisCounter):
    with respx.mock:
        respx.post(f"{_FAKE_URL}/GET/{_COUNTER_KEY}").mock(
            return_value=Response(200, json={"result": "47"})
        )
        result = await redis_counter.get(_CYCLE)
    assert result == 47


@pytest.mark.asyncio
async def test_c5_incr_first_call_sets_expire(redis_counter: RedisCounter):
    """Primera llamada a incr() (result=1) debe llamar EXPIRE."""
    with respx.mock:
        incr_route = respx.post(f"{_FAKE_URL}/INCR/{_COUNTER_KEY}").mock(
            return_value=Response(200, json={"result": 1})
        )
        expire_route = respx.post(url__startswith=f"{_FAKE_URL}/EXPIRE/").mock(
            return_value=Response(200, json={"result": 1})
        )
        result = await redis_counter.incr(_CYCLE)

    assert result == 1
    assert incr_route.called
    assert expire_route.called


@pytest.mark.asyncio
async def test_c5_incr_subsequent_call_no_expire(redis_counter: RedisCounter):
    """Llamadas a incr() con result>1 NO deben llamar EXPIRE."""
    with respx.mock:
        respx.post(f"{_FAKE_URL}/INCR/{_COUNTER_KEY}").mock(
            return_value=Response(200, json={"result": 5})
        )
        expire_route = respx.post(url__startswith=f"{_FAKE_URL}/EXPIRE/").mock(
            return_value=Response(200, json={"result": 1})
        )
        await redis_counter.incr(_CYCLE)

    assert not expire_route.called


@pytest.mark.asyncio
async def test_c5_alert_already_sent_checks_correct_key(redis_counter: RedisCounter):
    """alert_already_sent() consulta la clave de alerta correcta."""
    with respx.mock:
        alert_route = respx.post(f"{_FAKE_URL}/GET/{_ALERT_KEY_80}").mock(
            return_value=Response(200, json={"result": None})
        )
        result = await redis_counter.alert_already_sent(_CYCLE, 80)

    assert result is False
    assert alert_route.called


@pytest.mark.asyncio
async def test_c5_alert_already_sent_true_when_key_exists(redis_counter: RedisCounter):
    with respx.mock:
        respx.post(f"{_FAKE_URL}/GET/{_ALERT_KEY_80}").mock(
            return_value=Response(200, json={"result": "1"})
        )
        result = await redis_counter.alert_already_sent(_CYCLE, 80)

    assert result is True


@pytest.mark.asyncio
async def test_c5_mark_alert_sent_uses_setnx_ex(redis_counter: RedisCounter):
    """mark_alert_sent() usa SET NX EX con el TTL correcto."""
    _TTL = 86400
    with respx.mock:
        set_route = respx.post(
            f"{_FAKE_URL}/SET/{_ALERT_KEY_80}/1/NX/EX/{_TTL}"
        ).mock(return_value=Response(200, json={"result": "OK"}))
        await redis_counter.mark_alert_sent(_CYCLE, 80, ttl_seconds=_TTL)

    assert set_route.called
