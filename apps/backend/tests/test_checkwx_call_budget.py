"""Global budget of NEW CheckWX calls per minute (token bucket) and its settings.

B1 - Beyond the cap, new stations get `CheckWXBusyError`; cached ones are still served.
B2 - The bucket refills with time (injected clock) and never holds more than the cap.
B3 - Only real upstream calls spend a token: not waiters, not remembered failures, not quota refusals.
B4 - The router answers 429 `metar_busy` with `Retry-After`, next to the unchanged quota 429.
B5 - Settings validation.
"""
from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.counter import MemoryCounter, current_cycle
from app.services import checkwx as checkwx_svc
from tests.conftest import FakeCheckWX, FakeClock, checkwx_payload

_CAP = 6  # six per minute: one token every 10 seconds, exact in floating point


@pytest.fixture(autouse=True)
def small_cap(monkeypatch, checkwx_counter, checkwx_clock):
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "checkwx_new_calls_per_minute", _CAP, raising=False)


def _icaos(count: int, prefix: str = "G") -> list[str]:
    return [f"{prefix}{n:03d}" for n in range(count)]


async def _units(counter: MemoryCounter) -> int:
    return await counter.get(current_cycle())


# ---------------------------------------------------------------------------
# B1 - the cap
# ---------------------------------------------------------------------------

async def test_b1_new_stations_beyond_the_cap_are_refused_as_busy(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter
):
    for icao in _icaos(_CAP):
        await checkwx_svc.fetch_metar(icao, kind="metar")

    with pytest.raises(checkwx_svc.CheckWXBusyError) as busy:
        await checkwx_svc.fetch_metar("ZZZZ", kind="metar")

    assert busy.value.retry_after == 10
    assert checkwx_upstream.count() == _CAP  # the refused one never reached CheckWX
    assert await _units(checkwx_counter) == _CAP  # ...nor spent a quota unit


async def test_b1_cached_stations_are_still_served_beyond_the_cap(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter
):
    icaos = _icaos(_CAP)
    for icao in icaos:
        await checkwx_svc.fetch_metar(icao, kind="metar")
    with pytest.raises(checkwx_svc.CheckWXBusyError):
        await checkwx_svc.fetch_metar("ZZZZ", kind="metar")

    for icao in icaos:
        assert await checkwx_svc.fetch_metar(icao, kind="metar") == checkwx_payload("metar", icao)

    assert checkwx_upstream.count() == _CAP


async def test_b1_a_burst_of_distinct_stations_makes_at_most_cap_calls(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter
):
    checkwx_upstream.delay = 0.02

    results = await asyncio.gather(
        *(checkwx_svc.fetch_metar(icao, kind="metar") for icao in _icaos(_CAP + 25)), return_exceptions=True
    )

    assert checkwx_upstream.count() == _CAP
    assert sum(isinstance(r, dict) for r in results) == _CAP
    assert sum(isinstance(r, checkwx_svc.CheckWXBusyError) for r in results) == 25


# ---------------------------------------------------------------------------
# B2 - refill
# ---------------------------------------------------------------------------

async def test_b2_the_bucket_refills_over_time_and_a_refused_station_is_not_remembered(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter, checkwx_clock: FakeClock
):
    for icao in _icaos(_CAP):
        await checkwx_svc.fetch_metar(icao, kind="metar")
    with pytest.raises(checkwx_svc.CheckWXBusyError) as busy:
        await checkwx_svc.fetch_metar("ZZZZ", kind="metar")
    assert busy.value.retry_after == 10

    checkwx_clock.advance(9)
    with pytest.raises(checkwx_svc.CheckWXBusyError) as still_busy:
        await checkwx_svc.fetch_metar("ZZZZ", kind="metar")
    assert still_busy.value.retry_after == 1

    checkwx_clock.advance(1)  # one token is back: the very same station goes through
    assert await checkwx_svc.fetch_metar("ZZZZ", kind="metar") == checkwx_payload("metar", "ZZZZ")
    with pytest.raises(checkwx_svc.CheckWXBusyError):
        await checkwx_svc.fetch_metar("YYYY", kind="metar")


async def test_b2_the_bucket_never_holds_more_than_the_cap(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter, checkwx_clock: FakeClock
):
    await checkwx_svc.fetch_metar("AAAA", kind="metar")  # the bucket exists and is partly spent
    checkwx_clock.advance(100_000)  # a long idle period must not bank extra tokens

    outcomes = []
    for icao in _icaos(_CAP + 3):
        try:
            await checkwx_svc.fetch_metar(icao, kind="metar")
            outcomes.append("ok")
        except checkwx_svc.CheckWXBusyError:
            outcomes.append("busy")

    assert outcomes == ["ok"] * _CAP + ["busy"] * 3


# ---------------------------------------------------------------------------
# B3 - what spends a token
# ---------------------------------------------------------------------------

async def test_b3_waiters_of_one_flight_spend_a_single_token(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter, monkeypatch
):
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "checkwx_new_calls_per_minute", 2, raising=False)
    checkwx_upstream.delay = 0.03

    await asyncio.gather(*(checkwx_svc.fetch_metar("SAEZ", kind="metar") for _ in range(10)))
    await checkwx_svc.fetch_metar("SACO", kind="metar")  # second token

    with pytest.raises(checkwx_svc.CheckWXBusyError):
        await checkwx_svc.fetch_metar("SAWH", kind="metar")


async def test_b3_failed_calls_still_spend_a_token(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter
):
    """A failing CheckWX must not be hammered with new stations either."""
    checkwx_upstream.default_outcome = 500
    for icao in _icaos(_CAP):
        with pytest.raises(checkwx_svc.CheckWXUnavailableError):
            await checkwx_svc.fetch_metar(icao, kind="metar")

    with pytest.raises(checkwx_svc.CheckWXBusyError):
        await checkwx_svc.fetch_metar("ZZZZ", kind="metar")
    assert await _units(checkwx_counter) == 0  # ...although none of them cost quota


async def test_b3_remembered_failures_spend_no_token(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter
):
    checkwx_upstream.set("SAEZ", 500)
    for _ in range(20):
        with pytest.raises(checkwx_svc.CheckWXUnavailableError):
            await checkwx_svc.fetch_metar("SAEZ", kind="metar")
    assert checkwx_upstream.count() == 1

    for icao in _icaos(_CAP - 1):  # five tokens are left
        await checkwx_svc.fetch_metar(icao, kind="metar")
    with pytest.raises(checkwx_svc.CheckWXBusyError):
        await checkwx_svc.fetch_metar("ZZZZ", kind="metar")


async def test_b3_a_quota_refusal_gives_its_token_back(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter, checkwx_clock: FakeClock
):
    cycle = current_cycle()
    for _ in range(198):
        await checkwx_counter.incr(cycle)

    for icao in _icaos(_CAP + 4):  # more refusals than tokens: never "busy", always "quota"
        with pytest.raises(checkwx_svc.CheckWXQuotaExceededError):
            await checkwx_svc.fetch_metar(icao, kind="metar")

    for _ in range(_CAP):
        await checkwx_counter.decr(cycle)
    checkwx_clock.advance(31)  # the exhaustion memo is over (it also refills the bucket, which is full anyway)
    for icao in _icaos(_CAP, prefix="H"):  # the bucket is still full
        await checkwx_svc.fetch_metar(icao, kind="metar")
    assert checkwx_upstream.count() == _CAP


# ---------------------------------------------------------------------------
# B4 - router
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("fresh_rate_limit")
async def test_b4_router_answers_429_busy_with_retry_after_and_keeps_serving_cached_stations(
    async_client: AsyncClient, checkwx_upstream: FakeCheckWX, monkeypatch
):
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "checkwx_new_calls_per_minute", 1, raising=False)

    assert (await async_client.get("/api/metar?icao=SAEZ")).status_code == 200
    busy = await async_client.get("/api/metar?icao=SACO")
    cached = await async_client.get("/api/metar?icao=SAEZ")

    assert busy.status_code == 429
    detail = busy.json()["detail"]
    assert set(detail) == {"error", "message", "limit_per_minute", "retry_after"}
    assert detail["error"] == "metar_busy"
    assert detail["limit_per_minute"] == 1
    assert 1 <= detail["retry_after"] <= 60
    assert busy.headers["Retry-After"] == str(detail["retry_after"])
    assert cached.status_code == 200
    assert cached.json() == checkwx_payload("metar", "SAEZ")
    assert checkwx_upstream.count() == 1


# ---------------------------------------------------------------------------
# B5 - settings
# ---------------------------------------------------------------------------

def test_b5_defaults():
    defaults = Settings(_env_file=None)
    assert defaults.checkwx_new_calls_per_minute == 12
    assert defaults.checkwx_new_calls_per_client_per_minute == 3
    assert defaults.checkwx_failure_ttl_seconds == 15  # what the frontend retry policy assumes
    assert defaults.checkwx_flight_deadline_seconds == 20


@pytest.mark.parametrize("value", [0, -1, -12])
def test_b5_calls_per_minute_must_be_at_least_one(value: int):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, checkwx_new_calls_per_minute=value)


def test_b5_calls_per_minute_accepts_one():
    assert Settings(_env_file=None, checkwx_new_calls_per_minute=1).checkwx_new_calls_per_minute == 1


@pytest.mark.parametrize("value", [0, 0.5, -30])
def test_b5_failure_ttl_must_be_at_least_one_second(value: float):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, checkwx_failure_ttl_seconds=value)


@pytest.mark.parametrize("value", [0, -1])
def test_b5_calls_per_client_must_be_at_least_one(value: int):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, checkwx_new_calls_per_client_per_minute=value)


def test_b5_calls_per_client_accepts_one():
    assert Settings(_env_file=None, checkwx_new_calls_per_client_per_minute=1).checkwx_new_calls_per_client_per_minute == 1


@pytest.mark.parametrize("value", [0, 0.5, -20])
def test_b5_flight_deadline_must_be_at_least_one_second(value: float):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, checkwx_flight_deadline_seconds=value)
