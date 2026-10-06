"""ECMWF hourly rain: the mm of each 3 h slot come from the same model as the daily total."""

from __future__ import annotations

import asyncio
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from report_factories import FIRST_DAY, TARGET, make_ecmwf_rain

import fuente_horaria_ecmwf as ecmwf
from fuente_datos import shared_client
from fuente_horaria_ecmwf import (
    COHERENCE_FRACTION,
    COHERENCE_MIN_MM,
    ECMWF_HOURLY_MODEL,
    EcmwfHourlyRain,
    coherence_tolerance,
    day_hours,
    ecmwf_slot_rain,
    fetch_ecmwf_hourly_rain,
    is_coherent,
    parse_hourly_rain,
    slot_totals,
)

TARGET_INDEX = 2  # TARGET is the third day of the synthetic series
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
LAT, LON = -27.46, -58.9867  # Resistencia


def slot_rain(rain=None, *, daily_total=1.8, anchor_is_ecmwf=True):
    return ecmwf_slot_rain(
        rain, TARGET, daily_total=daily_total, anchor_is_ecmwf=anchor_is_ecmwf, city_name="Resistencia"
    )


# ---------------------------------------------------------------------------
# Parsing the Open-Meteo answer
# ---------------------------------------------------------------------------


def test_parses_the_hourly_precipitation_of_the_answer() -> None:
    payload = {
        "hourly_units": {"time": "iso8601", "precipitation": "mm"},
        "hourly": {"time": ["2026-10-07T00:00", "2026-10-07T01:00"], "precipitation": [0.0, 1.25]},
    }
    rain = parse_hourly_rain(payload)
    assert rain == EcmwfHourlyRain(times=("2026-10-07T00:00", "2026-10-07T01:00"), precip_mm=(0.0, 1.25))


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"hourly": {}},
        {"hourly": {"time": ["2026-10-07T00:00"]}},  # no precipitation
        {"hourly": {"time": ["2026-10-07T00:00", "2026-10-07T01:00"], "precipitation": [0.0]}},  # lengths differ
        {"hourly": {"time": [], "precipitation": []}},
    ],
)
def test_a_malformed_answer_is_no_data(payload: object) -> None:
    assert parse_hourly_rain(payload) is None


def test_null_or_non_numeric_hours_are_kept_as_missing() -> None:
    payload = {"hourly": {"time": ["2026-10-07T00:00", "2026-10-07T01:00"], "precipitation": [None, "x"]}}
    rain = parse_hourly_rain(payload)
    assert rain is not None and rain.precip_mm == (None, None)


# ---------------------------------------------------------------------------
# The 24 hours of the day and its 3 h slots
# ---------------------------------------------------------------------------


def test_the_day_is_the_24_hours_that_end_at_01_00_through_the_next_midnight() -> None:
    rain = make_ecmwf_rain(
        rain={
            (TARGET_INDEX, 0): 9.0,  # 23:00-24:00 of the day before: not this day
            (TARGET_INDEX, 1): 1.0,  # 00:00-01:00
            (TARGET_INDEX + 1, 0): 2.0,  # 23:00-24:00 of the target day
        }
    )
    hours = day_hours(rain, TARGET)
    assert hours is not None and len(hours) == 24
    assert hours[0] == 1.0
    assert hours[23] == 2.0
    assert sum(hours) == 3.0


def test_a_missing_hour_makes_the_day_unusable() -> None:
    assert day_hours(make_ecmwf_rain(rain={(TARGET_INDEX, 14): None}), TARGET) is None


def test_a_day_outside_the_series_is_unusable() -> None:
    assert day_hours(make_ecmwf_rain(days=2, first_day=FIRST_DAY), TARGET) is None


def test_slot_totals_add_the_three_hours_of_each_slot() -> None:
    hours = [0.0] * 24
    hours[6], hours[7], hours[8] = 1.0, 2.0, 0.5  # 06:00-09:00
    hours[21], hours[22], hours[23] = 0.1, 0.1, 0.1  # 21:00-24:00
    totals = dict(slot_totals(hours))
    assert sorted(totals) == list(range(0, 24, 3))
    assert totals[6] == 3.5
    assert totals[21] == 0.3
    assert totals[0] == 0.0


# ---------------------------------------------------------------------------
# Coherence of the hourly sum with the daily total
# ---------------------------------------------------------------------------


def test_tolerance_is_half_a_millimetre_or_a_quarter_of_the_total_whichever_is_greater() -> None:
    assert (COHERENCE_MIN_MM, COHERENCE_FRACTION) == (0.5, 0.25)
    assert coherence_tolerance(0.0) == 0.5
    assert coherence_tolerance(1.8) == 0.5
    assert coherence_tolerance(2.0) == 0.5  # both rules give 0.5
    assert coherence_tolerance(10.0) == 2.5
    assert coherence_tolerance(49.9) == pytest.approx(12.475)


@pytest.mark.parametrize(
    ("hourly", "daily", "expected"),
    [
        (2.3, 1.8, True),  # exactly 0.5 mm apart: inside (borde)
        (2.31, 1.8, False),
        (0.5, 0.0, True),
        (0.6, 0.0, False),
        (12.5, 10.0, True),  # exactly 25 %: inside (borde)
        (12.6, 10.0, False),
        (7.4, 10.0, False),
        (50.7, 49.9, True),  # CABA 7/10, real numbers
        (25.2, 1.8, False),  # Resistencia 7/10, real numbers
    ],
)
def test_coherence_inside_and_outside_the_tolerance(hourly: float, daily: float, expected: bool) -> None:
    assert is_coherent(hourly, daily) is expected


def test_coherent_hourly_rain_gives_the_slot_millimetres() -> None:
    # 1.8 mm in the day: 0.6 (12-15), 0.9 (15-18), 0.3 (18-21).
    rain = make_ecmwf_rain(
        rain={
            **{(TARGET_INDEX, h): 0.2 for h in (13, 14, 15)},
            **{(TARGET_INDEX, h): 0.3 for h in (16, 17, 18)},
            **{(TARGET_INDEX, h): 0.1 for h in (19, 20, 21)},
        }
    )
    result = slot_rain(rain)
    assert result.aviso is None
    assert result.bound_mm is None  # coherent: the daily total is shown as it is
    assert result.hourly_total == pytest.approx(1.8)
    assert result.by_start is not None
    by_start = dict(result.by_start)
    assert by_start[12] == pytest.approx(0.6)
    assert by_start[15] == pytest.approx(0.9)
    assert by_start[21] == 0.0


# The real Resistencia 7/10 answer: 1.8 mm in the day but 1.5 mm in the afternoon and 23.7 mm in 21-24.
RESISTENCIA_7_10 = {
    **{(TARGET_INDEX, h): 0.25 for h in range(13, 19)},
    (TARGET_INDEX, 22): 7.9,
    (TARGET_INDEX, 23): 7.9,
    (TARGET_INDEX + 1, 0): 7.9,
}


def test_incoherent_with_a_bigger_hourly_sum_shows_the_hourly_bound_and_its_window() -> None:
    result = slot_rain(make_ecmwf_rain(rain=RESISTENCIA_7_10), daily_total=1.8)
    assert result.hourly_total == pytest.approx(25.2)
    assert result.bound_mm == pytest.approx(25.2)  # the greater of 1.8 and 25.2
    assert result.by_start is not None
    assert dict(result.by_start)[21] == pytest.approx(23.7)
    assert result.aviso is not None
    assert "Resistencia" in result.aviso
    assert "25,2" in result.aviso and "1,8" in result.aviso
    assert "usando la cota horaria" in result.aviso


def test_incoherent_with_a_bigger_daily_total_shows_the_daily_bound_and_the_hourly_window() -> None:
    # 20 mm in the day, 3 mm in the hours: the hours still rain (> 0.9 mm), so they place the window.
    rain = make_ecmwf_rain(rain={(TARGET_INDEX, 8): 2.0, (TARGET_INDEX, 9): 1.0})
    result = slot_rain(rain, daily_total=20.0)
    assert result.bound_mm == 20.0
    assert result.by_start is not None
    # Hours 08 and 09 both end inside the 06-09 slot, so its rain is 2.0 + 1.0.
    assert dict(result.by_start)[6] == 3.0
    assert result.aviso is not None and "usando la cota diaria" in result.aviso


def test_incoherent_with_a_bigger_daily_total_and_almost_dry_hours_has_no_window() -> None:
    # 20 mm in the day but only 0.9 mm in the hours: a "dry" hourly series cannot place the rain.
    rain = make_ecmwf_rain(rain={(TARGET_INDEX, h): 0.3 for h in (8, 9, 10)})
    result = slot_rain(rain, daily_total=20.0)
    assert result.bound_mm == 20.0
    assert result.by_start is None
    assert result.aviso is not None
    assert "usando la cota diaria" in result.aviso and "sin franja" in result.aviso


@pytest.mark.parametrize(
    ("hourly_mm", "bound"),
    [
        (2.3, None),  # exactly 0.5 mm over 1.8: still coherent, no bound
        (2.4, 2.4),  # beyond the tolerance: the hourly sum is the bound
    ],
)
def test_bound_only_beyond_the_tolerance(hourly_mm: float, bound: float | None) -> None:
    rain = make_ecmwf_rain(rain={(TARGET_INDEX, 14): hourly_mm})
    result = slot_rain(rain, daily_total=1.8)
    assert result.bound_mm == bound
    assert result.by_start is not None
    assert (result.aviso is None) is (bound is None)


def test_without_ecmwf_hourly_rain_there_are_no_slots_and_it_is_warned() -> None:
    result = slot_rain(None)
    assert result.by_start is None
    assert result.bound_mm is None  # never a bound without ECMWF hours
    assert result.hourly_total is None
    assert result.aviso is not None and "Resistencia" in result.aviso


def test_an_incomplete_day_gives_no_slots_and_it_is_warned() -> None:
    result = slot_rain(make_ecmwf_rain(rain={(TARGET_INDEX, 10): None}))
    assert result.by_start is None
    assert result.aviso is not None and "incompleta" in result.aviso


def test_when_the_total_is_not_ecmwf_the_ecmwf_slots_are_not_used() -> None:
    result = slot_rain(make_ecmwf_rain(rain=RESISTENCIA_7_10), daily_total=0.0, anchor_is_ecmwf=False)
    assert result.by_start is None
    assert result.bound_mm is None
    assert result.aviso is not None


def test_unknown_daily_total_gives_no_slots_and_no_warning() -> None:
    # Without a total the plate says nothing about rain, so there is nothing to warn about.
    result = slot_rain(make_ecmwf_rain(), daily_total=None)
    assert result.by_start is None
    assert result.aviso is None


# ---------------------------------------------------------------------------
# Live fetch (mocked with respx: never the real network)
# ---------------------------------------------------------------------------


def _answer(rain: EcmwfHourlyRain) -> dict[str, object]:
    return {
        "hourly_units": {"time": "iso8601", "precipitation": "mm"},
        "hourly": {"time": list(rain.times), "precipitation": list(rain.precip_mm)},
    }


async def _fetch_once(**kwargs: object) -> EcmwfHourlyRain | None:
    async with shared_client():
        return await fetch_ecmwf_hourly_rain(LAT, LON, **kwargs)


def test_fetch_makes_one_ecmwf_hourly_request_and_parses_it() -> None:
    expected = make_ecmwf_rain(rain={(TARGET_INDEX, 15): 1.5})
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get(OPEN_METEO).mock(return_value=httpx.Response(200, json=_answer(expected)))
        rain = asyncio.run(_fetch_once())
    assert rain == expected
    assert route.call_count == 1
    params = parse_qs(str(route.calls.last.request.url.query, "ascii"))
    assert params["models"] == [ECMWF_HOURLY_MODEL] == ["ecmwf_ifs025"]
    assert params["hourly"] == ["precipitation"]
    assert params["timezone"] == ["America/Argentina/Buenos_Aires"]
    assert params["forecast_days"] == ["7"]
    assert float(params["latitude"][0]) == LAT and float(params["longitude"][0]) == LON


@pytest.mark.parametrize(
    "failure",
    [
        httpx.Response(500),
        httpx.Response(429),
        httpx.Response(400),
        httpx.ConnectTimeout("slow"),
        httpx.Response(200, json={"error": True}),
    ],
)
def test_a_failed_fetch_is_no_data_after_a_single_attempt(failure: object) -> None:
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get(OPEN_METEO)
        if isinstance(failure, Exception):
            route.mock(side_effect=failure)
        else:
            route.mock(return_value=failure)
        assert asyncio.run(_fetch_once()) is None
    assert route.call_count == 1  # never retried: one extra call per city and run


def test_fetch_uses_the_backend_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[object] = []

    async def fake_fetch_with_retry(client: object, method: str, url: str, **kwargs: object) -> object:
        seen.append(kwargs.get("timeout"))
        seen.append(kwargs.get("max_attempts"))
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(ecmwf, "fetch_with_retry", fake_fetch_with_retry)
    assert asyncio.run(_fetch_once()) is None
    from app.core.config import settings

    assert seen == [settings.http_timeout_seconds, 1]
