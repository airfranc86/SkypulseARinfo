"""The client key of the request in flight, readable by services without passing it as a parameter.

K1 - The helpers: unset means None, set/reset nest and restore.
K2 - The real ASGI app: the request_logging middleware sets it before the route runs, with the same key as
     the per-IP rate limiter (client_key), and it is visible in tasks the request creates.
K3 - Two requests in flight at the same time never see each other's key.
K4 - It is cleared when the request ends, also when the handler fails, so nothing leaks into later work.
"""
from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from app.core.client_context import current_client_key, reset_client_key, set_client_key
from tests.test_dashboard import _make_current_response

CURRENT_URL = "/api/weather/current"
ALICE = {"CF-Connecting-IP": "198.51.100.10"}
BOB = {"CF-Connecting-IP": "198.51.100.20"}


# ---------------------------------------------------------------------------
# K1 - helpers
# ---------------------------------------------------------------------------

def test_k1_without_a_request_the_key_is_none():
    assert current_client_key() is None


def test_k1_set_then_reset_restores_the_previous_value():
    outer = set_client_key("outer")
    try:
        inner = set_client_key("inner")
        assert current_client_key() == "inner"
        reset_client_key(inner)
        assert current_client_key() == "outer"
    finally:
        reset_client_key(outer)

    assert current_client_key() is None


def test_k1_none_is_a_valid_value_to_set():
    token = set_client_key("alice")
    try:
        inner = set_client_key(None)
        assert current_client_key() is None
        reset_client_key(inner)
        assert current_client_key() == "alice"
    finally:
        reset_client_key(token)


# ---------------------------------------------------------------------------
# K2 - the middleware
# ---------------------------------------------------------------------------

@pytest.fixture
def observed(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str | None]]:
    """Replace the service the /current route calls with one that records the key it can see."""
    seen: list[tuple[str, str | None]] = []

    async def fake_aggregate_current(lat: float, lon: float):
        seen.append(("handler", current_client_key()))
        return _make_current_response()

    monkeypatch.setattr("app.routers.weather.aggregate_current", fake_aggregate_current)
    return seen


@pytest.mark.usefixtures("fresh_rate_limit")
async def test_k2_the_route_sees_the_key_of_the_real_client(async_client: AsyncClient, observed):
    response = await async_client.get(f"{CURRENT_URL}?lat=-31.4&lon=-64.2", headers=ALICE)

    assert response.status_code == 200
    assert observed == [("handler", "198.51.100.10")]


@pytest.mark.usefixtures("fresh_rate_limit")
async def test_k2_it_is_the_same_key_as_the_rate_limiter_so_a_forged_header_does_not_change_it(
    async_client: AsyncClient, observed
):
    forged = {**ALICE, "X-Forwarded-For": "203.0.113.99, 203.0.113.98, 203.0.113.97"}

    await async_client.get(f"{CURRENT_URL}?lat=-31.4&lon=-64.2", headers=forged)

    assert observed == [("handler", "198.51.100.10")]


@pytest.mark.usefixtures("fresh_rate_limit")
async def test_k2_it_travels_to_tasks_created_with_gather_and_create_task(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    seen: dict[str, str | None] = {}

    async def read(name: str) -> None:
        await asyncio.sleep(0)
        seen[name] = current_client_key()

    async def fake_aggregate_current(lat: float, lon: float):
        await asyncio.gather(read("gather-1"), read("gather-2"))
        task = asyncio.create_task(read("create-task"))
        await task
        return _make_current_response()

    monkeypatch.setattr("app.routers.weather.aggregate_current", fake_aggregate_current)

    response = await async_client.get(f"{CURRENT_URL}?lat=-31.4&lon=-64.2", headers=ALICE)

    assert response.status_code == 200
    assert seen == {
        "gather-1": "198.51.100.10",
        "gather-2": "198.51.100.10",
        "create-task": "198.51.100.10",
    }


# ---------------------------------------------------------------------------
# K3 - concurrent requests
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("fresh_rate_limit")
async def test_k3_concurrent_requests_never_see_each_others_key(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    seen: dict[float, list[str | None]] = {}
    arrived = 0
    both_inside = asyncio.Event()

    async def fake_aggregate_current(lat: float, lon: float):
        nonlocal arrived
        seen.setdefault(lat, []).append(current_client_key())
        arrived += 1
        if arrived == 2:
            both_inside.set()
        await both_inside.wait()  # hold both requests in flight at the same time
        await asyncio.sleep(0)
        seen[lat].append(current_client_key())
        return _make_current_response()

    monkeypatch.setattr("app.routers.weather.aggregate_current", fake_aggregate_current)

    first, second = await asyncio.gather(
        async_client.get(f"{CURRENT_URL}?lat=-31.4&lon=-64.2", headers=ALICE),
        async_client.get(f"{CURRENT_URL}?lat=-34.6&lon=-58.4", headers=BOB),
    )

    assert first.status_code == second.status_code == 200
    assert seen == {
        -31.4: ["198.51.100.10", "198.51.100.10"],
        -34.6: ["198.51.100.20", "198.51.100.20"],
    }


# ---------------------------------------------------------------------------
# K4 - cleared afterwards
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("fresh_rate_limit")
async def test_k4_the_key_is_cleared_when_the_request_ends(async_client: AsyncClient, observed):
    assert current_client_key() is None

    await async_client.get(f"{CURRENT_URL}?lat=-31.4&lon=-64.2", headers=ALICE)

    assert current_client_key() is None  # the test runs in the same task the ASGI app ran in


@pytest.mark.usefixtures("fresh_rate_limit")
async def test_k4_a_failing_handler_still_clears_the_key(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    async def exploding(lat: float, lon: float):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.routers.weather.aggregate_current", exploding)

    with pytest.raises(RuntimeError):
        await async_client.get(f"{CURRENT_URL}?lat=-31.4&lon=-64.2", headers=ALICE)

    assert current_client_key() is None


@pytest.mark.usefixtures("fresh_rate_limit")
async def test_k4_a_later_request_sees_only_its_own_key(async_client: AsyncClient, observed):
    await async_client.get(f"{CURRENT_URL}?lat=-31.4&lon=-64.2", headers=ALICE)
    await async_client.get(f"{CURRENT_URL}?lat=-34.6&lon=-58.4", headers=BOB)

    assert [key for _name, key in observed] == ["198.51.100.10", "198.51.100.20"]


async def test_k4_a_request_without_forwarding_headers_is_keyed_by_the_connection(
    async_client: AsyncClient, observed
):
    """A client with no CF header still has a key (the connection's address): it is subject to the cap."""
    from app.core.rate_limit import limiter

    limiter.reset()
    await async_client.get(f"{CURRENT_URL}?lat=-31.4&lon=-64.2")
    limiter.reset()

    assert len(observed) == 1
    assert observed[0][1]  # a non-empty string, never None
