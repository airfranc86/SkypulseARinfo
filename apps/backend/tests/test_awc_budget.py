"""Call budget for AWC: a share per client AND a global cap on what goes out to aviationweather.gov.

Same budget as Open-Meteo (`core/token_bucket.ClientAndGlobalBudget`), spent in `HttpAwcSource` AFTER the 429
pause and BEFORE the usage counter and the network. METAR and TAF share it: both are "a new request to AWC".

W1 - The per-client cap (default 6/min): the 7th new request is refused without the network, the counter or the pause.
W2 - The global cap (default 40/min) is shared by every client; the client's token comes back on a global refusal.
W3 - Outside an HTTP request (no client key) nothing is capped.
W4 - A refusal is an `AwcRefused` (a `FetchRefused`): counted by reason and logged at most once a minute.
W5 - The shared `unverified` key has a larger dedicated share, still bounded by the global bucket.
W6 - A refusal is not a failure of the station: nothing is negative-cached and the stale copy is served.
W7 - A refused half-open probe gives its slot back. A shared flight spends ONE token.
W8 - Settings are validated and the structure that tracks clients is bounded.

The network is never touched (respx and in-memory sources).
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock

import httpx
import pytest
import respx
from pydantic import ValidationError

from app.core.cache import FetchRefused
from app.core.client_context import reset_client_key, set_client_key
from app.core.config import Settings, settings
from app.core.rate_limit import UNVERIFIED_CLIENT_KEY
from app.core.rate_limit_pause import awc_pause as pause
from app.services.metar_observation import get_nearest_metar_observation
from app.services.reportes_aeronauticos import (
    AwcError,
    fetch_taf_entry,
    get_metar_visibility,
    get_nearest_metar_visibility,
    get_taf_for_icao,
)
from app.services.reportes_aeronauticos import awc, awc_budget
from app.services.reportes_aeronauticos import taf as taf_module
from app.services.reportes_aeronauticos.aeropuertos import AR_AIRPORTS
from app.services.reportes_aeronauticos.awc import AWC_METAR_BASE, AWC_TAF_BASE, HttpAwcSource
from app.services.reportes_aeronauticos.awc_budget import AwcRefused
from app.services.reportes_aeronauticos.taf import TafBusyError
from app.services.reportes_aeronauticos.awc_budget import budget_refusals
from app.services.reportes_aeronauticos.awc_metar import fetch_metar_entries, metar_entries_cache
from tests.conftest import FakeClock
from tests.helpers_caracterizacion_aeronautica import FROZEN_NOW, awc_metar, load_taf, minutes_before

pytestmark = pytest.mark.integration

ROSARIO = (-32.95, -60.65)   # SAAR, 13.1 km
_NO_REFUSALS = {"client": 0, "global": 0, "unknown": 0}


@pytest.fixture
def awc_http():
    """Both AWC routes answering 200 with an empty list; yields (metar_route, taf_route)."""
    with respx.mock(assert_all_called=False) as router:
        yield (
            router.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=[])),
            router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=[])),
        )


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock()
    monkeypatch.setattr(awc.usage_counter, "record", mock)
    return mock


@pytest.fixture
def set_caps(monkeypatch: pytest.MonkeyPatch):
    def _set(*, client: int | None = None, overall: int | None = None, unknown: int | None = None) -> None:
        if unknown is not None:
            monkeypatch.setattr(settings, "awc_unknown_calls_per_minute", unknown)
        if client is not None:
            monkeypatch.setattr(settings, "awc_calls_per_client_per_minute", client)
        if overall is not None:
            monkeypatch.setattr(settings, "awc_calls_per_minute", overall)

    return _set


@contextmanager
def as_client(key: str | None) -> Iterator[None]:
    token = set_client_key(key)
    try:
        yield
    finally:
        reset_client_key(token)


KNOWN_STATIONS = [airport.icao for airport in AR_AIRPORTS]


def _known(index: int) -> str:
    """A station of the local airports list (cycled): calls to the source are not cached, so repeats are fine."""
    return KNOWN_STATIONS[index % len(KNOWN_STATIONS)]


def _unknown(index: int) -> str:
    """A code that is not in the local airports list: it also needs a token of the unknown-stations bucket."""
    return f"S{index:03d}"


async def _metar_calls(count: int, *, start: int = 0) -> list[bool]:
    """`count` METAR requests for distinct stations; True = went out, False = refused."""
    source = HttpAwcSource()
    outcomes: list[bool] = []
    for index in range(count):
        try:
            await source.metar(_known(start + index), hours=3, timeout=4.0)
            outcomes.append(True)
        except AwcRefused:
            outcomes.append(False)
    return outcomes


async def _taf_calls(count: int, *, start: int = 0) -> list[bool]:
    source = HttpAwcSource()
    outcomes: list[bool] = []
    for index in range(count):
        try:
            await source.taf(_known(start + index), timeout=4.0)
            outcomes.append(True)
        except AwcRefused:
            outcomes.append(False)
    return outcomes


# ---------------------------------------------------------------------------
# W1 - per-client cap
# ---------------------------------------------------------------------------

async def test_w1_the_7th_request_in_a_minute_from_one_client_is_refused_without_a_network_call(awc_http, counted) -> None:
    with as_client("alice"):
        outcomes = await _metar_calls(7)

    assert outcomes == [True] * 6 + [False]
    assert awc_http[0].call_count == 6
    assert counted.call_count == 6   # the refused request was not counted as an AWC request
    assert budget_refusals() == {"client": 1, "global": 0, "unknown": 0}


async def test_w1_the_metar_and_the_taf_share_the_same_client_budget(awc_http, counted) -> None:
    with as_client("alice"):
        assert await _metar_calls(3) == [True] * 3
        assert await _taf_calls(3) == [True] * 3
        assert await _metar_calls(1, start=10) == [False]
        assert await _taf_calls(1, start=10) == [False]

    assert awc_http[0].call_count == 3 and awc_http[1].call_count == 3


async def test_w1_the_share_refills_with_time(awc_http, counted, awc_budget_clock: FakeClock) -> None:
    with as_client("alice"):
        await _metar_calls(6)
        assert await _metar_calls(1, start=10) == [False]

        awc_budget_clock.advance(9)    # 6 per 60 s is one token per 10 s: 0.9 so far
        assert await _metar_calls(1, start=11) == [False]

        awc_budget_clock.advance(1.5)  # 1.05 tokens
        assert await _metar_calls(1, start=12) == [True]
        assert await _metar_calls(1, start=13) == [False]


async def test_w1_a_refusal_never_opens_the_429_pause(awc_http, counted) -> None:
    with as_client("alice"):
        await _metar_calls(20)

    assert pause.remaining() == 0.0
    assert pause.allow_request() is True


async def test_w1_the_empty_string_is_a_client_not_an_exemption(awc_http, counted, set_caps) -> None:
    set_caps(client=2)
    with as_client(""):
        assert await _metar_calls(4) == [True, True, False, False]


async def test_w1_one_client_cannot_exhaust_the_share_of_another(awc_http, counted) -> None:
    with as_client("scanner"):
        outcomes = await _metar_calls(60)
    assert sum(outcomes) == 6
    assert awc_http[0].call_count == 6

    with as_client("neighbour"):
        assert await _metar_calls(6, start=100) == [True] * 6
    assert pause.remaining() == 0.0
    assert budget_refusals() == {"client": 54, "global": 0, "unknown": 0}


# ---------------------------------------------------------------------------
# W2 - global cap
# ---------------------------------------------------------------------------

async def test_w2_the_global_cap_applies_across_clients(awc_http, counted, set_caps) -> None:
    set_caps(client=5, overall=8)
    with as_client("alice"):
        assert all(await _metar_calls(5))
    with as_client("bob"):
        outcomes = await _metar_calls(5, start=10)

    assert outcomes == [True, True, True, False, False]
    assert awc_http[0].call_count == 8
    assert budget_refusals() == {"client": 0, "global": 2, "unknown": 0}


async def test_w2_the_global_default_is_40_a_minute(awc_http, counted) -> None:
    outcomes: list[bool] = []
    for index in range(10):   # 10 clients x 6 = 60 attempts against a global cap of 40
        with as_client(f"client-{index}"):
            outcomes += await _metar_calls(6, start=index * 6)

    assert sum(outcomes) == 40
    assert budget_refusals() == {"client": 0, "global": 20, "unknown": 0}


async def test_w2_a_global_refusal_gives_the_client_token_back(awc_http, counted, set_caps, awc_budget_clock: FakeClock) -> None:
    set_caps(client=2, overall=6)   # global refills one token every 10 s
    for name in ("a", "b", "c"):
        with as_client(name):
            assert await _metar_calls(2) == [True, True]   # the global bucket is now empty
    with as_client("d"):
        assert await _metar_calls(1) == [False]            # refused by the global bucket
        assert budget_refusals() == {"client": 0, "global": 1, "unknown": 0}

        awc_budget_clock.advance(10)                       # one global token is back
        # `d` kept its two tokens only because the refused request gave its token back
        assert await _metar_calls(2, start=5) == [True, False]
    assert budget_refusals() == {"client": 0, "global": 2, "unknown": 0}   # the second one is a GLOBAL refusal, not a client one


async def test_w2_a_client_over_its_share_does_not_touch_the_global_bucket(awc_http, counted, set_caps) -> None:
    set_caps(client=2, overall=4)
    with as_client("greedy"):
        assert sum(await _metar_calls(30)) == 2
    with as_client("other"):
        assert await _metar_calls(2, start=50) == [True, True]   # 4 global tokens: 2 for greedy, 2 left


# ---------------------------------------------------------------------------
# W3 - no client key, no cap
# ---------------------------------------------------------------------------

async def test_w3_outside_an_http_request_nothing_is_capped(awc_http, counted) -> None:
    outcomes = await _metar_calls(60) + await _taf_calls(60)

    assert all(outcomes)
    assert counted.call_count == 120
    assert budget_refusals() == _NO_REFUSALS


# ---------------------------------------------------------------------------
# W4 - what a refusal is, counts and log
# ---------------------------------------------------------------------------

async def test_w4_a_refusal_is_a_fetch_refused_and_never_an_awc_error(awc_http, counted, set_caps) -> None:
    set_caps(client=1)
    with as_client("alice"):
        await _metar_calls(1)
        with pytest.raises(AwcRefused) as caught:
            await HttpAwcSource().metar("SABE", hours=3, timeout=4.0)

    assert isinstance(caught.value, FetchRefused)
    assert not isinstance(caught.value, AwcError)
    assert caught.value.reason == "client"


@pytest.mark.parametrize(
    ("client_cap", "overall_cap", "reason", "expected_wait"),
    [(6, 40, "client", 10), (2, 40, "client", 30), (50, 40, "global", 2), (50, 2, "global", 30)],
)
async def test_w4_the_refusal_says_how_long_to_wait_for_one_token(
    awc_http, counted, set_caps, client_cap: int, overall_cap: int, reason: str, expected_wait: int
) -> None:
    set_caps(client=client_cap, overall=overall_cap)
    with as_client("alice"):
        attempts = min(client_cap, overall_cap) + 1
        await _metar_calls(attempts - 1)
        with pytest.raises(AwcRefused) as caught:
            await HttpAwcSource().metar("SABE", hours=3, timeout=4.0)

    assert caught.value.reason == reason
    assert caught.value.retry_after == expected_wait
    assert isinstance(caught.value.retry_after, int)


async def test_w4_refusals_are_logged_at_most_once_a_minute_without_naming_the_client(
    awc_http, counted, set_caps, awc_budget_clock: FakeClock, caplog: pytest.LogCaptureFixture
) -> None:
    set_caps(client=1)
    caplog.set_level(logging.WARNING, logger=awc_budget.logger.name)
    with as_client("203.0.113.9"):
        await _metar_calls(1)
        await _metar_calls(10, start=5)
    lines = [r.getMessage() for r in caplog.records if "awc_budget_refused" in r.getMessage()]
    assert len(lines) == 1
    assert "client=1" in lines[0]
    assert "203.0.113.9" not in caplog.text

    awc_budget_clock.advance(61)
    with as_client("203.0.113.9"):
        assert await _metar_calls(2, start=30) == [True, False]   # one token came back, then one more refusal
    lines = [r.getMessage() for r in caplog.records if "awc_budget_refused" in r.getMessage()]
    assert len(lines) == 2
    assert "client=10" in lines[1]   # the 9 refusals not yet reported from the first minute + this one


# ---------------------------------------------------------------------------
# W5 - the shared `unverified` key
# ---------------------------------------------------------------------------

async def test_w5_the_unverified_key_gets_half_the_global_cap_and_others_keep_their_share(awc_http, counted) -> None:
    with as_client(UNVERIFIED_CLIENT_KEY):
        outcomes = await _metar_calls(21)
    assert outcomes == [True] * 20 + [False]   # 40 // 2

    with as_client("alice"):
        assert await _metar_calls(7, start=50) == [True] * 6 + [False]


async def test_w5_the_unverified_key_is_still_bounded_by_the_global_bucket(awc_http, counted, set_caps) -> None:
    set_caps(client=3, overall=10)   # unverified share = max(10 // 2, 3) = 5
    with as_client(UNVERIFIED_CLIENT_KEY):
        assert await _metar_calls(6) == [True] * 5 + [False]
    with as_client("alice"):
        assert all(await _metar_calls(3, start=10))   # global: 8 of 10 used
    with as_client("bob"):
        assert await _metar_calls(3, start=20) == [True, True, False]
    assert budget_refusals()["global"] == 1


async def test_w5_the_unverified_share_is_never_below_the_ordinary_one(awc_http, counted, set_caps) -> None:
    set_caps(client=8, overall=10)   # 10 // 2 = 5 would be less than an ordinary client's 8
    with as_client(UNVERIFIED_CLIENT_KEY):
        assert await _metar_calls(9) == [True] * 8 + [False]


# ---------------------------------------------------------------------------
# W6 - a refusal is not a failure of the station
# ---------------------------------------------------------------------------

async def test_w6_a_refused_station_is_not_remembered_as_failed_and_another_client_fetches_it(set_caps) -> None:
    set_caps(client=1)
    payload = awc_metar(minutes_before(FROZEN_NOW, 10), "SAAR", visib="6+", temp=18, dewp=12)
    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=payload))
        with as_client("alice"):
            await _metar_calls(1)
            assert await fetch_metar_entries("SAAR") is None     # over her share
        assert len(metar_entries_cache._failure_cache) == 0
        with as_client("bob"):
            assert await fetch_metar_entries("SAAR") is not None  # goes out: nobody poisoned the station
    assert route.call_count == 2


async def test_w6_a_refused_taf_is_not_remembered_as_failed_and_another_client_fetches_it(set_caps) -> None:
    set_caps(client=1)
    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=load_taf("SACO")))
        with as_client("alice"):
            await _taf_calls(1)
            with pytest.raises(TafBusyError):
                await fetch_taf_entry("SACO")
        assert len(taf_module._taf_cache._failure_cache) == 0
        with as_client("bob"):
            assert await fetch_taf_entry("SACO") is not None
    assert route.call_count == 2


async def test_w6_the_refused_client_gets_the_stale_metar_and_another_client_refreshes_it(metar_clock, set_caps) -> None:
    set_caps(client=2)
    payload = awc_metar(minutes_before(FROZEN_NOW, 10), "SAAR", visib="6+", temp=18, dewp=12)
    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=payload))
        with as_client("alice"):
            first = await fetch_metar_entries("SAAR")
            metar_clock.now = 301.0                              # the fresh copy expired; the stale one stays
            await _metar_calls(1, start=20)                      # her second and last token
            assert await fetch_metar_entries("SAAR") is first    # refused: the stale copy is served
        assert len(metar_entries_cache._failure_cache) == 0
        calls_before = route.call_count
        with as_client("bob"):
            refreshed = await fetch_metar_entries("SAAR")
        assert refreshed is not None and refreshed is not first
        assert route.call_count == calls_before + 1


async def test_w6_a_refused_client_keeps_the_cached_stations_available(set_caps) -> None:
    set_caps(client=1)
    payload = awc_metar(minutes_before(FROZEN_NOW, 10), "SAAR", visib="6+", temp=18, dewp=12)
    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=payload))
        with as_client("alice"):
            first = await fetch_metar_entries("SAAR")     # her only token
            assert await fetch_metar_entries("SABE") is None
            assert await fetch_metar_entries("SAAR") is first   # a cache hit needs no token
    assert route.call_count == 1


async def test_w6_niebla_and_the_dashboard_get_none_when_refused_and_never_an_error(set_caps) -> None:
    set_caps(client=1)
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=[]))
        with as_client("alice"):
            await _metar_calls(1)
            visibility = await get_nearest_metar_visibility(*ROSARIO, now=FROZEN_NOW)
            selection = await get_nearest_metar_observation(*ROSARIO, now=FROZEN_NOW)
            assert await get_metar_visibility("SAAR", FROZEN_NOW) is None
            assert await get_taf_for_icao("SACO") is None

    assert visibility.visibility_m is None and visibility.icao == "SAAR"
    assert selection.reason == "metar_unavailable"


async def test_w6_the_waiters_of_a_refused_flight_get_the_same_outcome(set_caps) -> None:
    set_caps(client=1)
    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=[]))
        with as_client("alice"):
            await _metar_calls(1)
            results = await asyncio.gather(*[fetch_metar_entries("SABE") for _ in range(5)])

    assert results == [None] * 5
    assert len(metar_entries_cache._failure_cache) == 0
    assert route.call_count == 1


# ---------------------------------------------------------------------------
# W7 - probe slot, shared flights
# ---------------------------------------------------------------------------

async def test_w7_a_refused_probe_does_not_block_the_next_caller(awc_http, counted, set_caps) -> None:
    set_caps(client=1)
    pause_clock = FakeClock()
    pause.clock = pause_clock
    with as_client("alice"):
        assert await _metar_calls(1) == [True]    # her only token
    pause.trip()
    pause_clock.advance(120)

    with as_client("alice"):
        assert await _metar_calls(1, start=1) == [False]   # takes the probe slot, then her share refuses her
    assert budget_refusals()["client"] == 1

    with as_client("bob"):
        assert await _metar_calls(1, start=2) == [True]    # bob is the probe and reopens the traffic
    assert awc_http[0].call_count == 2
    assert pause.remaining() == 0.0


async def test_w7_a_shared_flight_spends_one_token_however_many_wait_for_it(set_caps) -> None:
    set_caps(client=3)

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return httpx.Response(200, json=[])

    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_METAR_BASE).mock(side_effect=slow)

        async def as_(key: str):
            with as_client(key):
                return await fetch_metar_entries("SAAR")

        await asyncio.gather(as_("alice"), as_("bob"), as_("carol"))
        assert route.call_count == 1
        with as_client("bob"):
            assert all(await _metar_calls(3, start=10))   # bob paid nothing for the shared flight


async def test_w7_a_cached_answer_spends_nothing(set_caps) -> None:
    set_caps(client=1)
    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=load_taf("SACO")))
        with as_client("alice"):
            for _ in range(10):
                assert await fetch_taf_entry("SACO") is not None
    assert route.call_count == 1
    assert budget_refusals() == _NO_REFUSALS


# ---------------------------------------------------------------------------
# W8 - settings and bounds
# ---------------------------------------------------------------------------

def test_w8_the_defaults_are_6_per_client_and_40_overall() -> None:
    defaults = Settings(_env_file=None)

    assert defaults.awc_calls_per_client_per_minute == 6
    assert defaults.awc_calls_per_minute == 40


@pytest.mark.parametrize("name", ["awc_calls_per_client_per_minute", "awc_calls_per_minute"])
@pytest.mark.parametrize("value", [0, -1])
def test_w8_a_cap_below_one_is_rejected(name: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{name: value})


def test_w8_the_caps_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWC_CALLS_PER_CLIENT_PER_MINUTE", "3")
    monkeypatch.setenv("AWC_CALLS_PER_MINUTE", "25")

    configured = Settings(_env_file=None)

    assert configured.awc_calls_per_client_per_minute == 3
    assert configured.awc_calls_per_minute == 25


async def test_w8_the_number_of_tracked_clients_is_bounded(awc_http, counted, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(awc_budget, "_MAX_TRACKED_CLIENTS", 4)

    for index in range(10):
        with as_client(f"client-{index}"):
            assert await _metar_calls(1, start=index) == [True]

    assert awc_budget._budget().tracked_clients == 4


# ---------------------------------------------------------------------------
# W9 - stations that are not in the local airports list share one small global bucket
# ---------------------------------------------------------------------------
# `/api/taf?icao=` accepts any 4-character code. A sweep of made-up codes must not drain the global budget that the
# ~20 known stations (Niebla, the dashboard) live on: an unknown code ALSO needs a token of a separate bucket
# (default 8 a minute, for everybody together), so known stations always keep at least global - unknown = 32 tokens.

async def _unknown_calls(count: int, *, start: int = 0, kind: str = "metar") -> list[bool]:
    source = HttpAwcSource()
    outcomes: list[bool] = []
    for index in range(count):
        try:
            if kind == "metar":
                await source.metar(_unknown(start + index), hours=3, timeout=4.0)
            else:
                await source.taf(_unknown(start + index), timeout=4.0)
            outcomes.append(True)
        except AwcRefused:
            outcomes.append(False)
    return outcomes


def test_w9_the_unknown_cap_defaults_to_8_and_is_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    assert Settings(_env_file=None).awc_unknown_calls_per_minute == 8
    for value in (0, -1):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, awc_unknown_calls_per_minute=value)
    monkeypatch.setenv("AWC_UNKNOWN_CALLS_PER_MINUTE", "3")
    assert Settings(_env_file=None).awc_unknown_calls_per_minute == 3


async def test_w9_the_9th_unknown_station_in_a_minute_is_refused_while_a_known_one_still_passes(
    awc_http, counted, set_caps
) -> None:
    set_caps(client=50, overall=100)
    with as_client("alice"):
        assert await _unknown_calls(9) == [True] * 8 + [False]
        assert await _metar_calls(3) == [True] * 3   # known stations are not affected

    assert awc_http[0].call_count == 11
    assert counted.call_count == 11
    assert budget_refusals() == {"client": 0, "global": 0, "unknown": 1}


async def test_w9_the_refusal_is_an_awc_refused_with_the_wait_and_never_opens_the_pause(
    awc_http, counted, set_caps
) -> None:
    set_caps(client=50, overall=100, unknown=1)
    with as_client("alice"):
        await _unknown_calls(1)
        with pytest.raises(AwcRefused) as caught:
            await HttpAwcSource().taf("SAXY", timeout=4.0)

    assert isinstance(caught.value, FetchRefused) and not isinstance(caught.value, AwcError)
    assert caught.value.reason == "unknown"
    assert caught.value.retry_after == 60
    assert pause.remaining() == 0.0
    assert counted.call_count == 1


async def test_w9_the_wait_for_one_unknown_token_follows_the_cap(awc_http, counted, set_caps) -> None:
    set_caps(client=50, overall=100, unknown=8)
    with as_client("alice"):
        await _unknown_calls(8)
        with pytest.raises(AwcRefused) as caught:
            await HttpAwcSource().metar("SAXY", hours=3, timeout=4.0)

    assert caught.value.retry_after == 8   # ceil(60 / 8)


async def test_w9_the_unknown_cap_is_shared_by_every_client(awc_http, counted, set_caps) -> None:
    set_caps(client=50, overall=100)
    outcomes: list[bool] = []
    for index, name in enumerate(("a", "b", "c", "d")):
        with as_client(name):
            outcomes += await _unknown_calls(3, start=index * 3)

    assert outcomes == [True] * 8 + [False] * 4


async def test_w9_the_unknown_bucket_refills_with_time(awc_http, counted, set_caps, awc_budget_clock: FakeClock) -> None:
    set_caps(client=50, overall=100, unknown=8)
    with as_client("alice"):
        await _unknown_calls(8)
        awc_budget_clock.advance(7.0)     # 8 per 60 s is one token per 7.5 s
        assert await _unknown_calls(1, start=20) == [False]
        awc_budget_clock.advance(1.0)
        assert await _unknown_calls(1, start=21) == [True]


async def test_w9_known_stations_keep_global_minus_unknown_tokens_even_under_a_sweep(awc_http, counted) -> None:
    outcomes: list[bool] = []
    for index in range(6):   # six clients sweep 20 made-up codes each: only 8 get through, together
        with as_client(f"sweeper-{index}"):
            outcomes += await _unknown_calls(20, start=index * 20)
    assert sum(outcomes) == 8

    known: list[bool] = []
    for index in range(7):   # defaults: global 40, per client 6 -> known stations still have 40 - 8 = 32
        with as_client(f"visitor-{index}"):
            known += await _metar_calls(6, start=index)
    assert sum(known) == 32


async def test_w9_an_unknown_refusal_gives_back_the_client_token(awc_http, counted, set_caps) -> None:
    set_caps(client=3, overall=100, unknown=1)
    with as_client("alice"):
        assert await _unknown_calls(1) == [True]
        assert await _unknown_calls(1, start=1) == [False]      # refused by the unknown bucket
        assert await _metar_calls(3) == [True, True, False]      # 3 - 1 spent = 2 tokens left: the refusal cost nothing

    assert budget_refusals() == {"client": 1, "global": 0, "unknown": 1}


async def test_w9_an_unknown_refusal_gives_back_the_global_token(awc_http, counted, set_caps) -> None:
    set_caps(client=50, overall=3, unknown=1)
    with as_client("alice"):
        assert await _unknown_calls(1) == [True]
        assert await _unknown_calls(1, start=1) == [False]
    with as_client("bob"):
        assert await _metar_calls(3) == [True, True, False]      # 3 - 1 spent = 2 global tokens left

    assert budget_refusals() == {"client": 0, "global": 1, "unknown": 1}


async def test_w9_a_client_refusal_does_not_spend_the_unknown_token(awc_http, counted, set_caps) -> None:
    set_caps(client=1, overall=100, unknown=2)
    with as_client("alice"):
        assert await _metar_calls(1) == [True]
        assert await _unknown_calls(5) == [False] * 5            # over her share: refused before the unknown bucket
    with as_client("bob"):
        assert await _unknown_calls(1, start=10) == [True]       # the unknown bucket is untouched
    with as_client("carol"):
        assert await _unknown_calls(1, start=11) == [True]
    with as_client("dave"):
        assert await _unknown_calls(1, start=12) == [False]


async def test_w9_a_global_refusal_does_not_spend_the_unknown_token(awc_http, counted, set_caps) -> None:
    set_caps(client=50, overall=2, unknown=5)
    with as_client("erin"):
        assert await _unknown_calls(3) == [True, True, False]    # the third is refused by the global bucket
    set_caps(overall=100)
    awc_budget._reset_for_tests()                                 # rebuilt with a roomy global bucket and full tokens
    with as_client("frank"):
        assert await _unknown_calls(6, start=10) == [True] * 5 + [False]


async def test_w9_an_unknown_refusal_gives_the_probe_slot_back(awc_http, counted, set_caps) -> None:
    set_caps(client=50, overall=100, unknown=1)
    pause_clock = FakeClock()
    pause.clock = pause_clock
    with as_client("alice"):
        assert await _unknown_calls(1) == [True]
    pause.trip()
    pause_clock.advance(120)

    with as_client("alice"):
        assert await _unknown_calls(1, start=1) == [False]       # takes the probe slot, then the unknown bucket refuses
    with as_client("bob"):
        assert await _metar_calls(1) == [True]                   # bob is the probe and reopens the traffic
    assert pause.remaining() == 0.0


async def test_w9_outside_an_http_request_the_unknown_cap_does_not_apply(awc_http, counted) -> None:
    assert all(await _unknown_calls(30))
    assert budget_refusals() == _NO_REFUSALS


async def test_w9_the_unverified_key_is_bounded_by_the_unknown_cap_too(awc_http, counted) -> None:
    with as_client(UNVERIFIED_CLIENT_KEY):
        assert await _unknown_calls(10) == [True] * 8 + [False] * 2


async def test_w9_a_known_station_never_uses_the_unknown_bucket_whatever_its_spelling(awc_http, counted, set_caps) -> None:
    set_caps(client=100, overall=100, unknown=1)
    source = HttpAwcSource()
    with as_client("alice"):
        for spelling in ("SAAR", "saar", " Saar ", "saco", " SAEZ "):
            await source.metar(spelling, hours=3, timeout=4.0)
            await source.taf(spelling, timeout=4.0)
    assert budget_refusals() == _NO_REFUSALS


async def test_w9_an_unknown_station_in_any_spelling_is_still_unknown(awc_http, counted, set_caps) -> None:
    set_caps(client=100, overall=100, unknown=1)
    source = HttpAwcSource()
    with as_client("alice"):
        await source.metar("saxx", hours=3, timeout=4.0)
        with pytest.raises(AwcRefused):
            await source.metar(" SAXY ", hours=3, timeout=4.0)


async def test_w9_the_taf_of_an_unknown_station_is_asked_once_whatever_the_cap(set_caps) -> None:
    set_caps(client=100, overall=100, unknown=1)
    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=[]))
        with as_client("alice"):
            for _ in range(5):
                assert await fetch_taf_entry("SAXX") is None        # remembered as "no TAF": no new token
    assert route.call_count == 1
    assert budget_refusals() == _NO_REFUSALS


async def test_w9_a_refused_unknown_taf_is_busy_and_not_remembered_as_a_failure(set_caps) -> None:
    set_caps(client=100, overall=100, unknown=1)
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=[]))
        with as_client("alice"):
            assert await fetch_taf_entry("SAXX") is None
            with pytest.raises(TafBusyError):
                await fetch_taf_entry("SAXY")
        assert "SAXY" not in taf_module._taf_cache._failure_cache


async def test_w9_the_known_metar_readers_are_not_affected(set_caps) -> None:
    set_caps(client=100, overall=100, unknown=1)
    payload = awc_metar(minutes_before(FROZEN_NOW, 10), "SAAR", visib="6+", temp=18, dewp=12)
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=payload))
        with as_client("alice"):
            assert await get_metar_visibility("SAAR", FROZEN_NOW) == 10_000.0
            visibility = await get_nearest_metar_visibility(*ROSARIO, now=FROZEN_NOW)
            selection = await get_nearest_metar_observation(*ROSARIO, now=FROZEN_NOW)
    assert visibility.visibility_m == 10_000.0
    assert selection.reason == "metar_ok"


# ---------------------------------------------------------------------------
# logs of refusals are bounded
# ---------------------------------------------------------------------------

async def test_a_pause_rejection_writes_no_line_per_call_at_info_or_above(caplog: pytest.LogCaptureFixture) -> None:
    pause.trip()
    caplog.set_level(logging.INFO, logger=awc_budget.logger.name)
    for _ in range(20):
        with pytest.raises(AwcRefused):
            await HttpAwcSource().metar("SAAR", hours=3, timeout=4.0)

    assert [r for r in caplog.records if r.name == awc_budget.logger.name] == []
