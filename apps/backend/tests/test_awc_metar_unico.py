"""Phase 1c-1: ONE AWC METAR request and ONE cache per station, shared by Niebla and the dashboard "now".

Before, `/api/niebla` (`reportes_aeronauticos.metar`) and `/api/weather/dashboard` (`metar_observation`) each
asked AWC for the same station and kept their own cache. Now both read the raw METAR list from
`reportes_aeronauticos.awc_metar.fetch_metar_entries` and pick the report with the highest `obsTime`, each
keeping its own rules (Niebla: visibility, CAVOK, 20 km / 90 min; dashboard: `MetarObservation`, reasons).

The responses themselves are frozen by the `test_caracterizacion_aeronautica_*` suites; here only the
requests, the cache and the selection are pinned. No real service is ever called (respx and fakes only).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from httpx import AsyncClient

from app.core.cache import SingleFlightCache
from app.core.config import settings
from app.services.metar_observation import classify_observation, fetch_latest_observation, get_nearest_metar_observation
from app.services.openmeteo import VisibilityData
from app.services.reportes_aeronauticos import (
    AwcError,
    awc,
    clear_caches,
    get_metar_visibility,
    get_nearest_metar_visibility,
    set_source,
)
from app.services.reportes_aeronauticos.awc import AWC_METAR_BASE
from app.services.reportes_aeronauticos.awc_metar import (
    LatestMetar,
    fetch_metar_entries,
    latest_valid_entry,
    metar_entries_cache,
)
from tests.helpers_caracterizacion_aeronautica import (
    FROZEN_NOW,
    awc_metar,
    freeze_clock,
    minutes_before,
    reset_aeronautical_state,
)
from tests.hourly_fixtures import AR, make_hourly
from tests.test_caracterizacion_aeronautica_dashboard_metar import STATION_SAAR, _model_current, _om_current
from tests.test_dashboard_integration import _daily_ext, _multi_model

ROSARIO = (-32.95, -60.65)   # SAAR, 13.1 km
QUILMES = (-34.72, -58.25)   # SABE, 23.5 km: beyond the 20 km limit

OPEN_METEO = VisibilityData(
    current_m=3000.0, weather_code=1, fog_level=2, fog_label="Neblina o bruma", fog_color="#f0a020",
    hourly_m=[10000.0, 4000.0, 800.0], hourly_labels=["13:00", "14:00", "15:00"],
)
REPORT = {"temp": 18, "dewp": 12, "wdir": 270, "wspd": 10, "wgst": 18, "wxString": "-RA", "visib": "6+"}

# What both routes answered before this phase for `metar(10 min old, **REPORT)` (frozen by phase 1a).
NIEBLA_CAVOK = {
    "visibility_m": 10000.0, "fog_level": 0, "fog_label": "Despejada", "fog_color": "#3ecf7a", "weather_code": 1,
    "hourly": [
        {"hour_label": "13:00", "visibility_m": 10000.0, "fog_level": 0, "fog_label": "Despejada", "fog_color": "#3ecf7a"},
        {"hour_label": "14:00", "visibility_m": 4000.0, "fog_level": 2, "fog_label": "Neblina o bruma", "fog_color": "#f0a020"},
        {"hour_label": "15:00", "visibility_m": 800.0, "fog_level": 3, "fog_label": "Niebla", "fog_color": "#e03535"},
    ],
    "source": "metar", "metar_station": "SAAR", "metar_station_name": "Rosario", "metar_distance_km": 13.1,
    "hourly_source": "openmeteo",
}
DASHBOARD_FRESH = {
    "temp_c": 18.0, "feels_like_c": 18.0, "humidity": 68.0, "wind_speed_kmh": 18.5, "wind_dir_deg": 270.0,
    "wind_dir_cardinal": "W", "wind_gust_kmh": 33.3, "wind_intensity": "leve", "source": "metar",
    "source_reason": "metar_ok", "observed_at": "2026-10-08T14:50:00Z", "station": STATION_SAAR,
    "model_temp_c": 15.0, "notices": [{"code": "reported_phenomenon", "kind": "rain", "wx": "-RA"}],
}
DASHBOARD_MODEL = {"source": "openmeteo", "source_reason": "metar_unavailable", "station": None}


@pytest.fixture(autouse=True)
def _state():
    reset_aeronautical_state()
    yield
    reset_aeronautical_state()


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """The `metar_awc` usage counter: one `record` call per outgoing AWC request."""
    mock = MagicMock()
    monkeypatch.setattr(awc.usage_counter, "record", mock)
    return mock


def metar_awc_count(recorder: MagicMock) -> int:
    """How many `metar_awc` hits were recorded (the dashboard records other providers too)."""
    return [c.args[0] for c in recorder.call_args_list].count("metar_awc")


class CountingSource:
    """AWC source that answers after a pause (so concurrent callers overlap) and counts its requests."""

    def __init__(self, payload: Any, delay: float = 0.02) -> None:
        self.payload = payload
        self.delay = delay
        self.calls: list[tuple[str, int, float]] = []
        self.fail = False

    async def metar(self, icao: str, *, hours: int, timeout: float) -> Any:
        self.calls.append((icao, hours, timeout))
        await asyncio.sleep(self.delay)
        if self.fail:
            raise AwcError("forced failure")
        return self.payload

    async def taf(self, icao: str, *, timeout: float) -> Any:   # pragma: no cover - never used here
        raise AssertionError("the TAF is not part of this test")


def install(payload: Any = None, *, delay: float = 0.02) -> CountingSource:
    source = CountingSource(payload if payload is not None else [], delay)
    set_source(source)
    return source


def saar(minutes_old: float, **fields: object) -> list[dict]:
    return awc_metar(minutes_before(FROZEN_NOW, minutes_old), "SAAR", **fields)


# ---------------------------------------------------------------------------
# Niebla and the dashboard share ONE request (HTTP level, both routes)
# ---------------------------------------------------------------------------

@pytest.fixture
def both_routes(monkeypatch: pytest.MonkeyPatch):
    """Frozen clocks and stubs so /api/niebla and /api/weather/dashboard run with only AWC mocked."""
    freeze_clock(
        monkeypatch, FROZEN_NOW,
        "app.routers.weather", "app.services.metar_observation",
        "app.services.reportes_aeronauticos.metar", "app.services.reportes_aeronauticos.taf",
    )
    monkeypatch.setattr("app.routers.niebla.get_visibility_forecast", AsyncMock(return_value=OPEN_METEO))
    monkeypatch.setattr("app.routers.niebla.get_fog_inference_forecast", AsyncMock(return_value=None))
    monkeypatch.setattr("app.routers.niebla.get_nearest_taf_hourly", AsyncMock(return_value=None))


async def get_niebla(client: AsyncClient, location: tuple[float, float] = ROSARIO) -> httpx.Response:
    return await client.get("/api/niebla", params={"lat": location[0], "lon": location[1]})


async def get_dashboard_current(client: AsyncClient, location: tuple[float, float] = ROSARIO) -> dict:
    hourly = make_hourly(48, start=datetime(2026, 10, 8, tzinfo=AR), precipitations={})
    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock,
              return_value=_model_current(*location, 1)),
        patch("app.routers.weather.get_openmeteo_current", new_callable=AsyncMock, return_value=_om_current()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock,
              return_value=_multi_model(_daily_ext())),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=hourly),
    ):
        response = await client.get(f"/api/weather/dashboard?lat={location[0]}&lon={location[1]}")
    assert response.status_code == 200
    return response.json()["current"]


@pytest.mark.integration
@pytest.mark.live_current_observation
async def test_niebla_then_dashboard_make_one_request_and_count_one(
    async_client: AsyncClient, both_routes, recorder: MagicMock
) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=saar(10, **REPORT)))
        niebla = await get_niebla(async_client)
        current = await get_dashboard_current(async_client)

    assert route.call_count == 1
    assert metar_awc_count(recorder) == 1
    assert niebla.status_code == 200 and niebla.json() == NIEBLA_CAVOK
    assert {key: current[key] for key in DASHBOARD_FRESH} == DASHBOARD_FRESH


@pytest.mark.integration
@pytest.mark.live_current_observation
async def test_dashboard_then_niebla_make_one_request_and_count_one(
    async_client: AsyncClient, both_routes, recorder: MagicMock
) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=saar(10, **REPORT)))
        current = await get_dashboard_current(async_client)
        niebla = await get_niebla(async_client)

    assert route.call_count == 1
    assert metar_awc_count(recorder) == 1
    assert niebla.json() == NIEBLA_CAVOK
    assert {key: current[key] for key in DASHBOARD_FRESH} == DASHBOARD_FRESH


@pytest.mark.integration
@pytest.mark.live_current_observation
async def test_a_failing_awc_is_asked_once_and_both_routes_fall_back_as_before(
    async_client: AsyncClient, both_routes, recorder: MagicMock
) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_METAR_BASE).mock(side_effect=httpx.ReadTimeout("slow"))
        niebla = await get_niebla(async_client)
        current = await get_dashboard_current(async_client)

    assert route.call_count == 1                       # the failure is remembered: the second route does not retry
    assert metar_awc_count(recorder) == 1
    body = niebla.json()
    assert (body["source"], body["visibility_m"], body["metar_station"]) == ("openmeteo", 3000.0, "SAAR")
    assert {key: current[key] for key in DASHBOARD_MODEL} == DASHBOARD_MODEL


@pytest.mark.integration
@pytest.mark.live_current_observation
async def test_both_routes_hitting_the_same_station_at_once_make_one_request(
    async_client: AsyncClient, both_routes, recorder: MagicMock
) -> None:
    source = install(saar(10, **REPORT))
    niebla, current = await asyncio.gather(get_niebla(async_client), get_dashboard_current(async_client))

    assert len(source.calls) == 1
    assert niebla.json() == NIEBLA_CAVOK
    assert current["source"] == "metar"


# ---------------------------------------------------------------------------
# Concurrency at the service level: single-flight
# ---------------------------------------------------------------------------

async def test_concurrent_niebla_and_dashboard_callers_share_one_request() -> None:
    source = install(saar(10, **REPORT))

    visibility, selection, again = await asyncio.gather(
        get_nearest_metar_visibility(*ROSARIO, now=FROZEN_NOW),
        get_nearest_metar_observation(*ROSARIO, now=FROZEN_NOW),
        get_metar_visibility("SAAR", now=FROZEN_NOW),
    )

    assert len(source.calls) == 1
    assert visibility.visibility_m == 10_000.0
    assert selection.reason == "metar_ok"
    assert again == 10_000.0


async def test_concurrent_callers_of_different_stations_make_one_request_each() -> None:
    source = install(saar(10, **REPORT))

    await asyncio.gather(get_metar_visibility("SAAR", now=FROZEN_NOW), get_metar_visibility("SACO", now=FROZEN_NOW))

    assert sorted(call[0] for call in source.calls) == ["SAAR", "SACO"]


async def test_concurrent_callers_share_one_failure_too() -> None:
    source = install(None)
    source.fail = True

    visibility, selection = await asyncio.gather(
        get_nearest_metar_visibility(*ROSARIO, now=FROZEN_NOW),
        get_nearest_metar_observation(*ROSARIO, now=FROZEN_NOW),
    )

    assert len(source.calls) == 1
    assert visibility.visibility_m is None
    assert selection.reason == "metar_unavailable"


# ---------------------------------------------------------------------------
# What is requested: 3 hours, the 4 s observation timeout
# ---------------------------------------------------------------------------

async def test_the_request_asks_for_three_hours_with_the_observation_timeout(awc_fixtures) -> None:
    source = awc_fixtures(metar={"SAAR": saar(10, **REPORT)})

    await get_metar_visibility("SAAR", now=FROZEN_NOW)          # Niebla
    await fetch_latest_observation("SAAR")                       # dashboard: served from the same cache

    assert source.calls == [("metar", "SAAR", 3, settings.metar_observation_timeout_seconds)]
    assert settings.metar_observation_timeout_seconds == 4.0


async def test_the_http_request_carries_hours_3_and_a_four_second_read_timeout() -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=saar(10, **REPORT)))
        await get_metar_visibility("SAAR", now=FROZEN_NOW)

    request = route.calls.last.request
    assert request.url.params["hours"] == "3"
    assert request.extensions["timeout"]["read"] == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# The cache: name, lifetimes, persistence, behavior in time
# ---------------------------------------------------------------------------

def test_the_shared_cache_is_a_single_flight_cache_with_the_agreed_lifetimes() -> None:
    cache = metar_entries_cache
    assert isinstance(cache, SingleFlightCache)
    assert cache._name == "awc_metar"
    assert cache._persistence is None
    assert cache._cache.ttl == 300
    assert cache._failure_cache.ttl == 60
    assert cache._stale_cache.ttl == min(1800, settings.metar_max_age_minutes * 60)


async def test_a_success_is_cached_for_300_seconds_and_then_asked_again(metar_clock) -> None:
    source = install(saar(10, **REPORT), delay=0)

    await fetch_metar_entries("SAAR")
    metar_clock.now = 299
    await fetch_metar_entries("SAAR")
    assert len(source.calls) == 1

    metar_clock.now = 301
    await fetch_metar_entries("SAAR")
    assert len(source.calls) == 2


async def test_a_failure_is_remembered_for_60_seconds_and_then_asked_again(metar_clock) -> None:
    source = install(None, delay=0)
    source.fail = True

    assert await fetch_metar_entries("SAAR") is None
    metar_clock.now = 59
    assert await fetch_metar_entries("SAAR") is None
    assert len(source.calls) == 1

    metar_clock.now = 61
    assert await fetch_metar_entries("SAAR") is None
    assert len(source.calls) == 2


async def test_the_failure_of_a_station_does_not_hide_another_station(metar_clock) -> None:
    source = install(saar(10, **REPORT), delay=0)
    source.fail = True
    assert await fetch_metar_entries("SACO") is None

    source.fail = False
    assert await fetch_metar_entries("SAAR") is not None
    assert [call[0] for call in source.calls] == ["SACO", "SAAR"]


async def test_after_the_fresh_copy_expires_a_failing_awc_serves_the_stale_copy_to_both_consumers(
    metar_clock,
) -> None:
    source = install(saar(10, **REPORT), delay=0)
    assert (await get_nearest_metar_visibility(*ROSARIO, now=FROZEN_NOW)).visibility_m == 10_000.0

    metar_clock.now = 301                      # the fresh copy is gone, the stale one is not
    source.fail = True
    visibility = await get_nearest_metar_visibility(*ROSARIO, now=FROZEN_NOW + timedelta(minutes=5))
    selection = await get_nearest_metar_observation(*ROSARIO, now=FROZEN_NOW + timedelta(minutes=5))

    assert len(source.calls) == 2        # one failed refresh, shared by both consumers
    assert visibility.visibility_m == 10_000.0
    assert selection.reason == "metar_ok"


async def test_the_stale_copy_dies_after_its_lifetime(metar_clock) -> None:
    source = install(saar(10, **REPORT), delay=0)
    await fetch_metar_entries("SAAR")

    source.fail = True
    metar_clock.now = metar_entries_cache._stale_cache.ttl + 1
    assert await fetch_metar_entries("SAAR") is None


async def test_the_stale_copy_lives_30_minutes_and_not_a_second_more(metar_clock) -> None:
    source = install(saar(10, **REPORT), delay=0)
    await fetch_metar_entries("SAAR")

    source.fail = True
    metar_clock.now = 1799
    assert await fetch_metar_entries("SAAR") is not None
    metar_clock.now = 1801
    assert await fetch_metar_entries("SAAR") is None


async def test_a_stale_copy_never_lets_a_consumer_accept_a_report_older_than_90_minutes(metar_clock) -> None:
    source = install(saar(80, **REPORT), delay=0)
    await fetch_metar_entries("SAAR")

    metar_clock.now = 400
    source.fail = True
    later = FROZEN_NOW + timedelta(minutes=11)           # the stale report is now 91 minutes old
    visibility = await get_nearest_metar_visibility(*ROSARIO, now=later)
    selection = await get_nearest_metar_observation(*ROSARIO, now=later)

    assert visibility.visibility_m is None
    assert selection.reason == "metar_stale"


async def test_clear_caches_empties_the_shared_cache() -> None:
    source = install(saar(10, **REPORT), delay=0)
    await fetch_metar_entries("SAAR")
    await fetch_metar_entries("SAAR")
    assert len(source.calls) == 1

    clear_caches()
    await fetch_metar_entries("SAAR")
    assert len(source.calls) == 2


async def test_clearing_the_failure_cache_through_clear_caches_allows_a_retry() -> None:
    source = install(None, delay=0)
    source.fail = True
    assert await fetch_metar_entries("SAAR") is None

    source.fail = False
    source.payload = saar(10, **REPORT)
    clear_caches()
    assert await fetch_metar_entries("SAAR") is not None


# ---------------------------------------------------------------------------
# fetch_metar_entries: what counts as a usable list
# ---------------------------------------------------------------------------

async def test_a_good_list_is_returned_as_an_immutable_sequence_of_the_dict_entries() -> None:
    install([*saar(10, **REPORT), "junk", 7, None], delay=0)

    entries = await fetch_metar_entries("SAAR")

    assert isinstance(entries, tuple)
    assert [entry["icaoId"] for entry in entries] == ["SAAR"]


@pytest.mark.parametrize(
    "payload",
    [[], {"error": "boom"}, "text", None, ["junk"], [{"icaoId": "SAAR", "visib": "6+"}]],
    ids=["empty", "dict", "string", "none", "no-dicts", "no-obs-time"],
)
async def test_an_unusable_payload_is_none_and_remembered_as_a_failure(payload: Any) -> None:
    source = install(payload, delay=0)

    assert await fetch_metar_entries("SAAR") is None
    assert await fetch_metar_entries("SAAR") is None
    assert len(source.calls) == 1


async def test_the_awc_error_is_none() -> None:
    source = install(None, delay=0)
    source.fail = True
    assert await fetch_metar_entries("SAAR") is None


async def test_http_failures_are_none_and_counted_once_per_outgoing_request(recorder: MagicMock) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_METAR_BASE).mock(return_value=httpx.Response(500))
        assert await fetch_metar_entries("SAAR") is None
        assert await fetch_metar_entries("SAAR") is None

    recorder.assert_called_once_with("metar_awc")


# ---------------------------------------------------------------------------
# One selection rule: the highest valid obsTime
# ---------------------------------------------------------------------------

def _entry(minutes_old: float, **fields: object) -> dict:
    return {"icaoId": "SAAR", "obsTime": int(minutes_before(FROZEN_NOW, minutes_old).timestamp()), **fields}


def test_latest_valid_entry_is_the_highest_obs_time_whatever_the_order() -> None:
    older, newest, middle = _entry(70, tag="old"), _entry(20, tag="new"), _entry(50, tag="mid")

    latest = latest_valid_entry([older, newest, middle])

    assert isinstance(latest, LatestMetar)
    assert latest.entry["tag"] == "new"
    assert latest.observed_at == minutes_before(FROZEN_NOW, 20)
    assert latest.observed_at.tzinfo is not None


def test_latest_valid_entry_ignores_what_has_no_valid_obs_time() -> None:
    undated = [
        {"icaoId": "SAAR", "tag": "none"},
        {"obsTime": "abc", "tag": "abc"},
        {"obsTime": "", "tag": "empty"},
        {"obsTime": None, "tag": "null"},
        {"obsTime": "nan", "tag": "nan"},
        {"obsTime": "inf", "tag": "inf"},
        {"obsTime": 1e30, "tag": "huge"},
        "junk",
        7,
    ]

    assert latest_valid_entry(undated) is None
    assert latest_valid_entry([*undated, _entry(300, tag="valid")]).entry["tag"] == "valid"   # type: ignore[union-attr]
    assert latest_valid_entry([]) is None


def test_latest_valid_entry_keeps_the_first_of_two_equal_times() -> None:
    first, second = _entry(10, tag="first"), _entry(10, tag="second")
    assert latest_valid_entry([first, second]).entry["tag"] == "first"   # type: ignore[union-attr]


async def test_both_consumers_use_the_later_report_even_when_data_0_is_older() -> None:
    older = saar(70, visib=1, temp=1, dewp=0)[0]
    later = saar(20, visib="6+", temp=19, dewp=13)[0]
    install([older, later], delay=0)

    visibility = await get_nearest_metar_visibility(*ROSARIO, now=FROZEN_NOW)
    selection = await get_nearest_metar_observation(*ROSARIO, now=FROZEN_NOW)

    assert visibility.visibility_m == 10_000.0
    assert visibility.observed_at == minutes_before(FROZEN_NOW, 20)
    assert selection.observation is not None
    assert (selection.observation.temp_c, selection.observation.observed_at) == (19.0, minutes_before(FROZEN_NOW, 20))


async def test_both_consumers_ignore_entries_without_obs_time() -> None:
    undated = {"icaoId": "SAAR", "visib": 1, "temp": 1, "dewp": 0}
    install([undated, saar(20, visib="6+", temp=19, dewp=13)[0]], delay=0)

    visibility = await get_metar_visibility("SAAR", now=FROZEN_NOW)
    observation = await fetch_latest_observation("SAAR")

    assert visibility == 10_000.0
    assert observation is not None and observation.temp_c == 19.0


async def test_the_latest_report_decides_even_without_visibility() -> None:
    """Niebla does not fall back to an older report that has `visib`: the latest one is the METAR."""
    install([saar(70, visib="6+")[0], saar(20)[0]], delay=0)

    assert await get_metar_visibility("SAAR", now=FROZEN_NOW) is None


# ---------------------------------------------------------------------------
# Each consumer keeps its own rules over the same list
# ---------------------------------------------------------------------------

async def test_the_consumers_apply_their_own_age_and_distance_rules_to_the_same_cached_list() -> None:
    source = install(saar(85, **REPORT), delay=0)

    assert await get_metar_visibility("SAAR", now=FROZEN_NOW) == 10_000.0
    assert await get_metar_visibility("SAAR", now=FROZEN_NOW + timedelta(minutes=6)) is None   # 91 minutes
    observation = await fetch_latest_observation("SAAR")
    assert observation is not None
    assert classify_observation(10.0, observation, FROZEN_NOW + timedelta(minutes=5)) == "metar_ok"
    assert classify_observation(10.0, observation, FROZEN_NOW + timedelta(minutes=6)) == "metar_stale"
    assert len(source.calls) == 1


async def test_a_station_beyond_20_km_asks_nobody() -> None:
    source = install(saar(10, **REPORT), delay=0)

    visibility = await get_nearest_metar_visibility(*QUILMES, now=FROZEN_NOW)
    selection = await get_nearest_metar_observation(*QUILMES, now=FROZEN_NOW)

    assert source.calls == []
    assert visibility.visibility_m is None and visibility.icao == "SABE"
    assert selection.reason == "metar_too_far"
