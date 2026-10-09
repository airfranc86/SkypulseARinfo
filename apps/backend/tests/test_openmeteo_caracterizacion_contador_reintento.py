"""Characterization (phase 2a): usage counter and retry policy of every Open-Meteo request.

Pins, per function: how many times `usage_counter.record("open_meteo")` runs for one logical call, how many HTTP
requests a 5xx and a 429 cost, and, for the multi-model call only, that nothing goes out (or counts) while the 429
pause is open (the other functions are covered in `test_openmeteo_429_pause.py`). Production code is not touched:
every assertion here passes against the current code.
"""
from __future__ import annotations

from datetime import datetime

import httpx
import pytest
import respx

import app.services.openmeteo as om_module
from app.core import usage_counter
from app.core.rate_limit_pause import openmeteo_pause as pause
from app.services.openmeteo import (
    get_current,
    get_daily_forecast_ext,
    get_fog_inference_forecast,
    get_hourly_forecast_ecmwf,
    get_hourly_forecast_ext,
    get_multi_model_daily,
    get_visibility_forecast,
)
from tests._om_payloads import (
    _CURRENT_PAYLOAD,
    _DAILY_EXT_PAYLOAD,
    _FOG_PAYLOAD,
    _VISIBILITY_PAYLOAD,
    OM_URL,
)

LAT, LON = -31.4, -64.2


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """The retry of `fetch_with_retry` does not really wait."""
    monkeypatch.setattr("app.core.http_client._backoff_delay", lambda attempt: 0.0)


@pytest.fixture(autouse=True)
def fixed_argentine_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """The niebla payloads are dated 2024-01-15: with the real clock the fog reader would have no hours to show."""
    monkeypatch.setattr(om_module, "_ar_now", lambda: datetime(2024, 1, 15, 12, 30, tzinfo=om_module._AR_TZ))


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record each `usage_counter.record` instead of sending it to Upstash."""
    calls: list[str] = []
    monkeypatch.setattr(usage_counter, "record", calls.append)
    return calls


@pytest.fixture
def om():
    with respx.mock(assert_all_called=False) as router:
        yield router.get(OM_URL)


_HOURLY_PAYLOAD = {
    "elevation": 25.0,
    "hourly": {"time": [f"2026-10-08T{h:02d}:00" for h in range(24)], "temperature_2m": [20.0] * 24},
}

# name -> (call, payload that parses, HTTP requests one successful logical call makes)
_CALLS = {
    "current": (lambda: get_current(LAT, LON), _CURRENT_PAYLOAD, 1),
    "daily": (lambda: get_daily_forecast_ext(LAT, LON), _DAILY_EXT_PAYLOAD, 1),
    "multi_model": (lambda: get_multi_model_daily(LAT, LON), _DAILY_EXT_PAYLOAD, 2),
    "hourly": (lambda: get_hourly_forecast_ext(LAT, LON), _HOURLY_PAYLOAD, 1),
    "hourly_ecmwf": (lambda: get_hourly_forecast_ecmwf(LAT, LON), _HOURLY_PAYLOAD, 1),
    "visibility": (lambda: get_visibility_forecast(LAT, LON), _VISIBILITY_PAYLOAD, 1),
    "fog": (lambda: get_fog_inference_forecast(LAT, LON), _FOG_PAYLOAD, 1),
}
# 429 is not asked of the multi-model call: its two concurrent requests race against the pause the first 429 opens.
_SINGLE_REQUEST = [name for name, (_c, _p, requests) in _CALLS.items() if requests == 1]


# ---------------------------------------------------------------------------
# Counter: once per request that goes out, before the HTTP call
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", list(_CALLS))
async def test_one_successful_call_records_once_per_request_it_sends(name, om, counted) -> None:
    call, payload, requests = _CALLS[name]
    om.mock(return_value=httpx.Response(200, json=payload))
    assert await call() is not None
    assert om.call_count == requests
    assert counted == ["open_meteo"] * requests


@pytest.mark.parametrize("name", list(_CALLS))
async def test_a_cache_hit_records_nothing(name, om, counted) -> None:
    call, payload, requests = _CALLS[name]
    om.mock(return_value=httpx.Response(200, json=payload))
    await call()
    await call()
    assert om.call_count == requests
    assert counted == ["open_meteo"] * requests


@pytest.mark.parametrize("name", list(_CALLS))
async def test_a_retried_5xx_counts_once_per_request_not_once_per_attempt(name, om, counted) -> None:
    call, _payload, requests = _CALLS[name]
    om.mock(return_value=httpx.Response(503))
    assert await call() is None
    assert om.call_count == 2 * requests          # each request is tried twice
    assert counted == ["open_meteo"] * requests   # and counted once


@pytest.mark.parametrize("name", list(_CALLS))
async def test_a_5xx_followed_by_success_costs_two_attempts_and_one_count_per_request(name, om, counted) -> None:
    """Every request fails once and then succeeds: two attempts per request (the multi-model call sends two requests)."""
    call, payload, requests = _CALLS[name]
    attempts: dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        key = request.url.params.get("models", "")
        attempts[key] = attempts.get(key, 0) + 1
        return httpx.Response(503) if attempts[key] == 1 else httpx.Response(200, json=payload)

    om.mock(side_effect=handler)
    assert await call() is not None
    assert om.call_count == 2 * requests
    assert counted == ["open_meteo"] * requests


# ---------------------------------------------------------------------------
# Retry: a 429 is never retried, a 5xx is retried once
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", _SINGLE_REQUEST)
async def test_a_429_costs_one_http_request_and_one_count(name, om, counted) -> None:
    call, _payload, _requests = _CALLS[name]
    om.mock(return_value=httpx.Response(429, json={"error": True}))
    assert await call() is None
    assert om.call_count == 1
    assert counted == ["open_meteo"]


@pytest.mark.parametrize("name", _SINGLE_REQUEST)
async def test_a_5xx_costs_exactly_two_http_requests(name, om, counted) -> None:
    call, _payload, _requests = _CALLS[name]
    om.mock(return_value=httpx.Response(500))
    assert await call() is None
    assert om.call_count == 2


@pytest.mark.parametrize("name", _SINGLE_REQUEST)
async def test_a_transport_error_is_retried_once_too(name, om, counted) -> None:
    call, _payload, _requests = _CALLS[name]
    om.mock(side_effect=httpx.ConnectError("no network"))
    assert await call() is None
    assert om.call_count == 2
    assert counted == ["open_meteo"]


# ---------------------------------------------------------------------------
# While the 429 pause is open: no request, no count
# ---------------------------------------------------------------------------

async def test_multi_model_sends_nothing_and_counts_nothing_while_the_pause_is_open(om, counted) -> None:
    om.mock(return_value=httpx.Response(200, json=_DAILY_EXT_PAYLOAD))
    pause.trip()
    assert await get_multi_model_daily(LAT, LON) is None
    assert om.call_count == 0
    assert counted == []
