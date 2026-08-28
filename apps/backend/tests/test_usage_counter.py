"""Tests para el contador de diagnóstico de uso de proveedores upstream (Plan A Fase 2).

A diferencia de `app.core.counter` (gate real de cuota CheckWX), este contador
NUNCA bloquea — solo cuenta llamadas upstream por proveedor, fire-and-forget.

U1 — Redis mode: dos proveedores distintos generan keys separadas (namespace).
U2 — record() no bloquea ni propaga excepción cuando Upstash está caído.
U3 — get_usage() lee el valor correcto tras uno o más record() (modo memoria).
U4 — Modo memoria funciona igual de bien sin Redis, con namespaces independientes.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
import respx
from httpx import Response

from app.core import usage_counter
from app.core.counter import current_cycle
from app.core.upstash import UpstashRedis

_FAKE_URL = "https://fake-upstash.io"
_FAKE_TOKEN = "test-token"


@pytest.fixture(autouse=True)
def reset_usage_counter():
    usage_counter._reset_for_tests()
    yield
    usage_counter._reset_for_tests()


# ---------------------------------------------------------------------------
# U1 — namespaces separados por proveedor (Redis)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_u1_different_providers_use_separate_redis_keys():
    redis = UpstashRedis(_FAKE_URL, _FAKE_TOKEN)
    usage_counter.configure_redis(redis)
    cycle = current_cycle()

    with respx.mock:
        smn_incr = respx.post(f"{_FAKE_URL}/INCR/skypulse:smn:counter:{cycle}").mock(
            return_value=Response(200, json={"result": 1})
        )
        respx.post(url__startswith=f"{_FAKE_URL}/EXPIRE/skypulse:smn:").mock(
            return_value=Response(200, json={"result": 1})
        )
        om_incr = respx.post(f"{_FAKE_URL}/INCR/skypulse:open_meteo:counter:{cycle}").mock(
            return_value=Response(200, json={"result": 1})
        )
        respx.post(url__startswith=f"{_FAKE_URL}/EXPIRE/skypulse:open_meteo:").mock(
            return_value=Response(200, json={"result": 1})
        )

        usage_counter.record("smn")
        usage_counter.record("open_meteo")
        await usage_counter._wait_pending_for_tests()

    assert smn_incr.called
    assert om_incr.called


# ---------------------------------------------------------------------------
# U2 — Upstash caído: record() no bloquea ni propaga
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_u2_record_fails_open_when_upstash_down():
    redis = UpstashRedis(_FAKE_URL, _FAKE_TOKEN)
    usage_counter.configure_redis(redis)

    with respx.mock:
        respx.post(url__startswith=f"{_FAKE_URL}/INCR/").mock(
            side_effect=httpx.ConnectError("Name or service not known")
        )
        usage_counter.record("smn")  # no debe lanzar (fire-and-forget)
        await usage_counter._wait_pending_for_tests()  # no debe propagar tampoco


# ---------------------------------------------------------------------------
# U3 — get_usage() refleja los record() en modo memoria
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_u3_get_usage_reflects_records_in_memory_mode():
    usage_counter.configure_memory()
    usage_counter.record("windy")
    usage_counter.record("windy")
    await usage_counter._wait_pending_for_tests()

    assert await usage_counter.get_usage("windy") == 2


# ---------------------------------------------------------------------------
# U4 — modo memoria: proveedores independientes, sin Redis
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_u4_memory_mode_keeps_providers_independent():
    usage_counter.configure_memory()
    usage_counter.record("usgs")
    usage_counter.record("emsc")
    usage_counter.record("emsc")
    await usage_counter._wait_pending_for_tests()

    assert await usage_counter.get_usage("usgs") == 1
    assert await usage_counter.get_usage("emsc") == 2


# ---------------------------------------------------------------------------
# Extra — get_usage() sobre un proveedor sin record() previo → 0
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_usage_unknown_provider_returns_zero_in_memory_mode():
    usage_counter.configure_memory()
    assert await usage_counter.get_usage("metar_awc") == 0
