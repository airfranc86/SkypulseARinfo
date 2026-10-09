"""GET /api/taf under the AWC protection: the old 200/404/422/503 stay, and a refusal is a 429 `taf_busy`.

The only new answer is `429 {"detail": {"error": "taf_busy", "retry_after": N}}` with a `Retry-After` header
(the same style as the `metar_busy` of `/api/metar`). It appears ONLY when the call budget or the 429 pause
refuses a NEW request to AWC and there is neither a cached TAF nor a remembered "no TAF" to answer with.
AWC is mocked with respx; the network is never touched.
"""
from __future__ import annotations

import asyncio
import logging

import httpx
import pytest
import respx
from httpx import AsyncClient

from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.rate_limit_pause import awc_pause as pause
from app.services.reportes_aeronauticos.awc import AWC_TAF_BASE
from tests.conftest import FakeClock
from tests.helpers_caracterizacion_aeronautica import load_taf

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _fresh_route_limiter():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def set_caps(monkeypatch: pytest.MonkeyPatch):
    def _set(*, client: int, overall: int = 100, unknown: int = 100) -> None:
        monkeypatch.setattr(settings, "awc_calls_per_client_per_minute", client)
        monkeypatch.setattr(settings, "awc_calls_per_minute", overall)
        monkeypatch.setattr(settings, "awc_unknown_calls_per_minute", unknown)

    return _set


@pytest.fixture
def awc_taf():
    """The AWC TAF route: SACO has a TAF, any other station gets an empty list."""
    saco = load_taf("SACO")

    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=saco if request.url.params["ids"] == "SACO" else [])

    with respx.mock(assert_all_called=False) as router:
        yield router.get(AWC_TAF_BASE).mock(side_effect=answer)


async def _get(client: AsyncClient, icao: str) -> httpx.Response:
    return await client.get("/api/taf", params={"icao": icao})


# ---------------------------------------------------------------------------
# the old contract
# ---------------------------------------------------------------------------

async def test_200_404_and_422_are_unchanged(async_client: AsyncClient, awc_taf) -> None:
    assert (await _get(async_client, "SACO")).status_code == 200
    missing = await _get(async_client, "SAXX")
    assert (missing.status_code, missing.json()) == (404, {"detail": "taf_not_found"})
    assert (await _get(async_client, "SAC")).status_code == 422
    assert (await async_client.get("/api/taf")).status_code == 422


async def test_503_is_unchanged_when_awc_fails(async_client: AsyncClient) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(500, text="boom"))
        response = await _get(async_client, "SACO")

    assert (response.status_code, response.json()) == (503, {"detail": "taf_unavailable"})
    assert "retry-after" not in response.headers


async def test_a_failure_is_remembered_for_a_minute_and_stays_a_503(async_client: AsyncClient) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(500, text="boom"))
        first = await _get(async_client, "SACO")
        second = await _get(async_client, "SACO")

    assert (first.status_code, second.status_code) == (503, 503)
    assert route.call_count == 1


async def test_five_simultaneous_requests_for_one_station_make_one_awc_request(async_client: AsyncClient) -> None:
    saco = load_taf("SACO")

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return httpx.Response(200, json=saco)

    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_TAF_BASE).mock(side_effect=slow)
        responses = await asyncio.gather(*[_get(async_client, "SACO") for _ in range(5)])

    assert [r.status_code for r in responses] == [200] * 5
    assert route.call_count == 1


async def test_a_station_without_taf_is_asked_once_and_stays_a_404(async_client: AsyncClient, awc_taf) -> None:
    responses = [await _get(async_client, "SAXX") for _ in range(3)]

    assert [r.status_code for r in responses] == [404, 404, 404]
    assert awc_taf.call_count == 1


async def test_the_icao_in_any_case_makes_one_request(async_client: AsyncClient, awc_taf) -> None:
    assert (await _get(async_client, "saco")).status_code == 200
    assert (await _get(async_client, "SACO")).status_code == 200
    assert awc_taf.call_count == 1


# ---------------------------------------------------------------------------
# the new 429 `taf_busy`
# ---------------------------------------------------------------------------

async def test_over_the_client_share_a_new_station_is_a_429_taf_busy(async_client: AsyncClient, awc_taf, set_caps) -> None:
    set_caps(client=1, overall=2)
    assert (await _get(async_client, "SACO")).status_code == 200

    response = await _get(async_client, "SAAR")

    assert response.status_code == 429
    assert response.json() == {"detail": {"error": "taf_busy", "retry_after": 60}}
    assert response.headers["retry-after"] == "60"
    assert awc_taf.call_count == 1   # the refused request never reached AWC


async def test_over_the_global_cap_it_is_a_429_taf_busy_with_the_wait_for_one_token(
    async_client: AsyncClient, awc_taf, set_caps
) -> None:
    set_caps(client=50, overall=4)
    for icao in ("SACO", "SAAR", "SABE", "SAEZ"):
        await _get(async_client, icao)

    response = await _get(async_client, "SAME")

    assert response.status_code == 429
    assert response.json()["detail"] == {"error": "taf_busy", "retry_after": 15}
    assert response.headers["retry-after"] == "15"


async def test_during_the_429_pause_it_is_a_429_taf_busy_with_the_time_left(async_client: AsyncClient, awc_taf) -> None:
    clock = FakeClock()
    pause.clock = clock
    pause.trip()
    clock.advance(30.0)

    response = await _get(async_client, "SACO")

    assert response.status_code == 429
    assert response.json() == {"detail": {"error": "taf_busy", "retry_after": 90}}
    assert response.headers["retry-after"] == "90"
    assert awc_taf.call_count == 0


async def test_a_429_from_awc_itself_is_a_503_and_the_next_request_finds_the_pause(async_client: AsyncClient) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(429, text="slow down"))
        first = await _get(async_client, "SACO")
        second = await _get(async_client, "SAAR")

    assert (first.status_code, first.json()) == (503, {"detail": "taf_unavailable"})
    assert second.status_code == 429 and second.json()["detail"]["error"] == "taf_busy"
    assert route.call_count == 1


async def test_a_refusal_is_never_remembered_so_the_same_station_works_once_the_budget_allows(
    async_client: AsyncClient, awc_taf, set_caps
) -> None:
    set_caps(client=1, overall=2)
    await _get(async_client, "SAXX")                     # her only token
    assert (await _get(async_client, "SACO")).status_code == 429

    limiter.reset()
    from app.services.reportes_aeronauticos import awc_budget
    awc_budget._reset_for_tests()                         # a minute later: the share is back
    assert (await _get(async_client, "SACO")).status_code == 200


# ---------------------------------------------------------------------------
# when there is something to answer with, there is no 429
# ---------------------------------------------------------------------------

async def test_a_cached_taf_is_served_even_when_the_budget_is_spent(async_client: AsyncClient, awc_taf, set_caps) -> None:
    set_caps(client=1, overall=2)
    assert (await _get(async_client, "SACO")).status_code == 200
    assert (await _get(async_client, "SAAR")).status_code == 429

    again = await _get(async_client, "SACO")

    assert again.status_code == 200 and again.json()["icao"] == "SACO"


async def test_a_remembered_no_taf_is_a_404_even_when_the_budget_is_spent(async_client: AsyncClient, awc_taf, set_caps) -> None:
    set_caps(client=1, overall=2)
    assert (await _get(async_client, "SAXX")).status_code == 404   # spends the only token
    assert (await _get(async_client, "SACO")).status_code == 429

    again = await _get(async_client, "SAXX")

    assert (again.status_code, again.json()) == (404, {"detail": "taf_not_found"})


async def test_the_stale_taf_is_served_instead_of_a_429_when_a_refresh_is_refused(
    async_client: AsyncClient, awc_taf, set_caps, taf_clock
) -> None:
    set_caps(client=1, overall=2)
    assert (await _get(async_client, "SACO")).status_code == 200   # spends the only token
    taf_clock.now = 3601.0                                         # the fresh copy expired; the stale one stays

    response = await _get(async_client, "SACO")

    assert response.status_code == 200 and response.json()["icao"] == "SACO"
    assert awc_taf.call_count == 1


async def test_the_stale_taf_is_served_during_the_pause(async_client: AsyncClient, awc_taf, taf_clock) -> None:
    assert (await _get(async_client, "SACO")).status_code == 200
    taf_clock.now = 3601.0
    pause.trip()

    response = await _get(async_client, "SACO")

    assert response.status_code == 200
    assert awc_taf.call_count == 1


# ---------------------------------------------------------------------------
# stations outside the local airports list share a small global bucket
# ---------------------------------------------------------------------------

async def test_the_9th_unknown_station_in_a_minute_is_a_429_taf_busy_and_a_known_one_still_works(
    async_client: AsyncClient, awc_taf, set_caps
) -> None:
    set_caps(client=50, overall=100, unknown=8)
    for index in range(8):
        assert (await _get(async_client, f"SX{index:02d}")).status_code == 404

    refused = await _get(async_client, "SXZZ")

    assert refused.status_code == 429
    assert refused.json() == {"detail": {"error": "taf_busy", "retry_after": 8}}
    assert refused.headers["retry-after"] == "8"
    assert (await _get(async_client, "SACO")).status_code == 200   # a known station is not affected


async def test_a_remembered_no_taf_of_an_unknown_station_is_still_a_404_after_the_unknown_cap_is_spent(
    async_client: AsyncClient, awc_taf, set_caps
) -> None:
    set_caps(client=50, overall=100, unknown=1)
    assert (await _get(async_client, "SXAA")).status_code == 404
    assert (await _get(async_client, "SXBB")).status_code == 429

    again = await _get(async_client, "SXAA")

    assert (again.status_code, again.json()) == (404, {"detail": "taf_not_found"})


async def test_a_busy_answer_writes_no_info_line_per_request(async_client: AsyncClient, awc_taf, set_caps, caplog) -> None:
    set_caps(client=1, overall=2)
    caplog.set_level(logging.INFO)
    assert (await _get(async_client, "SACO")).status_code == 200
    for _ in range(5):
        assert (await _get(async_client, "SAAR")).status_code == 429

    noisy = [r for r in caplog.records if r.name.startswith("app.routers.taf") and "refused" in r.getMessage()]
    assert noisy == []
