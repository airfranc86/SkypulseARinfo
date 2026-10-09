"""The Open-Meteo budget end to end: real ASGI app, real middleware, real services, respx for Open-Meteo.

The dashboard asks Open-Meteo for the two daily models and the hourly series of every NEW cell (3 calls
here; the observation, the METAR and the ECMWF hourly series are doubles, as in test_dashboard_integration).
The client is told apart by `CF-Connecting-IP`, exactly as the per-IP rate limiter does.

E1 - One client sweeping distinct cells stops reaching Open-Meteo after its share; a second client is unaffected.
E2 - Rotating `X-Forwarded-For` does not buy a new share.
E3 - The global cap holds across clients, and a refusal is the same 503 the dashboard already answers.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from httpx import AsyncClient

from app.core import usage_counter
from app.core.config import settings
from app.core.rate_limit_pause import openmeteo_pause as pause
from app.services.openmeteo_budget import budget_refusals
from tests.test_dashboard import _make_current_response
from tests.test_openmeteo_cache import OM_URL

pytestmark = pytest.mark.usefixtures("frozen_ar_today", "fresh_rate_limit")

ALICE = {"CF-Connecting-IP": "198.51.100.10"}
BOB = {"CF-Connecting-IP": "198.51.100.20"}
CAROL = {"CF-Connecting-IP": "198.51.100.30"}
CALLS_PER_NEW_CELL = 3  # daily GFS + daily ECMWF + hourly best_match


def _daily_payload() -> dict:
    n = 7
    return {
        "daily": {
            "time": [f"2026-05-{20 + i:02d}" for i in range(n)],
            "temperature_2m_max": [24.0] * n,
            "temperature_2m_min": [12.0] * n,
            "precipitation_sum": [0.0] * n,
            "precipitation_probability_max": [10] * n,
            "wind_speed_10m_max": [20.0] * n,
            "wind_gusts_10m_max": [30.0] * n,
            "wind_direction_10m_dominant": [270.0] * n,
            "relative_humidity_2m_mean": [55.0] * n,
            "uv_index_max": [6.0] * n,
            "weather_code": [0] * n,
            "sunrise": [f"2026-05-{20 + i:02d}T07:30" for i in range(n)],
            "sunset": [f"2026-05-{20 + i:02d}T18:00" for i in range(n)],
            "daylight_duration": [37800.0] * n,
            "cloud_cover_mean": [30.0] * n,
        }
    }


def _hourly_payload() -> dict:
    n = 48
    return {
        "elevation": 430.0,
        "hourly": {
            "time": [f"2026-05-{20 + h // 24:02d}T{h % 24:02d}:00" for h in range(n)],
            "temperature_2m": [20.0] * n,
            "precipitation": [0.0] * n,
            "precipitation_probability": [10] * n,
            "wind_speed_10m": [15.0] * n,
            "weather_code": [0] * n,
            "is_day": [1] * n,
        },
    }


def _upstream(request: httpx.Request) -> httpx.Response:
    payload = _daily_payload() if "daily" in request.url.params else _hourly_payload()
    return httpx.Response(200, json=payload)


@pytest.fixture
def om():
    with respx.mock(assert_all_called=False) as router:
        yield router.get(OM_URL).mock(side_effect=_upstream)


@pytest.fixture(autouse=True)
def other_sources(monkeypatch: pytest.MonkeyPatch):
    """The observation is a double and the call counter does not go to Upstash."""
    monkeypatch.setattr(
        "app.routers.weather.aggregate_current",
        AsyncMock(return_value=_make_current_response()),
    )
    monkeypatch.setattr(usage_counter, "record", lambda provider: None)


async def _dashboard(client: AsyncClient, headers: dict[str, str], cell: int) -> httpx.Response:
    lat = -25.0 - cell * 0.5
    return await client.get(f"/api/weather/dashboard?lat={lat}&lon=-64.2", headers=headers)


async def test_e1_a_client_sweeping_cells_stops_reaching_open_meteo_after_its_share(
    async_client: AsyncClient, om
):
    statuses = [(await _dashboard(async_client, ALICE, cell)).status_code for cell in range(8)]

    assert statuses == [200] * 4 + [503] * 4  # 12 calls = 4 new cells; the rest is refused
    assert om.call_count == 4 * CALLS_PER_NEW_CELL
    assert budget_refusals()["client"] == 4 * CALLS_PER_NEW_CELL
    assert budget_refusals()["global"] == 0

    refused = await _dashboard(async_client, ALICE, 5)
    assert refused.json()["detail"] == "forecast_unavailable"  # the answer the dashboard already gave
    assert (await _dashboard(async_client, ALICE, 0)).status_code == 200  # a cached cell needs no token
    assert om.call_count == 4 * CALLS_PER_NEW_CELL

    neighbour = await _dashboard(async_client, BOB, 20)  # another client, another share
    assert neighbour.status_code == 200
    assert om.call_count == 5 * CALLS_PER_NEW_CELL
    assert pause.remaining() == 0.0 and pause.allow_request() is True  # the sweep provoked no 429


async def test_e2_rotating_x_forwarded_for_does_not_buy_a_new_share(async_client: AsyncClient, om):
    statuses = []
    for cell in range(6):
        headers = {**ALICE, "X-Forwarded-For": f"203.0.113.{cell + 1}, 203.0.113.99, 203.0.113.98"}
        statuses.append((await _dashboard(async_client, headers, cell)).status_code)

    assert statuses == [200] * 4 + [503] * 2
    assert om.call_count == 4 * CALLS_PER_NEW_CELL


async def test_e3_the_global_cap_holds_across_clients(async_client: AsyncClient, om, monkeypatch):
    monkeypatch.setattr(settings, "openmeteo_calls_per_minute", 2 * CALLS_PER_NEW_CELL)

    first = await _dashboard(async_client, ALICE, 0)
    second = await _dashboard(async_client, BOB, 1)
    third = await _dashboard(async_client, CAROL, 2)

    assert (first.status_code, second.status_code, third.status_code) == (200, 200, 503)
    assert om.call_count == 2 * CALLS_PER_NEW_CELL
    assert budget_refusals() == {"client": 0, "global": CALLS_PER_NEW_CELL}
    assert (await _dashboard(async_client, ALICE, 0)).status_code == 200  # what is cached is still served
