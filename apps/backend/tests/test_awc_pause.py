"""Circuit breaker for AWC: a 429 pauses every request to aviationweather.gov for METAR and TAF alike.

Same behaviour as the Open-Meteo pause (`core/rate_limit_pause.py`, reused as is): the first 429 opens a pause
(the `Retry-After` when usable, else 120 s); while it lasts nothing goes to the network, nothing is counted as
`metar_awc` and no budget token is spent; after it ONE probe goes out and decides. A call that does not go out
is a refusal (`AwcRefused`, a `FetchRefused`): the caches do not remember it as a failure and serve their last
good copy, and every consumer answers "unavailable" for that request only.

The network is never touched (respx and in-memory sources).
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import httpx
import pytest
import respx

from app.core.cache import FetchRefused
from app.core.client_context import reset_client_key, set_client_key
from app.core.config import settings
from app.core.rate_limit_pause import awc_pause as pause
from app.services.metar_observation import get_nearest_metar_observation
from app.services.reportes_aeronauticos import (
    AwcError,
    fetch_taf_entry,
    get_metar_visibility,
    get_nearest_metar_visibility,
    get_taf_for_icao,
)
from app.services.reportes_aeronauticos import awc
from app.services.reportes_aeronauticos.awc import AWC_METAR_BASE, AWC_TAF_BASE, HttpAwcSource
from app.services.reportes_aeronauticos.awc_budget import AwcRefused
from app.services.reportes_aeronauticos.taf import TafBusyError
from app.services.reportes_aeronauticos.awc_metar import metar_entries_cache
from app.services.reportes_aeronauticos import taf as taf_module
from tests.conftest import FakeClock
from tests.helpers_caracterizacion_aeronautica import FROZEN_NOW, awc_metar, load_taf, minutes_before

pytestmark = pytest.mark.integration

ROSARIO = (-32.95, -60.65)   # SAAR, 13.1 km


@pytest.fixture
def clock() -> FakeClock:
    fake = FakeClock()
    pause.clock = fake
    return fake


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """The `metar_awc` usage counter: one `record` call per outgoing AWC request."""
    mock = MagicMock()
    monkeypatch.setattr(awc.usage_counter, "record", mock)
    return mock


def _too_many(headers: dict | None = None) -> httpx.Response:
    return httpx.Response(429, text="slow down", headers=headers or {})


def _saar_metar(minutes_old: float = 10) -> list[dict]:
    return awc_metar(minutes_before(FROZEN_NOW, minutes_old), "SAAR", visib="6+", temp=18, dewp=12)


async def _metar(source: HttpAwcSource | None = None, icao: str = "SAAR") -> object:
    return await (source or HttpAwcSource()).metar(icao, hours=3, timeout=4.0)


async def _taf(source: HttpAwcSource | None = None, icao: str = "SACO") -> object:
    return await (source or HttpAwcSource()).taf(icao, timeout=4.0)


# ---------------------------------------------------------------------------
# opening the pause
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["metar", "taf"])
async def test_a_429_opens_the_default_pause_of_120_seconds(kind: str, clock: FakeClock) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_METAR_BASE if kind == "metar" else AWC_TAF_BASE).mock(return_value=_too_many())
        with pytest.raises(AwcError):
            await (_metar() if kind == "metar" else _taf())
    assert pause.remaining() == pytest.approx(120.0)


@pytest.mark.parametrize(
    ("header", "expected"),
    [("45", 45.0), ("300", 300.0), ("3", 10.0), ("700", 120.0), ("0", 120.0), ("soon", 120.0)],
)
async def test_the_retry_after_sets_the_pause_within_its_bounds(header: str, expected: float, clock: FakeClock) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_METAR_BASE).mock(return_value=_too_many({"Retry-After": header}))
        with pytest.raises(AwcError):
            await _metar()
    assert pause.remaining() == pytest.approx(expected)


@pytest.mark.parametrize("status", [400, 404, 500, 503])
async def test_other_http_errors_do_not_open_the_pause(status: int, clock: FakeClock) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_METAR_BASE).mock(return_value=httpx.Response(status))
        with pytest.raises(AwcError):
            await _metar()
    assert pause.remaining() == 0.0
    assert pause.allow_request() is True


@pytest.mark.parametrize("failure", [httpx.ReadTimeout("slow"), httpx.ConnectError("down")])
async def test_a_timeout_or_a_network_error_does_not_open_the_pause(failure: Exception, clock: FakeClock) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_METAR_BASE).mock(side_effect=failure)
        with pytest.raises(AwcError):
            await _metar()
    assert pause.remaining() == 0.0


# ---------------------------------------------------------------------------
# while it lasts: no network, no counter, a refusal
# ---------------------------------------------------------------------------

async def test_no_network_call_and_no_counter_during_the_pause(counted: MagicMock, clock: FakeClock) -> None:
    with respx.mock(assert_all_called=False) as router:
        metar_route = router.get(AWC_METAR_BASE).mock(return_value=_too_many())
        taf_route = router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=[]))
        with pytest.raises(AwcError):
            await _metar()
        assert counted.call_count == 1

        clock.advance(60.0)
        for _ in range(3):
            with pytest.raises(AwcRefused):
                await _metar(icao="SABE")
            with pytest.raises(AwcRefused):
                await _taf()

    assert metar_route.call_count == 1
    assert taf_route.call_count == 0
    assert counted.call_count == 1


async def test_a_429_on_the_metar_pauses_the_taf_too(clock: FakeClock) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_METAR_BASE).mock(return_value=_too_many())
        taf_route = router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=[]))
        with pytest.raises(AwcError):
            await _metar()
        with pytest.raises(AwcRefused):
            await _taf()
    assert taf_route.call_count == 0


async def test_a_refusal_during_the_pause_is_a_fetch_refused_and_not_an_awc_error(clock: FakeClock) -> None:
    pause.trip()
    with pytest.raises(AwcRefused) as caught:
        await _metar()
    assert isinstance(caught.value, FetchRefused)
    assert not isinstance(caught.value, AwcError)
    assert caught.value.reason == "paused"


@pytest.mark.parametrize(("elapsed", "expected"), [(0, 120), (59.5, 61), (119.2, 1)])
async def test_the_refusal_says_how_long_to_wait_in_whole_seconds(elapsed: float, expected: int, clock: FakeClock) -> None:
    pause.trip()
    clock.advance(elapsed)
    with pytest.raises(AwcRefused) as caught:
        await _metar()
    assert caught.value.retry_after == expected
    assert isinstance(caught.value.retry_after, int)


async def test_the_pause_also_applies_outside_an_http_request(clock: FakeClock) -> None:
    pause.trip()
    with pytest.raises(AwcRefused):   # no client key here: the budget does not apply, the pause does
        await _taf()


# ---------------------------------------------------------------------------
# after it: one probe
# ---------------------------------------------------------------------------

async def test_after_the_pause_a_successful_probe_reopens_the_traffic(counted: MagicMock, clock: FakeClock) -> None:
    pause.trip()
    clock.advance(121.0)
    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=[{"icaoId": "SAAR"}]))
        assert await _metar() == [{"icaoId": "SAAR"}]
        assert pause.remaining() == 0.0
        assert await _metar(icao="SABE") == [{"icaoId": "SAAR"}]
    assert route.call_count == 2


async def test_only_one_probe_goes_out_and_the_others_wait_for_its_result(clock: FakeClock) -> None:
    pause.trip()
    clock.advance(121.0)
    release = asyncio.Event()
    requests: list[str] = []

    async def slow(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.params["ids"])
        await release.wait()
        return httpx.Response(200, json=[])

    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_METAR_BASE).mock(side_effect=slow)
        probe = asyncio.create_task(_metar())
        await asyncio.sleep(0.01)
        assert requests == ["SAAR"]

        with pytest.raises(AwcRefused):   # a second caller while the probe is in flight
            await asyncio.wait_for(_metar(icao="SABE"), timeout=2.0)   # never wait on the probe's gate
        assert requests == ["SAAR"]

        release.set()
        assert await probe == []
        assert pause.remaining() == 0.0


async def test_a_probe_that_gets_another_429_renews_the_pause(clock: FakeClock) -> None:
    pause.trip()
    clock.advance(121.0)
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_METAR_BASE).mock(return_value=_too_many({"Retry-After": "30"}))
        with pytest.raises(AwcError):
            await _metar()
    assert pause.remaining() == pytest.approx(30.0)


async def test_a_success_from_before_a_newer_429_does_not_close_the_pause(clock: FakeClock) -> None:
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["ids"] == "SAAR":
            await release.wait()     # started before the 429 below, answers 200 after it
            return httpx.Response(200, json=[])
        return _too_many()

    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_METAR_BASE).mock(side_effect=handler)
        slow = asyncio.create_task(_metar(icao="SAAR"))
        await asyncio.sleep(0.01)
        with pytest.raises(AwcError):
            await _metar(icao="SABE")
        assert pause.remaining() > 0

        release.set()
        assert await slow == []

    assert pause.remaining() > 0   # the old success did not reopen the traffic


# ---------------------------------------------------------------------------
# the consumers: unavailable for this request only
# ---------------------------------------------------------------------------

async def test_niebla_and_the_dashboard_get_none_during_the_pause_without_an_error(clock: FakeClock) -> None:
    pause.trip()
    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=_saar_metar()))
        visibility = await get_nearest_metar_visibility(*ROSARIO, now=FROZEN_NOW)
        selection = await get_nearest_metar_observation(*ROSARIO, now=FROZEN_NOW)
        assert await get_metar_visibility("SAAR", FROZEN_NOW) is None
    assert route.call_count == 0
    assert visibility.visibility_m is None and visibility.icao == "SAAR"
    assert selection.reason == "metar_unavailable" and selection.observation is None


async def test_the_taf_helper_of_niebla_is_none_during_the_pause(clock: FakeClock) -> None:
    pause.trip()
    assert await get_taf_for_icao("SACO") is None


async def test_fetch_taf_entry_reports_busy_with_the_wait_during_the_pause(clock: FakeClock) -> None:
    pause.trip()
    clock.advance(20.0)
    with pytest.raises(TafBusyError) as caught:
        await fetch_taf_entry("SACO")
    assert caught.value.retry_after == 100


async def test_a_refusal_is_not_remembered_as_a_failure_of_the_station(clock: FakeClock) -> None:
    pause.trip()
    assert await get_metar_visibility("SAAR", FROZEN_NOW) is None
    with pytest.raises(TafBusyError):
        await fetch_taf_entry("SACO")
    assert len(metar_entries_cache._failure_cache) == 0
    assert len(taf_module._taf_cache._failure_cache) == 0

    clock.advance(121.0)   # the pause ends: the very next call goes out, without waiting for any failure TTL
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=_saar_metar()))
        router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=load_taf("SACO")))
        assert await get_metar_visibility("SAAR", FROZEN_NOW) is not None
        assert await fetch_taf_entry("SACO") is not None


async def test_the_last_good_metar_is_served_while_the_pause_lasts(metar_clock, clock: FakeClock) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=_saar_metar()))
        first = await get_metar_visibility("SAAR", FROZEN_NOW)
        assert first is not None
        metar_clock.now = 301.0           # the 5-minute fresh copy expired; the 30-minute stale one stays
        pause.trip()

        assert await get_metar_visibility("SAAR", FROZEN_NOW) == first
    assert route.call_count == 1


async def test_the_last_good_taf_is_served_while_the_pause_lasts(taf_clock, clock: FakeClock) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=load_taf("SACO")))
        first = await fetch_taf_entry("SACO")
        taf_clock.now = 3601.0            # the hour-long fresh copy expired; the stale one stays
        pause.trip()

        assert await fetch_taf_entry("SACO") == first
    assert route.call_count == 1


# ---------------------------------------------------------------------------
# the pause costs no budget
# ---------------------------------------------------------------------------

async def test_a_call_refused_by_the_pause_spends_no_budget_token(monkeypatch: pytest.MonkeyPatch, clock: FakeClock) -> None:
    monkeypatch.setattr(settings, "awc_calls_per_client_per_minute", 1)
    monkeypatch.setattr(settings, "awc_calls_per_minute", 10)
    pause.trip()
    token = set_client_key("alice")
    try:
        for _ in range(5):
            with pytest.raises(AwcRefused) as caught:
                await _metar()
            assert caught.value.reason == "paused"
        clock.advance(121.0)
        with respx.mock(assert_all_called=False) as router:
            router.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=[]))
            assert await _metar() == []   # her only token was still there
    finally:
        reset_client_key(token)


# ---------------------------------------------------------------------------
# the half-open probe: what closes it, what leaves it, what gives it back
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", [400, 403, 404, 422])
async def test_a_4xx_other_than_429_answers_the_probe_so_the_pause_closes(status: int, clock: FakeClock) -> None:
    pause.trip()
    clock.advance(121.0)
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_METAR_BASE).mock(return_value=httpx.Response(status))
        with pytest.raises(AwcError):
            await _metar()
    assert pause.remaining() == 0.0
    assert pause.allow_request() is True    # the traffic flows again: AWC is alive, it only rejected THAT request
    assert pause.allow_request() is True


async def test_a_4xx_after_a_newer_429_does_not_close_the_pause(clock: FakeClock) -> None:
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["ids"] == "SAAR":
            await release.wait()
            return httpx.Response(404)
        return _too_many()

    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_METAR_BASE).mock(side_effect=handler)
        slow = asyncio.create_task(_metar(icao="SAAR"))
        await asyncio.sleep(0.01)
        with pytest.raises(AwcError):
            await _metar(icao="SABE")
        release.set()
        with pytest.raises(AwcError):
            await slow

    assert pause.remaining() > 0


@pytest.mark.parametrize(
    "arrange",
    [
        pytest.param(lambda route: route.mock(return_value=httpx.Response(500)), id="5xx"),
        pytest.param(lambda route: route.mock(side_effect=httpx.ReadTimeout("slow")), id="timeout"),
        pytest.param(lambda route: route.mock(side_effect=httpx.ConnectError("down")), id="network"),
    ],
)
async def test_a_5xx_or_a_timeout_leave_the_probe_slot_held_as_before(arrange, clock: FakeClock) -> None:
    pause.trip()
    clock.advance(121.0)
    with respx.mock(assert_all_called=False) as router:
        arrange(router.get(AWC_METAR_BASE))
        with pytest.raises(AwcError):
            await _metar()
    assert pause.allow_request() is False   # nothing was learned: the probe window stays held until it expires


async def test_a_200_with_invalid_json_still_closes_the_pause_as_before(clock: FakeClock) -> None:
    pause.trip()
    clock.advance(121.0)
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, text="<html>x</html>"))
        with pytest.raises(AwcError):
            await _metar()
    assert pause.remaining() == 0.0 and pause.allow_request() is True   # the server answered: it is alive


async def test_a_cancelled_probe_gives_its_slot_back(clock: FakeClock) -> None:
    pause.trip()
    clock.advance(121.0)
    started = asyncio.Event()
    gate = asyncio.Event()
    requests: list[str] = []

    async def slow(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.params["ids"])
        started.set()
        await gate.wait()
        return httpx.Response(200, json=[])

    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_METAR_BASE).mock(side_effect=slow)
        probe = asyncio.create_task(_metar())
        await started.wait()
        with pytest.raises(AwcRefused):          # while the probe is in flight, everybody else waits
            await _metar(icao="SABE")

        probe.cancel()
        with pytest.raises(asyncio.CancelledError):
            await probe

        gate.set()
        assert await _metar(icao="SABE") == []   # the slot is free: the next caller is the new probe
        assert requests == ["SAAR", "SABE"]
    assert pause.remaining() == 0.0


async def test_cancelling_a_request_that_took_no_probe_changes_nothing(clock: FakeClock) -> None:
    started = asyncio.Event()

    async def slow(request: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.Event().wait()
        return httpx.Response(200, json=[])

    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_METAR_BASE).mock(side_effect=slow)
        task = asyncio.create_task(_metar())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert pause.remaining() == 0.0 and pause.allow_request() is True


def test_a_probe_ticket_only_releases_its_own_window(clock: FakeClock) -> None:
    pause.trip()
    clock.advance(121.0)
    assert pause.allow_request() is True
    first = pause.probe_ticket()
    assert first is not None

    pause.trip()                       # the probe came back 429: a new pause...
    clock.advance(121.0)
    assert pause.allow_request() is True    # ...and another caller takes the NEW probe window
    second = pause.probe_ticket()
    assert second is not None and second != first

    pause.release_probe_ticket(first)  # the first, late, tries to give "its" slot back: it is not its slot any more
    assert pause.allow_request() is False

    pause.release_probe_ticket(second)
    assert pause.allow_request() is True


def test_a_call_that_did_not_take_the_probe_has_no_ticket(clock: FakeClock) -> None:
    assert pause.allow_request() is True
    assert pause.probe_ticket() is None
    pause.release_probe_ticket(None)   # harmless
