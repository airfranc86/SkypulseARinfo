"""Phase 1c-2: ONE AWC request per station for the TAF, a remembered "no TAF", and a normalised ICAO.

Before, the TAF cache (`TTLCache`) had no single-flight (two simultaneous callers made two AWC requests), did
not remember that a station has no TAF (every repeat went out again, and `/api/taf?icao=XXXX` accepts ANY
4-character code) and failures were not remembered at all. Now:

- the entry of a station lives 60 min, a failure 60 s, and concurrent callers share one request (`SingleFlightCache`);
- "AWC answered but there is no TAF" is remembered 300 s in its own small cache;
- `fetch_taf_entry` keeps its contract: a `dict`, `None` for "no TAF" and `TafFetchError` for "could not ask";
- the ICAO is `strip().upper()`-ed inside the package, for the METAR cache key too.

AWC is replaced by in-memory sources; the network is never touched.
"""
from __future__ import annotations

import asyncio
import copy
from typing import Any

import pytest

from app.services.reportes_aeronauticos import (
    AwcError,
    TafFetchError,
    clear_caches,
    fetch_taf_entry,
    get_metar_visibility,
    get_source,
    get_taf_for_icao,
    set_source,
)
from app.services.reportes_aeronauticos import taf as taf_module
from app.services.reportes_aeronauticos.awc_metar import fetch_metar_entries, metar_entries_cache
from tests.helpers_caracterizacion_aeronautica import FROZEN_NOW, awc_metar, load_taf, minutes_before


class SlowSource:
    """AWC source that answers after a pause (so concurrent callers overlap) and records each request."""

    def __init__(self, *, taf: dict[str, Any] | None = None, metar: dict[str, Any] | None = None, delay: float = 0.02) -> None:
        self.taf_payloads = dict(taf or {})
        self.metar_payloads = dict(metar or {})
        self.delay = delay
        self.fail = False
        self.taf_calls: list[str] = []
        self.metar_calls: list[str] = []

    async def metar(self, icao: str, *, hours: int, timeout: float) -> Any:
        self.metar_calls.append(icao)
        await asyncio.sleep(self.delay)
        if self.fail:
            raise AwcError("forced failure")
        return copy.deepcopy(self.metar_payloads.get(icao, []))

    async def taf(self, icao: str, *, timeout: float) -> Any:
        self.taf_calls.append(icao)
        await asyncio.sleep(self.delay)
        if self.fail:
            raise AwcError("forced failure")
        return copy.deepcopy(self.taf_payloads.get(icao, []))


@pytest.fixture(autouse=True)
def _restore_source():
    original = get_source()
    yield
    set_source(original)


@pytest.fixture
def source():
    """A `SlowSource` serving the real SACO TAF, installed as the AWC source for the test."""
    installed = SlowSource(taf={"SACO": load_taf("SACO")})
    set_source(installed)
    return installed


# ---------------------------------------------------------------------------
# one request per station
# ---------------------------------------------------------------------------

async def test_concurrent_callers_of_one_station_make_one_request_and_share_the_entry(source: SlowSource) -> None:
    entries = await asyncio.gather(*[fetch_taf_entry("SACO") for _ in range(5)])

    assert source.taf_calls == ["SACO"]
    assert all(entry is entries[0] and entry is not None for entry in entries)


async def test_the_niebla_helper_and_the_route_helper_share_the_same_request(source: SlowSource) -> None:
    entry, fcsts = await asyncio.gather(fetch_taf_entry("SACO"), get_taf_for_icao("SACO"))

    assert source.taf_calls == ["SACO"]
    assert fcsts == entry["fcsts"]


async def test_concurrent_callers_of_different_stations_make_one_request_each(source: SlowSource) -> None:
    source.taf_payloads["SAAR"] = load_taf("SAAR")

    await asyncio.gather(fetch_taf_entry("SACO"), fetch_taf_entry("SAAR"), fetch_taf_entry("SACO"))

    assert sorted(source.taf_calls) == ["SAAR", "SACO"]


async def test_concurrent_callers_share_one_failure_too(source: SlowSource) -> None:
    source.fail = True

    results = await asyncio.gather(*[fetch_taf_entry("SACO") for _ in range(4)], return_exceptions=True)

    assert source.taf_calls == ["SACO"]
    assert all(isinstance(result, TafFetchError) for result in results)


async def test_concurrent_callers_share_one_no_taf_answer(source: SlowSource) -> None:
    results = await asyncio.gather(*[fetch_taf_entry("SAXX") for _ in range(4)])

    assert source.taf_calls == ["SAXX"]
    assert results == [None] * 4


# ---------------------------------------------------------------------------
# lifetimes
# ---------------------------------------------------------------------------

async def test_the_entry_cache_is_bounded_to_64_stations(source: SlowSource) -> None:
    source.delay = 0
    for index in range(80):
        source.taf_payloads[f"S{index:03d}"] = load_taf("SACO")
        assert await fetch_taf_entry(f"S{index:03d}") is not None

    assert len(taf_module._taf_cache._cache) == 64


async def test_an_entry_is_cached_for_an_hour_and_then_asked_again(source: SlowSource, taf_clock) -> None:
    first = await fetch_taf_entry("SACO")
    taf_clock.now = 3599.0
    assert await fetch_taf_entry("SACO") is first
    assert source.taf_calls == ["SACO"]

    taf_clock.now = 3601.0
    assert await fetch_taf_entry("SACO") is not first
    assert source.taf_calls == ["SACO", "SACO"]


async def test_a_failure_is_remembered_for_60_seconds_and_then_asked_again(source: SlowSource, taf_clock) -> None:
    source.fail = True
    with pytest.raises(TafFetchError):
        await fetch_taf_entry("SACO")

    taf_clock.now = 59.0
    with pytest.raises(TafFetchError):        # remembered: the answer is still "could not ask", never "no TAF"
        await fetch_taf_entry("SACO")
    assert source.taf_calls == ["SACO"]

    taf_clock.now = 61.0
    source.fail = False
    assert await fetch_taf_entry("SACO") is not None
    assert source.taf_calls == ["SACO", "SACO"]


@pytest.mark.parametrize(
    "payload",
    [[], [{"icaoId": "SAXX", "fcsts": []}], [{"icaoId": "SAXX"}]],
)
async def test_a_station_without_taf_is_remembered_for_300_seconds_and_then_asked_again(
    source: SlowSource, taf_clock, payload: Any
) -> None:
    source.taf_payloads["SAXX"] = payload

    assert await fetch_taf_entry("SAXX") is None
    taf_clock.now = 299.0
    assert await fetch_taf_entry("SAXX") is None
    assert await get_taf_for_icao("SAXX") is None
    assert source.taf_calls == ["SAXX"]   # repeating a station without TAF does not go out again

    taf_clock.now = 301.0
    assert await fetch_taf_entry("SAXX") is None
    assert source.taf_calls == ["SAXX", "SAXX"]


@pytest.mark.parametrize("payload", [{"oops": 1}, {}, [None], ["x"], [[]], "text", 42, None])
async def test_a_200_with_an_unrecognised_shape_is_no_taf_remembered_for_300_seconds(
    source: SlowSource, taf_clock, payload: Any
) -> None:
    """Frozen contract of `/api/taf`: whatever 200 body has no usable first entry is "no TAF" (404), not a 503."""
    source.taf_payloads["SAXX"] = payload

    assert await fetch_taf_entry("SAXX") is None
    assert "SAXX" in taf_module._no_taf_cache
    taf_clock.now = 299.0
    assert await fetch_taf_entry("SAXX") is None
    assert await get_taf_for_icao("SAXX") is None
    assert source.taf_calls == ["SAXX"]                         # one request within the 300 s

    taf_clock.now = 301.0
    source.taf_payloads["SAXX"] = load_taf("SACO")
    assert await fetch_taf_entry("SAXX") is not None


async def test_a_station_that_publishes_a_taf_later_is_found_after_the_memory_expires(source: SlowSource, taf_clock) -> None:
    assert await fetch_taf_entry("SAXX") is None
    source.taf_payloads["SAXX"] = load_taf("SACO")

    taf_clock.now = 301.0

    assert await fetch_taf_entry("SAXX") is not None


async def test_no_taf_is_not_a_failure_and_a_failure_is_not_no_taf(source: SlowSource) -> None:
    assert await fetch_taf_entry("SAXX") is None
    assert len(taf_module._taf_cache._cache) == 0             # nothing positive was stored for it

    source.fail = True
    with pytest.raises(TafFetchError):
        await fetch_taf_entry("SACO")
    assert "SACO" not in taf_module._no_taf_cache             # a failure does not say "there is no TAF"


async def test_an_old_taf_that_disappears_from_awc_is_no_taf_and_not_the_stale_copy(source: SlowSource, taf_clock) -> None:
    assert await fetch_taf_entry("SACO") is not None
    taf_clock.now = 3601.0
    source.taf_payloads["SACO"] = []   # AWC answers, but the station has no TAF any more

    assert await fetch_taf_entry("SACO") is None
    assert await fetch_taf_entry("SACO") is None
    assert source.taf_calls == ["SACO", "SACO"]


async def test_the_last_good_taf_is_served_when_awc_fails_after_the_hour(source: SlowSource, taf_clock) -> None:
    first = await fetch_taf_entry("SACO")
    taf_clock.now = 3601.0
    source.fail = True

    assert await fetch_taf_entry("SACO") is first


async def test_a_failed_refresh_serves_the_last_good_taf_for_up_to_three_hours(source: SlowSource, taf_clock) -> None:
    first = await fetch_taf_entry("SACO")
    taf_clock.now = 3601.0                       # the fresh copy (1 h) expired
    source.fail = True

    assert await fetch_taf_entry("SACO") is first
    taf_clock.now = 10799.0                      # still inside the 3 h of the stale copy; the 60 s failure memory is over
    assert await fetch_taf_entry("SACO") is first

    taf_clock.now = 10801.0                      # past 3 h: nothing good is left to serve
    with pytest.raises(TafFetchError):
        await fetch_taf_entry("SACO")


async def test_the_stale_taf_does_not_outlive_three_hours_when_the_station_loses_its_taf(source: SlowSource, taf_clock) -> None:
    await fetch_taf_entry("SACO")
    taf_clock.now = 10801.0
    source.taf_payloads["SACO"] = []

    assert await fetch_taf_entry("SACO") is None


async def test_failures_are_not_cached_as_entries(source: SlowSource) -> None:
    source.fail = True
    with pytest.raises(TafFetchError):
        await fetch_taf_entry("SACO")

    assert "SACO" not in taf_module._taf_cache._cache


async def test_the_no_taf_memory_is_bounded(source: SlowSource) -> None:
    source.delay = 0
    for index in range(200):
        assert await fetch_taf_entry(f"S{index:03d}") is None

    assert len(taf_module._no_taf_cache) <= 64


# ---------------------------------------------------------------------------
# clearing
# ---------------------------------------------------------------------------

async def test_clear_caches_forgets_entries_failures_and_no_taf(source: SlowSource) -> None:
    await fetch_taf_entry("SACO")
    await fetch_taf_entry("SAXX")
    source.fail = True
    with pytest.raises(TafFetchError):
        await fetch_taf_entry("SAAR")
    assert source.taf_calls == ["SACO", "SAXX", "SAAR"]

    clear_caches()
    source.fail = False
    await fetch_taf_entry("SACO")
    await fetch_taf_entry("SAXX")
    await fetch_taf_entry("SAAR")

    assert source.taf_calls == ["SACO", "SAXX", "SAAR", "SACO", "SAXX", "SAAR"]


def test_clear_taf_cache_empties_both_stores() -> None:
    taf_module._no_taf_cache["SAXX"] = True
    taf_module.clear_taf_cache()

    assert len(taf_module._no_taf_cache) == 0
    assert len(taf_module._taf_cache._cache) == 0


# ---------------------------------------------------------------------------
# the ICAO is normalised inside the package
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("spelling", ["saco", "SACO", " saco ", "Saco\n"])
async def test_every_spelling_of_a_taf_station_shares_one_entry_and_one_request(source: SlowSource, spelling: str) -> None:
    first = await fetch_taf_entry("SACO")

    assert await fetch_taf_entry(spelling) is first
    assert source.taf_calls == ["SACO"]


async def test_the_taf_request_carries_the_normalised_code(source: SlowSource) -> None:
    await fetch_taf_entry(" saco ")

    assert source.taf_calls == ["SACO"]


async def test_a_lower_case_spelling_of_a_station_without_taf_hits_the_same_memory(source: SlowSource) -> None:
    assert await fetch_taf_entry("saxx") is None
    assert await fetch_taf_entry("SAXX") is None

    assert source.taf_calls == ["SAXX"]


async def test_concurrent_spellings_of_one_station_make_one_request(source: SlowSource) -> None:
    await asyncio.gather(fetch_taf_entry("saco"), fetch_taf_entry("SACO"), fetch_taf_entry("Saco"))

    assert source.taf_calls == ["SACO"]


async def test_metar_visibility_of_saar_and_SAAR_share_one_entry_and_one_request() -> None:
    payload = awc_metar(minutes_before(FROZEN_NOW, 10), "SAAR", visib="6+", temp=18, dewp=12)
    installed = SlowSource(metar={"SAAR": payload}, delay=0)
    set_source(installed)

    lower = await get_metar_visibility("saar", FROZEN_NOW)
    upper = await get_metar_visibility("SAAR", FROZEN_NOW)

    assert lower is not None and lower == upper
    assert installed.metar_calls == ["SAAR"]
    assert list(metar_entries_cache._cache.keys()) == ["SAAR"]


async def test_the_metar_cache_key_and_request_use_the_normalised_code() -> None:
    installed = SlowSource(metar={"SAAR": awc_metar(minutes_before(FROZEN_NOW, 10), "SAAR", visib="6+")}, delay=0)
    set_source(installed)

    first = await fetch_metar_entries(" saar ")

    assert first is not None
    assert await fetch_metar_entries("SAAR") is first
    assert installed.metar_calls == ["SAAR"]
