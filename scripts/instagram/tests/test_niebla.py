"""Dense fog for the night notice: the rule (reglas) and the hourly visibility source (one call, no retry)."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from report_factories import TARGET, make_visibility

import fuente_visibilidad as vis
from fuente_datos import shared_client
from fuente_visibilidad import (
    VISIBILITY_VARIABLE,
    HourlyVisibility,
    day_visibility,
    fetch_visibility,
    fog_check,
    parse_hourly_visibility,
)
from reglas import FOG_TEXT, FOG_VISIBILITY_M, Fog, dense_fog, format_fog_hours

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
LAT, LON = -34.6037, -58.3816  # Buenos Aires
TARGET_INDEX = 2  # TARGET is the third day of the synthetic series


def hours(values: dict[int, float]) -> tuple[tuple[int, float], ...]:
    """24 clear hours (20 km) with the given overrides."""
    return tuple((hour, values.get(hour, 20000.0)) for hour in range(24))


# ---------------------------------------------------------------------------
# The rule: visibility strictly under 500 m in some hour of the day
# ---------------------------------------------------------------------------


def test_the_threshold_is_500_m_and_the_text_says_possible() -> None:
    assert FOG_VISIBILITY_M == 500.0
    assert FOG_TEXT == "Niebla densa posible"


def test_exactly_500_m_is_not_dense_fog() -> None:
    assert dense_fog(hours({5: 500.0})) is None


def test_499_m_is_dense_fog() -> None:
    assert dense_fog(hours({5: 499.0})) == Fog(first_hour=5, last_hour=5, min_visibility_m=499)


def test_the_range_goes_from_the_first_to_the_last_foggy_hour_with_the_minimum() -> None:
    fog = dense_fog(hours({4: 450.0, 5: 120.0, 6: 300.0, 7: 900.0, 9: 480.0}))
    assert fog == Fog(first_hour=4, last_hour=9, min_visibility_m=120)
    assert format_fog_hours(fog) == "04:00 a 09:00 hs"


def test_a_single_foggy_hour_is_written_as_one_time() -> None:
    assert format_fog_hours(Fog(first_hour=23, last_hour=23, min_visibility_m=80)) == "23:00 hs"


def test_the_minimum_is_rounded_half_up_to_whole_metres() -> None:
    fog = dense_fog(hours({3: 160.5}))
    assert fog is not None and fog.min_visibility_m == 161


def test_a_clear_day_has_no_fog() -> None:
    assert dense_fog(hours({})) is None
    assert dense_fog(()) is None


# ---------------------------------------------------------------------------
# Parsing the Open-Meteo answer
# ---------------------------------------------------------------------------


def test_parses_the_hourly_visibility_of_the_answer() -> None:
    payload = {
        "hourly_units": {"time": "iso8601", "visibility": "m"},
        "hourly": {"time": ["2026-10-07T00:00", "2026-10-07T01:00"], "visibility": [42480.0, 160.0]},
    }
    assert parse_hourly_visibility(payload) == HourlyVisibility(
        times=("2026-10-07T00:00", "2026-10-07T01:00"), visibility_m=(42480.0, 160.0)
    )


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"hourly": {}},
        {"hourly": {"time": ["2026-10-07T00:00"]}},
        {"hourly": {"time": ["2026-10-07T00:00", "2026-10-07T01:00"], "visibility": [1.0]}},
        {"hourly": {"time": [], "visibility": []}},
    ],
)
def test_a_malformed_answer_is_no_data(payload: object) -> None:
    assert parse_hourly_visibility(payload) is None


# ---------------------------------------------------------------------------
# The 24 hours of the forecast day (local time)
# ---------------------------------------------------------------------------


def test_the_day_is_00_00_to_23_00_of_the_target_date() -> None:
    series = make_visibility(values={(TARGET_INDEX, 0): 300.0, (TARGET_INDEX, 23): 400.0, (TARGET_INDEX + 1, 0): 1.0})
    day = day_visibility(series, TARGET)
    assert day is not None and len(day) == 24
    assert day[0] == (0, 300.0)
    assert day[23] == (23, 400.0)


def test_a_missing_hour_makes_the_day_unusable() -> None:
    series = make_visibility(values={(TARGET_INDEX, 6): None})
    assert day_visibility(series, TARGET) is None


def test_a_series_that_does_not_reach_the_day_is_unusable() -> None:
    series = make_visibility(days=1)
    assert day_visibility(series, TARGET) is None


# ---------------------------------------------------------------------------
# Fog check of one city: fog, or no fog with the reason in the avisos
# ---------------------------------------------------------------------------


def test_fog_check_finds_the_fog_without_warnings() -> None:
    series = make_visibility(values={(TARGET_INDEX, h): 200.0 for h in range(4, 10)})
    check = fog_check(series, TARGET, city_name="Buenos Aires")
    assert check.fog == Fog(first_hour=4, last_hour=9, min_visibility_m=200)
    assert check.aviso is None


def test_without_visibility_the_fog_is_not_evaluated_and_it_is_warned() -> None:
    check = fog_check(None, TARGET, city_name="Buenos Aires")
    assert check.fog is None
    assert check.aviso is not None and "Buenos Aires" in check.aviso and "niebla" in check.aviso


def test_with_missing_hours_the_fog_is_not_evaluated_even_if_other_hours_are_foggy() -> None:
    values = {(TARGET_INDEX, 5): 100.0, (TARGET_INDEX, 6): None}
    check = fog_check(make_visibility(values=values), TARGET, city_name="Resistencia")
    assert check.fog is None
    assert check.aviso is not None and "incompleta" in check.aviso and TARGET.isoformat() in check.aviso


# ---------------------------------------------------------------------------
# Live fetch (respx: never the real network)
# ---------------------------------------------------------------------------


def _answer(series: HourlyVisibility) -> dict[str, object]:
    return {
        "hourly_units": {"time": "iso8601", "visibility": "m"},
        "hourly": {"time": list(series.times), "visibility": list(series.visibility_m)},
    }


async def _fetch_once() -> HourlyVisibility | None:
    async with shared_client():
        return await fetch_visibility(LAT, LON)


def test_fetch_makes_one_visibility_request_in_local_time_and_parses_it() -> None:
    expected = make_visibility(values={(TARGET_INDEX, 5): 150.0})
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get(OPEN_METEO).mock(return_value=httpx.Response(200, json=_answer(expected)))
        series = asyncio.run(_fetch_once())
    assert series == expected
    assert route.call_count == 1
    params = parse_qs(str(route.calls.last.request.url.query, "ascii"))
    assert params["hourly"] == [VISIBILITY_VARIABLE] == ["visibility"]
    assert params["timezone"] == ["America/Argentina/Buenos_Aires"]
    assert float(params["latitude"][0]) == LAT and float(params["longitude"][0]) == LON
    assert "models" not in params  # the default model of Open-Meteo, like the web's hourly series


@pytest.mark.parametrize(
    "failure",
    [
        httpx.Response(500),
        httpx.Response(429),
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
    assert route.call_count == 1  # never retried


def test_fetch_uses_the_backend_timeout_and_one_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[object] = []

    async def fake_fetch_with_retry(client: object, method: str, url: str, **kwargs: object) -> object:
        seen.extend([kwargs.get("timeout"), kwargs.get("max_attempts")])
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(vis, "fetch_with_retry", fake_fetch_with_retry)
    assert asyncio.run(_fetch_once()) is None
    from app.core.config import settings

    assert seen == [settings.http_timeout_seconds, 1]


def test_make_visibility_covers_whole_days() -> None:
    series = make_visibility(days=2)
    assert len(series.times) == 48
    assert series.times[0] == f"{(TARGET - timedelta(days=TARGET_INDEX)).isoformat()}T00:00"
