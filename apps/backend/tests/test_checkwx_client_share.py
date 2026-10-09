"""Per-client share of the global bucket of NEW CheckWX calls.

C1 - One client cannot drain the global bucket; refusals on either side spend nothing on the other.
C2 - The per-client cap and its refill (injected clock).
C3 - Cached stations, remembered failures and joining a flight spend no share.
C4 - The structure that tracks clients is bounded.
C5 - No client key is ONE shared anonymous client.
C6 - A quota refusal hands the client's token back.
C7 - The router keys the share by the same client key as the per-IP rate limiter.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.core.counter import MemoryCounter, current_cycle
from app.services import checkwx as checkwx_svc
from tests.conftest import FakeCheckWX, FakeClock, checkwx_payload

_GLOBAL = 6  # one global token every 10 s
_SHARE = 3  # one token per client every 20 s


@pytest.fixture(autouse=True)
def caps(monkeypatch, checkwx_counter, checkwx_clock):
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "checkwx_new_calls_per_minute", _GLOBAL, raising=False)
    monkeypatch.setattr(cfg.settings, "checkwx_new_calls_per_client_per_minute", _SHARE, raising=False)


def _stations(count: int, prefix: str) -> list[str]:
    return [f"{prefix}{n:03d}" for n in range(count)]


async def _fetch(icao: str, client: str | None) -> dict:
    return await checkwx_svc.fetch_metar(icao, kind="metar", client=client)


# ---------------------------------------------------------------------------
# C1 - one client cannot drain the global bucket
# ---------------------------------------------------------------------------

async def test_c1_a_client_over_its_share_is_refused_without_spending_a_global_token(
    checkwx_upstream: FakeCheckWX
):
    for icao in _stations(_SHARE, "A"):
        await _fetch(icao, "alice")

    for icao in _stations(5, "X"):  # alice keeps trying
        with pytest.raises(checkwx_svc.CheckWXBusyError) as busy:
            await _fetch(icao, "alice")
        assert busy.value.retry_after == 20

    for icao in _stations(_SHARE, "B"):  # bob still gets every station: alice left the global bucket alone
        assert await _fetch(icao, "bob") == checkwx_payload("metar", icao)
    assert checkwx_upstream.count() == 2 * _SHARE


async def test_c1_a_global_refusal_spends_no_share_of_the_client(
    checkwx_upstream: FakeCheckWX, checkwx_clock: FakeClock
):
    for icao in _stations(_SHARE, "A"):
        await _fetch(icao, "alice")
    for icao in _stations(_SHARE, "B"):
        await _fetch(icao, "bob")  # the six global tokens are gone

    for icao in _stations(_SHARE, "X"):  # carol is refused by the GLOBAL bucket, three times
        with pytest.raises(checkwx_svc.CheckWXBusyError) as busy:
            await _fetch(icao, "carol")
        assert busy.value.retry_after == 10

    checkwx_clock.advance(10)  # one global token is back
    assert await _fetch("CCC0", "carol") == checkwx_payload("metar", "CCC0")  # her share was never touched


# ---------------------------------------------------------------------------
# C2 - cap and refill
# ---------------------------------------------------------------------------

async def test_c2_the_share_refills_over_time(checkwx_upstream: FakeCheckWX, checkwx_clock: FakeClock):
    for icao in _stations(_SHARE, "A"):
        await _fetch(icao, "alice")

    with pytest.raises(checkwx_svc.CheckWXBusyError) as busy:
        await _fetch("ZZZZ", "alice")
    assert busy.value.retry_after == 20

    checkwx_clock.advance(19)
    with pytest.raises(checkwx_svc.CheckWXBusyError) as still_busy:
        await _fetch("ZZZZ", "alice")
    assert still_busy.value.retry_after == 1

    checkwx_clock.advance(1)  # the very station that was refused goes through: busy is not remembered
    assert await _fetch("ZZZZ", "alice") == checkwx_payload("metar", "ZZZZ")


async def test_c2_a_share_refusal_costs_no_quota_and_no_upstream_call(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter
):
    for icao in _stations(_SHARE, "A"):
        await _fetch(icao, "alice")
    with pytest.raises(checkwx_svc.CheckWXBusyError):
        await _fetch("ZZZZ", "alice")

    assert checkwx_upstream.count() == _SHARE
    assert await checkwx_counter.get(current_cycle()) == _SHARE


# ---------------------------------------------------------------------------
# C3 - what spends nothing
# ---------------------------------------------------------------------------

async def test_c3_cached_and_remembered_failures_spend_no_share(checkwx_upstream: FakeCheckWX):
    checkwx_upstream.set("FAIL", 500)

    for _ in range(6):
        await _fetch("GOOD", "alice")  # one call, five cache hits
        with pytest.raises(checkwx_svc.CheckWXUnavailableError):
            await _fetch("FAIL", "alice")  # one call, five remembered failures
    assert await _fetch("LAST", "alice") == checkwx_payload("metar", "LAST")  # the third and last token

    with pytest.raises(checkwx_svc.CheckWXBusyError):
        await _fetch("NEXT", "alice")
    assert checkwx_upstream.count() == 3


async def test_c3_joining_a_flight_spends_no_share(checkwx_upstream: FakeCheckWX):
    checkwx_upstream.delay = 0.03

    results = await asyncio.gather(
        _fetch("SAEZ", "alice"), _fetch("SAEZ", "bob"), _fetch("SAEZ", "carol"), _fetch("SAEZ", "dave")
    )

    assert all(r == checkwx_payload("metar", "SAEZ") for r in results)
    assert checkwx_upstream.count() == 1
    for icao in _stations(_SHARE, "B"):  # only the leader paid: bob still has his whole share
        assert await _fetch(icao, "bob") == checkwx_payload("metar", icao)


# ---------------------------------------------------------------------------
# C4 - bounded structure
# ---------------------------------------------------------------------------

def test_c4_the_default_bound_is_1024_clients():
    assert checkwx_svc._MAX_TRACKED_CLIENTS == 1024


async def test_c4_the_number_of_tracked_clients_is_bounded(checkwx_upstream: FakeCheckWX, monkeypatch):
    import app.core.config as cfg
    monkeypatch.setattr(checkwx_svc, "_MAX_TRACKED_CLIENTS", 8)
    monkeypatch.setattr(cfg.settings, "checkwx_new_calls_per_minute", 10_000, raising=False)

    for n, icao in enumerate(_stations(30, "K")):
        await _fetch(icao, f"client-{n}")

    assert len(checkwx_svc._client_shares()) == 8


# ---------------------------------------------------------------------------
# C5 - anonymous client
# ---------------------------------------------------------------------------

async def test_c5_no_client_key_is_one_shared_anonymous_client(checkwx_upstream: FakeCheckWX):
    await _fetch("AAA0", None)
    await _fetch("AAA1", None)
    await checkwx_svc.fetch_metar("AAA2", kind="metar")  # no argument at all: the same anonymous client

    with pytest.raises(checkwx_svc.CheckWXBusyError):
        await _fetch("AAA3", None)
    assert await _fetch("AAA3", "alice") == checkwx_payload("metar", "AAA3")  # a real client is unaffected


# ---------------------------------------------------------------------------
# C6 - quota refusal
# ---------------------------------------------------------------------------

async def test_c6_a_quota_refusal_hands_the_client_token_back(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter, checkwx_clock: FakeClock, monkeypatch
):
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "checkwx_new_calls_per_client_per_minute", 2, raising=False)
    cycle = current_cycle()
    for _ in range(198):
        await checkwx_counter.incr(cycle)

    with pytest.raises(checkwx_svc.CheckWXQuotaExceededError):
        await _fetch("AAA0", "alice")

    for _ in range(2):
        await checkwx_counter.decr(cycle)
    checkwx_clock.advance(31)  # the exhaustion memo is over
    for icao in ("AAA1", "AAA2"):  # her whole share of two is intact
        assert await _fetch(icao, "alice") == checkwx_payload("metar", icao)


# ---------------------------------------------------------------------------
# C7 - router
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("fresh_rate_limit")
async def test_c7_the_router_passes_the_rate_limit_client_key(async_client: AsyncClient):
    fetch = AsyncMock(return_value=checkwx_payload("metar", "SAEZ"))
    with patch.object(checkwx_svc, "fetch_metar", fetch):
        await async_client.get("/api/metar?icao=SAEZ", headers={"CF-Connecting-IP": "203.0.113.7"})

    assert fetch.await_args.kwargs["client"] == "203.0.113.7"


@pytest.mark.usefixtures("fresh_rate_limit")
async def test_c7_one_ip_cannot_use_up_the_budget_of_another(
    async_client: AsyncClient, checkwx_upstream: FakeCheckWX
):
    alice = {"CF-Connecting-IP": "203.0.113.7"}
    bob = {"CF-Connecting-IP": "203.0.113.8"}
    for icao in _stations(_SHARE, "A"):
        assert (await async_client.get(f"/api/metar?icao={icao}", headers=alice)).status_code == 200

    refused = await async_client.get("/api/metar?icao=ZZZZ", headers=alice)
    served = await async_client.get("/api/metar?icao=ZZZZ", headers=bob)

    assert refused.status_code == 429
    detail = refused.json()["detail"]
    assert detail["error"] == "metar_busy"
    assert refused.headers["Retry-After"] == str(detail["retry_after"]) == "20"
    assert served.status_code == 200
