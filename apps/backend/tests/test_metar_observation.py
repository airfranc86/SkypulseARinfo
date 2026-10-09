"""Tests for app.services.metar_observation (AWC METAR as the dashboard "now", FRA-320)."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import httpx
import pytest
import respx

from app.services.metar_observation import (
    MetarObservation,
    classify_observation,
    fetch_latest_observation,
    get_nearest_metar_observation,
    relative_humidity,
)
from app.services.reportes_aeronauticos import awc
from app.services.reportes_aeronauticos.awc import AWC_METAR_BASE as AWC_METAR_URL
from app.services.reportes_aeronauticos.awc_metar import metar_entries_cache

OBS_TIME = datetime(2026, 10, 5, 21, 0, tzinfo=timezone.utc)
NOW = OBS_TIME + timedelta(minutes=20)
_MISSING = object()

# Rosario city centre: SAAR is ~13 km away. Santiago del Estero: nearest airport (SANT) is >100 km.
# Quilmes: nearest airport (SABE) is ~23.5 km away, inside the old 30 km limit but beyond the 20 km one.
ROSARIO = (-32.95, -60.65)
QUILMES = (-34.72, -58.25)
SANTIAGO_DEL_ESTERO = (-27.78, -64.27)


def _entry(**overrides: object) -> dict:
    base: dict = {
        "icaoId": "SAAR",
        "obsTime": int(OBS_TIME.timestamp()),
        "temp": 22,
        "dewp": 11,
        "wdir": 80,
        "wspd": 8,
        "rawOb": "METAR SAAR 052100Z 08008KT CAVOK 22/11 Q1013",
    }
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not _MISSING}


def _observation(**overrides: object) -> MetarObservation:
    base = MetarObservation(
        icao="SAAR",
        observed_at=OBS_TIME,
        temp_c=22.0,
        dewpoint_c=11.0,
        humidity=50.0,
        wind_dir_deg=80.0,
        wind_speed_kmh=14.8,
        wind_gust_kmh=None,
        wx_string=None,
        raw="METAR SAAR 052100Z 08008KT CAVOK 22/11 Q1013",
    )
    return replace(base, **overrides)


async def _fetch_with(payload: object = None, *, status: int = 200, **kwargs: object):
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(AWC_METAR_URL).mock(
            return_value=httpx.Response(status, json=payload, **kwargs)  # type: ignore[arg-type]
        )
        result = await fetch_latest_observation("SAAR")
    return result, route


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

async def test_parses_a_normal_metar():
    result, route = await _fetch_with([_entry()])

    assert result == _observation()
    assert route.call_count == 1
    params = route.calls.last.request.url.params
    assert params["ids"] == "SAAR"
    assert params["format"] == "json"
    assert params["hours"] == "3"


async def test_picks_the_most_recent_entry_by_obs_time():
    older = _entry(obsTime=int((OBS_TIME - timedelta(hours=1)).timestamp()), temp=30)
    result, _ = await _fetch_with([older, _entry()])

    assert result is not None
    assert result.observed_at == OBS_TIME
    assert result.temp_c == 22.0


async def test_variable_wind_has_no_direction():
    result, _ = await _fetch_with([_entry(wdir="VRB", wspd=3)])

    assert result is not None
    assert result.wind_dir_deg is None
    assert result.wind_speed_kmh == pytest.approx(5.6)


async def test_calm_wind_has_no_direction():
    result, _ = await _fetch_with([_entry(wdir=0, wspd=0)])

    assert result is not None
    assert result.wind_dir_deg is None
    assert result.wind_speed_kmh == 0.0


async def test_gust_is_converted_to_kmh():
    result, _ = await _fetch_with([_entry(wspd=15, wgst=25, wxString="-RA BR")])

    assert result is not None
    assert result.wind_speed_kmh == pytest.approx(27.8)
    assert result.wind_gust_kmh == pytest.approx(46.3)
    assert result.wx_string == "-RA BR"


async def test_missing_temperature_is_parsed_as_none():
    result, _ = await _fetch_with([_entry(temp=_MISSING)])

    assert result is not None
    assert result.temp_c is None
    assert result.humidity is None


@pytest.mark.parametrize(
    ("temp_c", "dewpoint_c", "expected"),
    [(22.0, 11.0, 50.0), (20.0, 20.0, 100.0), (10.0, 11.0, 100.0), (30.0, -10.0, 7.0)],
)
def test_relative_humidity_uses_magnus_rounded_and_clamped(temp_c, dewpoint_c, expected):
    assert relative_humidity(temp_c, dewpoint_c) == expected


def test_relative_humidity_is_none_without_both_inputs():
    assert relative_humidity(None, 10.0) is None
    assert relative_humidity(10.0, None) is None


# ---------------------------------------------------------------------------
# Failures never raise and are logged
# ---------------------------------------------------------------------------

async def test_empty_list_returns_none():
    result, _ = await _fetch_with([])
    assert result is None


async def test_http_500_returns_none():
    result, _ = await _fetch_with({"error": "boom"}, status=500)
    assert result is None


async def test_invalid_json_returns_none():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(AWC_METAR_URL).mock(return_value=httpx.Response(200, content=b"<html>nope"))
        result = await fetch_latest_observation("SAAR")
    assert result is None


async def test_entries_without_obs_time_return_none():
    result, _ = await _fetch_with([_entry(obsTime=_MISSING)])
    assert result is None


async def test_timeout_returns_none_and_uses_the_short_timeout(caplog):
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(AWC_METAR_URL).mock(side_effect=httpx.ReadTimeout("slow"))
        result = await fetch_latest_observation("SAAR")

    assert result is None
    assert route.calls.last.request.extensions["timeout"]["read"] == pytest.approx(4.0)
    assert "SAAR" in caplog.text


# ---------------------------------------------------------------------------
# Caches
# ---------------------------------------------------------------------------

async def test_successful_result_is_cached():
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(AWC_METAR_URL).mock(return_value=httpx.Response(200, json=[_entry()]))
        first = await fetch_latest_observation("SAAR")
        second = await fetch_latest_observation("SAAR")

    assert first == second
    assert route.call_count == 1


async def test_failure_is_cached_briefly():
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(AWC_METAR_URL).mock(return_value=httpx.Response(500))
        first = await fetch_latest_observation("SAAR")
        second = await fetch_latest_observation("SAAR")

    assert first is None and second is None
    assert route.call_count == 1


def test_cache_ttls_are_five_minutes_and_one_minute():
    assert metar_entries_cache._cache.ttl == 300
    assert metar_entries_cache._failure_cache.ttl == 60


async def test_records_awc_usage(monkeypatch):
    recorder = MagicMock()
    monkeypatch.setattr(awc.usage_counter, "record", recorder)

    await _fetch_with([_entry()])

    recorder.assert_called_once_with("metar_awc")


# ---------------------------------------------------------------------------
# Selection: 20 km / 90 min
# ---------------------------------------------------------------------------

def test_classify_accepts_exactly_twenty_km_and_ninety_minutes():
    obs = _observation()
    assert classify_observation(20.0, obs, OBS_TIME + timedelta(minutes=90)) == "metar_ok"


def test_classify_rejects_beyond_twenty_km():
    assert classify_observation(20.01, _observation(), NOW) == "metar_too_far"


def test_classify_rejects_what_the_old_thirty_km_limit_accepted():
    assert classify_observation(25.0, _observation(), NOW) == "metar_too_far"


def test_classify_rejects_older_than_ninety_minutes():
    assert classify_observation(10.0, _observation(), OBS_TIME + timedelta(minutes=95)) == "metar_stale"


def test_classify_without_observation_is_unavailable():
    assert classify_observation(10.0, None, NOW) == "metar_unavailable"


@pytest.mark.parametrize("missing", ["temp_c", "dewpoint_c"])
def test_classify_requires_temperature_and_dewpoint(missing):
    obs = _observation(**{missing: None})
    assert classify_observation(10.0, obs, NOW) == "metar_missing_fields"


async def test_nearest_selection_uses_the_close_airport():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(AWC_METAR_URL).mock(return_value=httpx.Response(200, json=[_entry()]))
        selection = await get_nearest_metar_observation(*ROSARIO, now=NOW)

    assert selection.reason == "metar_ok"
    assert selection.icao == "SAAR"
    assert selection.name == "Rosario"
    assert 0 < selection.distance_km <= 20
    assert selection.observation == _observation()


async def test_nearest_selection_does_not_fetch_a_far_airport():
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(AWC_METAR_URL).mock(return_value=httpx.Response(200, json=[_entry()]))
        selection = await get_nearest_metar_observation(*SANTIAGO_DEL_ESTERO, now=NOW)

    assert selection.reason == "metar_too_far"
    assert selection.observation is None
    assert route.call_count == 0


async def test_nearest_selection_does_not_fetch_an_airport_between_20_and_30_km():
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(AWC_METAR_URL).mock(return_value=httpx.Response(200, json=[_entry()]))
        selection = await get_nearest_metar_observation(*QUILMES, now=NOW)

    assert selection.reason == "metar_too_far"
    assert selection.icao == "SABE"
    assert 20.0 < selection.distance_km < 30.0
    assert selection.observation is None
    assert route.call_count == 0


async def test_nearest_selection_flags_a_95_minute_old_metar_as_stale():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(AWC_METAR_URL).mock(return_value=httpx.Response(200, json=[_entry()]))
        selection = await get_nearest_metar_observation(
            *ROSARIO, now=OBS_TIME + timedelta(minutes=95)
        )

    assert selection.reason == "metar_stale"
    assert selection.observation is None


async def test_nearest_selection_without_temperature_is_missing_fields():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(AWC_METAR_URL).mock(
            return_value=httpx.Response(200, json=[_entry(temp=_MISSING)])
        )
        selection = await get_nearest_metar_observation(*ROSARIO, now=NOW)

    assert selection.reason == "metar_missing_fields"


async def test_nearest_selection_with_awc_down_is_unavailable():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(AWC_METAR_URL).mock(return_value=httpx.Response(503))
        selection = await get_nearest_metar_observation(*ROSARIO, now=NOW)

    assert selection.reason == "metar_unavailable"
