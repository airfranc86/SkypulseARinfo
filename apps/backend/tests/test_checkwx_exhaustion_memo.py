"""Exhaustion memo: once the daily quota is found spent, say so without touching anything for ~30 s.

E1 - Refusals during the memo cost no Upstash command at all (no INCR, no DECR).
E2 - The memo answers BEFORE the global bucket and the client share are consulted.
E3 - It expires with the injected clock and the next request checks the counter again.
E4 - It belongs to a cycle: a new cycle clears it.
E5 - Cached stations are still served; the router keeps the quota 429 contract.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, Response

from app.core.counter import MemoryCounter, RedisCounter, current_cycle
from app.core.upstash import UpstashRedis
from app.services import checkwx as checkwx_svc
from tests.conftest import FakeCheckWX, FakeClock, checkwx_payload

_UPSTASH = "https://fake-upstash.io"


class FakeQuotaUpstash:
    """Upstash stand-in holding ONE counter, recording every command it receives."""

    def __init__(self, value: int) -> None:
        self.value = value
        self.commands: list[str] = []

    def handle(self, request) -> Response:
        command = request.url.path.split("/")[1]
        self.commands.append(command)
        if command == "INCR":
            self.value += 1
        elif command == "DECR":
            self.value -= 1
        elif command == "EXPIRE":
            return Response(200, json={"result": 1})
        return Response(200, json={"result": self.value})


@pytest.fixture
def upstash(checkwx_upstream: FakeCheckWX, checkwx_counter, monkeypatch) -> FakeQuotaUpstash:
    """The quota lives in a fake Upstash that already holds 198 of 198 units."""
    fake = FakeQuotaUpstash(value=198)
    checkwx_upstream.router.post(url__startswith=_UPSTASH).mock(side_effect=fake.handle)
    checkwx_svc.set_counter(RedisCounter(UpstashRedis(_UPSTASH, "token")))
    monkeypatch.setattr(checkwx_svc, "maybe_notify", AsyncMock())  # alerts are not what is measured here
    return fake


async def _refused(icao: str, **kwargs) -> None:
    with pytest.raises(checkwx_svc.CheckWXQuotaExceededError) as caught:
        await checkwx_svc.fetch_metar(icao, kind="metar", **kwargs)
    assert caught.value.count == 198


# ---------------------------------------------------------------------------
# E1 - cost
# ---------------------------------------------------------------------------

async def test_e1_refusals_during_the_memo_cost_zero_upstash_commands(upstash: FakeQuotaUpstash):
    await _refused("AAA0")
    assert upstash.commands == ["INCR", "DECR"]  # the one finding: reserve, see it is over, give it back

    for n in range(10):
        await _refused(f"BBB{n}")
    await _refused("AAA0")  # even the same station again

    assert upstash.commands == ["INCR", "DECR"]
    assert upstash.value == 198


# ---------------------------------------------------------------------------
# E2 - ahead of the bucket and the share
# ---------------------------------------------------------------------------

async def test_e2_the_memo_answers_before_the_bucket_and_the_client_share(
    upstash: FakeQuotaUpstash, monkeypatch
):
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "checkwx_new_calls_per_minute", 1, raising=False)
    monkeypatch.setattr(cfg.settings, "checkwx_new_calls_per_client_per_minute", 1, raising=False)
    await _refused("AAA0", client="alice")  # the finding; its tokens come back
    assert checkwx_svc._global_bucket().try_acquire() is None  # now empty both on purpose
    assert checkwx_svc._client_shares().try_acquire("alice") is None

    await _refused("BBB0", client="alice")  # "quota", not "busy", and still not a single command

    assert upstash.commands == ["INCR", "DECR"]


# ---------------------------------------------------------------------------
# E3 - expiry
# ---------------------------------------------------------------------------

def test_e3_the_memo_lasts_about_thirty_seconds():
    assert checkwx_svc._EXHAUSTION_MEMO_SECONDS == 30


async def test_e3_the_memo_expires_and_the_counter_is_checked_again(
    upstash: FakeQuotaUpstash, checkwx_clock: FakeClock
):
    await _refused("AAA0")
    checkwx_clock.advance(checkwx_svc._EXHAUSTION_MEMO_SECONDS - 1)
    await _refused("AAA1")
    assert upstash.commands == ["INCR", "DECR"]  # still inside the memo

    checkwx_clock.advance(2)
    await _refused("AAA2")
    assert upstash.commands == ["INCR", "DECR", "INCR", "DECR"]  # looked again, found it spent again


async def test_e3_once_the_memo_expires_a_freed_unit_is_spent(
    upstash: FakeQuotaUpstash, checkwx_clock: FakeClock, checkwx_upstream: FakeCheckWX
):
    await _refused("AAA0")
    upstash.value = 100  # units came back (refunds, a bigger limit...)
    checkwx_clock.advance(checkwx_svc._EXHAUSTION_MEMO_SECONDS + 1)

    assert await checkwx_svc.fetch_metar("AAA1", kind="metar") == checkwx_payload("metar", "AAA1")


# ---------------------------------------------------------------------------
# E4 - per cycle
# ---------------------------------------------------------------------------

async def test_e4_a_new_cycle_clears_the_memo(
    upstash: FakeQuotaUpstash, checkwx_upstream: FakeCheckWX, monkeypatch
):
    today = {"cycle": "2026-10-08"}
    monkeypatch.setattr(checkwx_svc, "current_cycle", lambda: today["cycle"])
    await _refused("AAA0")

    today["cycle"] = "2026-10-09"  # midnight UTC: a fresh counter, well inside the 30 s of the memo
    upstash.value = 0

    assert await checkwx_svc.fetch_metar("AAA1", kind="metar") == checkwx_payload("metar", "AAA1")


# ---------------------------------------------------------------------------
# E5 - what the memo does not touch
# ---------------------------------------------------------------------------

async def test_e5_cached_stations_are_still_served_during_the_memo(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter
):
    assert await checkwx_svc.fetch_metar("SAEZ", kind="metar") == checkwx_payload("metar", "SAEZ")
    cycle = current_cycle()
    for _ in range(197):
        await checkwx_counter.incr(cycle)
    with pytest.raises(checkwx_svc.CheckWXQuotaExceededError):
        await checkwx_svc.fetch_metar("SACO", kind="metar")  # the finding

    assert await checkwx_svc.fetch_metar("SAEZ", kind="metar") == checkwx_payload("metar", "SAEZ")


@pytest.mark.usefixtures("fresh_rate_limit")
async def test_e5_the_router_keeps_the_quota_429_contract_during_the_memo(
    async_client: AsyncClient, checkwx_counter: MemoryCounter
):
    cycle = current_cycle()
    for _ in range(198):
        await checkwx_counter.incr(cycle)

    with patch("app.core.notifier.sentry_sdk"):
        finding = await async_client.get("/api/metar?icao=SAEZ")
        remembered = await async_client.get("/api/metar?icao=SACO")

    for response in (finding, remembered):
        assert response.status_code == 429
        detail = response.json()["detail"]
        assert set(detail) == {"error", "message", "cycle", "limit", "retry_after"}
        assert detail["error"] == "metar_quota_exceeded"
        assert detail["cycle"] == cycle
        assert detail["limit"] == 198
        assert response.headers["Retry-After"] == str(detail["retry_after"])
