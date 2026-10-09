"""Pausa ante el 429 de Open-Meteo: el módulo corta la red hasta que pase la ventana.

Render comparte IP y Open-Meteo responde 429 a todas las llamadas: reintentar solo suma al límite
y al contador `open_meteo`. Durante la pausa los fetch devuelven None sin salir a la red, para que
las cachés sirvan el último dato bueno.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

import app.services.openmeteo as om_module
from app.core import rate_limit_pause
from app.core.cache import CacheOutcome
from app.services.openmeteo import (
    get_current,
    get_daily_forecast_ext,
    get_fog_inference_forecast,
    get_hourly_forecast_ecmwf,
    get_hourly_forecast_ext,
    get_visibility_forecast,
)
from tests.test_openmeteo_cache import (
    _CURRENT_PAYLOAD,
    _DAILY_EXT_PAYLOAD,
    _FOG_PAYLOAD,
    _VISIBILITY_PAYLOAD,
    OM_URL,
)

pause = rate_limit_pause.openmeteo_pause


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """El reintento de `fetch_with_retry` no espera de verdad (el reinicio de la pausa es de conftest)."""
    monkeypatch.setattr("app.core.http_client._backoff_delay", lambda attempt: 0.0)


@pytest.fixture
def clock() -> FakeClock:
    fake = FakeClock()
    pause.clock = fake
    return fake


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Registra cada `usage_counter.record` en vez de mandarlo a Upstash."""
    calls: list[str] = []
    monkeypatch.setattr(om_module.usage_counter, "record", calls.append)
    return calls


@pytest.fixture
def om():
    with respx.mock(assert_all_called=False) as router:
        yield router.get(OM_URL)


def _hourly_payload() -> dict:
    times = [f"2026-10-08T{h:02d}:00" for h in range(24)]
    return {"elevation": 25.0, "hourly": {"time": times, "temperature_2m": [20.0] * 24}}


_CALLS = {
    "current": (lambda: get_current(-31.4, -64.2), _CURRENT_PAYLOAD),
    "daily": (lambda: get_daily_forecast_ext(-31.4, -64.2), _DAILY_EXT_PAYLOAD),
    "hourly": (lambda: get_hourly_forecast_ext(-31.4, -64.2), _hourly_payload()),
    "hourly_ecmwf": (lambda: get_hourly_forecast_ecmwf(-31.4, -64.2), _hourly_payload()),
    "visibility": (lambda: get_visibility_forecast(-31.4, -64.2), _VISIBILITY_PAYLOAD),
    "fog": (lambda: get_fog_inference_forecast(-31.4, -64.2), _FOG_PAYLOAD),
}


def _too_many(headers: dict | None = None) -> httpx.Response:
    return httpx.Response(429, json={"error": True}, headers=headers or {})


async def test_a_429_starts_the_default_pause(om, counted, clock) -> None:
    om.mock(return_value=_too_many())
    assert await get_current(-31.4, -64.2) is None
    assert pause.remaining() == pytest.approx(120.0)


async def test_no_network_call_and_no_counter_increment_during_the_pause(om, counted, clock) -> None:
    om.mock(return_value=_too_many())
    await get_current(-31.4, -64.2)
    calls_before, records_before = om.call_count, len(counted)
    assert records_before == 1

    clock.advance(60.0)
    assert await get_daily_forecast_ext(-31.4, -64.2) is None
    assert await get_current(-34.6, -58.4) is None
    assert await get_visibility_forecast(-34.6, -58.4) is None

    assert om.call_count == calls_before
    assert len(counted) == records_before


@pytest.mark.parametrize("name", list(_CALLS))
async def test_every_fetch_consults_the_pause_before_the_network(name, om, counted, clock) -> None:
    call, payload = _CALLS[name]
    om.mock(return_value=httpx.Response(200, json=payload))
    pause.trip()
    assert await call() is None
    assert om.call_count == 0
    assert counted == []


@pytest.mark.parametrize("name", list(_CALLS))
async def test_every_fetch_arms_the_pause_on_a_429(name, om, counted, clock) -> None:
    call, _payload = _CALLS[name]
    om.mock(return_value=_too_many())
    assert await call() is None
    assert pause.remaining() == pytest.approx(120.0)


async def test_after_the_pause_one_probe_goes_out_and_success_reopens_traffic(om, counted, clock) -> None:
    om.mock(return_value=_too_many())
    await get_current(-31.4, -64.2)
    clock.advance(120.0)

    om.mock(return_value=httpx.Response(200, json=_CURRENT_PAYLOAD))
    calls_before = om.call_count
    assert await get_current(-34.6, -58.4) is not None            # la prueba
    assert om.call_count == calls_before + 1
    assert pause.remaining() == 0.0

    assert await get_current(-30.0, -60.0) is not None             # el tráfico volvió
    assert om.call_count == calls_before + 2


async def test_a_failed_probe_pauses_again(om, counted, clock) -> None:
    om.mock(return_value=_too_many())
    await get_current(-31.4, -64.2)
    clock.advance(120.0)
    calls_before = om.call_count

    assert await get_current(-34.6, -58.4) is None                 # la prueba vuelve con 429
    assert om.call_count > calls_before
    calls_after_probe = om.call_count
    assert pause.remaining() == pytest.approx(120.0)

    assert await get_current(-30.0, -60.0) is None                 # y de nuevo no sale a la red
    assert om.call_count == calls_after_probe


async def test_only_one_probe_goes_out_among_concurrent_requests(om, counted, clock) -> None:
    pause.trip()
    clock.advance(120.0)

    async def slow(request):
        await asyncio.sleep(0.05)
        return httpx.Response(200, json=_CURRENT_PAYLOAD)

    om.mock(side_effect=slow)
    results = await asyncio.gather(*[get_current(-31.0 - i, -64.0) for i in range(4)])
    assert om.call_count == 1
    assert sum(r is not None for r in results) == 1


async def test_retry_after_sets_the_pause_length(om, counted, clock) -> None:
    om.mock(return_value=_too_many({"Retry-After": "45"}))
    await get_current(-31.4, -64.2)
    assert pause.remaining() == pytest.approx(45.0)
    clock.advance(44.0)
    assert await get_daily_forecast_ext(-31.4, -64.2) is None
    clock.advance(1.5)
    om_module._CACHE_FORECAST._failure_cache.clear()   # el fallo de la pausa también se recuerda 15 s
    om.mock(return_value=httpx.Response(200, json=_DAILY_EXT_PAYLOAD))
    assert await get_daily_forecast_ext(-31.4, -64.2) is not None


async def test_an_excessive_retry_after_falls_back_to_the_default(om, counted, clock) -> None:
    om.mock(return_value=_too_many({"Retry-After": "86400"}))
    await get_current(-31.4, -64.2)
    assert pause.remaining() == pytest.approx(120.0)


async def test_a_non_numeric_retry_after_falls_back_to_the_default(om, counted, clock) -> None:
    om.mock(return_value=_too_many({"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}))
    await get_current(-31.4, -64.2)
    assert pause.remaining() == pytest.approx(120.0)


@pytest.mark.parametrize(
    "failure",
    [
        httpx.Response(500),
        httpx.Response(503),
        httpx.Response(404),
        httpx.Response(400),
        httpx.ConnectError("sin red"),
        httpx.ReadTimeout("lento"),
    ],
    ids=["500", "503", "404", "400", "connect-error", "timeout"],
)
async def test_other_failures_do_not_start_a_pause(failure, om, counted, clock) -> None:
    if isinstance(failure, Exception):
        om.mock(side_effect=failure)
    else:
        om.mock(return_value=failure)
    assert await get_current(-31.4, -64.2) is None
    assert pause.remaining() == 0.0
    assert pause.allow_request() is True


async def test_a_pause_serves_the_memory_stale_copy_without_network(om, counted, clock) -> None:
    om.mock(return_value=httpx.Response(200, json=_CURRENT_PAYLOAD))
    first = await get_current(-31.4, -64.2)
    assert first is not None
    om_module._CACHE_CURRENT._cache.clear()                         # venció el TTL fresco
    om_module._CACHE_CURRENT._failure_cache.clear()

    pause.trip()
    calls_before = om.call_count
    outcome = CacheOutcome()
    assert await get_current(-31.4, -64.2, cache_outcome=outcome) is first
    assert outcome.hit is True
    assert om.call_count == calls_before


async def test_the_counter_still_counts_normal_requests(om, counted, clock) -> None:
    om.mock(return_value=httpx.Response(200, json=_CURRENT_PAYLOAD))
    await get_current(-31.4, -64.2)
    await get_current(-34.6, -58.4)
    assert counted == ["open_meteo", "open_meteo"]


async def test_the_pause_fixture_starts_every_test_clean() -> None:
    assert pause.remaining() == 0.0
    assert pause.allow_request() is True


async def test_the_first_429_costs_a_single_http_call(om, counted, clock) -> None:
    om.mock(return_value=_too_many())
    assert await get_current(-31.4, -64.2) is None
    assert om.call_count == 1                      # sin el reintento de fetch_with_retry


async def test_a_5xx_is_still_retried_once(om, counted, clock) -> None:
    om.mock(return_value=httpx.Response(503))
    assert await get_current(-31.4, -64.2) is None
    assert om.call_count == 2


async def test_a_slow_request_started_before_a_429_cannot_close_the_pause(om, counted, clock) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["latitude"] == "-31.4":
            await asyncio.sleep(0.05)              # termina DESPUÉS del 429 del otro pedido
            return httpx.Response(200, json=_CURRENT_PAYLOAD)
        return _too_many()

    om.mock(side_effect=handler)
    slow, limited = await asyncio.gather(get_current(-31.4, -64.2), get_current(-34.6, -58.4))
    assert slow is not None and limited is None
    assert pause.remaining() == pytest.approx(120.0)
    assert await get_daily_forecast_ext(-31.4, -64.2) is None      # y no sale a la red
    assert om.call_count == 2


async def test_a_tiny_retry_after_still_pauses_at_least_ten_seconds(om, counted, clock) -> None:
    om.mock(return_value=_too_many({"Retry-After": "1"}))
    await get_current(-31.4, -64.2)
    assert pause.remaining() == pytest.approx(10.0)
