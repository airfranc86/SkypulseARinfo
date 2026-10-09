"""Facade of `reportes_aeronauticos`: public names, `clear_caches()` and the METAR/TAF services over the AWC seam.

Everything runs on `FixtureAwcSource` (no HTTP at all); the real adapter is covered by
`test_awc_source.py` and by the characterization tests.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.core.config import settings

import app.services.reportes_aeronauticos as facade
from app.services.reportes_aeronauticos import (
    AwcError,
    TafFetchError,
    clear_caches,
    fetch_taf_entry,
    get_metar_visibility,
    get_nearest_metar_visibility,
    get_nearest_taf_hourly,
    get_taf_for_icao,
    taf_hourly_slots,
)
from app.services.reportes_aeronauticos.awc_metar import metar_entries_cache
from app.services.reportes_aeronauticos import taf as taf_module
from tests.helpers_caracterizacion_aeronautica import FROZEN_NOW, awc_metar, load_taf, reset_aeronautical_state

EXPECTED_PUBLIC_NAMES = {
    "AR_AIRPORTS", "Airport", "AwcError", "AwcSource", "HttpAwcSource", "MetarVisibility",
    "TafFetchError", "TafHourlySlot", "clear_caches", "fetch_taf_entry", "get_metar_visibility",
    "get_nearest_metar_visibility", "get_nearest_taf_hourly", "get_source", "get_taf_for_icao",
    "nearest_airport", "nearest_airport_with_distance", "normalize_icao", "normalize_taf",
    "set_source", "taf_hourly_slots",
}

AR = timezone(timedelta(hours=-3))
# 15:30 in Argentina = 18:30 UTC; the SACO TAF in the fixtures is valid from 18Z.
NOW_AR = datetime(2026, 10, 6, 15, 30, tzinfo=AR)


@pytest.fixture(autouse=True)
def _clean_state():
    reset_aeronautical_state()
    yield
    reset_aeronautical_state()


# ---------------------------------------------------------------- the facade


def test_the_facade_exports_exactly_the_public_names() -> None:
    assert set(facade.__all__) == EXPECTED_PUBLIC_NAMES
    for name in facade.__all__:
        assert not name.startswith("_")
        assert hasattr(facade, name)


def test_clear_caches_empties_both_the_metar_and_the_taf_cache() -> None:
    metar_entries_cache._cache["SAAR"] = object()   # type: ignore[assignment]
    taf_module._taf_cache["SACO"] = {"fcsts": [{}]}
    clear_caches()
    assert "SAAR" not in metar_entries_cache._cache
    assert "SACO" not in taf_module._taf_cache


# ---------------------------------------------------------------- fetch_taf_entry over the seam


async def test_fetch_taf_entry_returns_the_entry_and_caches_it(awc_fixtures) -> None:
    source = awc_fixtures(taf={"SACO": load_taf("SACO")})
    first = await fetch_taf_entry("SACO")
    second = await fetch_taf_entry("SACO")
    assert first is not None and first["icaoId"] == "SACO"
    assert second == first
    assert [call[0] for call in source.calls] == ["taf"]   # second answer came from the cache


async def test_fetch_taf_entry_is_none_when_the_airport_has_no_taf_and_is_not_cached(awc_fixtures) -> None:
    source = awc_fixtures(taf={})
    assert await fetch_taf_entry("SAXX") is None
    assert await fetch_taf_entry("SAXX") is None
    assert len(source.calls) == 2
    assert "SAXX" not in taf_module._taf_cache


async def test_fetch_taf_entry_without_periods_is_none_and_not_cached(awc_fixtures) -> None:
    awc_fixtures(taf={"SACO": [{"icaoId": "SACO", "fcsts": []}]})
    assert await fetch_taf_entry("SACO") is None
    assert "SACO" not in taf_module._taf_cache


async def test_fetch_taf_entry_turns_an_awc_failure_into_taf_fetch_error_and_does_not_cache(awc_fixtures) -> None:
    awc_fixtures(fail=True)
    with pytest.raises(TafFetchError) as caught:
        await fetch_taf_entry("SACO")
    assert isinstance(caught.value.__cause__, AwcError)
    assert "SACO" not in taf_module._taf_cache


async def test_get_taf_for_icao_is_tolerant_and_returns_the_periods(awc_fixtures) -> None:
    awc_fixtures(taf={"SACO": load_taf("SACO")})
    periods = await get_taf_for_icao("SACO")
    assert periods is not None and len(periods) == 5
    awc_fixtures(fail=True)
    clear_caches()
    assert await get_taf_for_icao("SACO") is None


# ---------------------------------------------------------------- /api/taf keeps its 404 / 503 / 422


@pytest.mark.integration
async def test_taf_route_answers_200_404_503_and_422(async_client: AsyncClient, awc_fixtures) -> None:
    awc_fixtures(taf={"SACO": load_taf("SACO")})
    assert (await async_client.get("/api/taf", params={"icao": "SACO"})).status_code == 200
    missing = await async_client.get("/api/taf", params={"icao": "SAXX"})
    assert (missing.status_code, missing.json()["detail"]) == (404, "taf_not_found")
    assert (await async_client.get("/api/taf", params={"icao": "SAC"})).status_code == 422
    invalid = await async_client.get("/api/taf", params={"icao": "SA-O"})
    assert (invalid.status_code, invalid.json()["detail"]) == (422, "invalid_icao")

    awc_fixtures(fail=True)
    clear_caches()
    failed = await async_client.get("/api/taf", params={"icao": "SAAR"})
    assert (failed.status_code, failed.json()["detail"]) == (503, "taf_unavailable")


# ---------------------------------------------------------------- hourly projection


def test_the_hourly_projection_is_pure_and_reads_6_plus_as_ten_km() -> None:
    fcsts = load_taf("SACO")[0]["fcsts"]
    start_ar = datetime(2026, 10, 6, 16, 0, tzinfo=AR)
    slots = taf_hourly_slots(fcsts, start_ar, 2)
    assert [s.hour_label for s in slots] == ["16:00", "17:00"]
    assert slots[0].visibility_m == 10_000.0
    assert taf_hourly_slots(copy.deepcopy(fcsts), start_ar, 2) == slots


async def test_the_nearest_hourly_forecast_takes_its_clock_from_the_caller(awc_fixtures) -> None:
    awc_fixtures(taf={"SACO": load_taf("SACO")})
    slots = await get_nearest_taf_hourly(-31.32, -64.21, hours=3, now=NOW_AR)
    assert slots is not None
    assert [s.hour_label for s in slots] == ["16:00", "17:00", "18:00"]   # next round hour in AR time


async def test_the_nearest_hourly_forecast_is_none_without_a_taf(awc_fixtures) -> None:
    awc_fixtures(taf={})
    assert await get_nearest_taf_hourly(-31.32, -64.21, hours=3, now=NOW_AR) is None


# ---------------------------------------------------------------- METAR over the seam


async def test_metar_visibility_goes_through_the_installed_source(awc_fixtures) -> None:
    obs = FROZEN_NOW - timedelta(minutes=10)
    source = awc_fixtures(metar={"SAAR": awc_metar(obs, "SAAR", visib="6+")})
    assert await get_metar_visibility("SAAR", now=FROZEN_NOW) == 10_000.0
    assert await get_metar_visibility("SAAR", now=FROZEN_NOW) == 10_000.0   # cached
    assert source.calls == [("metar", "SAAR", 3, settings.metar_observation_timeout_seconds)]


async def test_metar_visibility_is_none_when_the_source_fails(awc_fixtures) -> None:
    awc_fixtures(fail=True)
    assert await get_metar_visibility("SAAR", now=FROZEN_NOW) is None


async def test_nearest_metar_visibility_reports_the_station_even_without_data(awc_fixtures) -> None:
    awc_fixtures(metar={})
    result = await get_nearest_metar_visibility(-32.95, -60.65, now=FROZEN_NOW)
    assert (result.icao, result.visibility_m) == ("SAAR", None)
    assert result.distance_km == 13.1
