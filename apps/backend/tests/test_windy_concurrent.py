"""Tests de concurrencia para _fetch_raw de Windy (Fix 3).

Cubre el bug KeyError: cuando el fetcher falla mientras waiters esperan,
todas las coroutines deben recibir la excepción real, nunca un KeyError.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from app.services.windy import (
    WindyNotConfiguredError,
    _fetch_raw,
    get_hourly_forecast,
    get_temp_850hpa_first,
)
import app.services.windy as windy_module


# ---------------------------------------------------------------------------
# Payload mínimo válido para los tests de éxito
# ---------------------------------------------------------------------------

_WINDY_MINIMAL = {
    "ts": [1747742400000],
    "temp-surface": [295.15],
    "rh-surface": [55.0],
    "wind_u-surface": [3.0],
    "wind_v-surface": [4.0],
    "past3hprecip-surface": [0.0],
    "windGust-surface": [8.0],
    "lclouds-surface": [20.0],
    "mclouds-surface": [10.0],
    "hclouds-surface": [5.0],
    "dewpoint-surface": [285.0],
    "temp-850h": [280.0],
}

WINDY_URL = "https://api.windy.com/api/point-forecast/v2"


@pytest.fixture(autouse=True)
def enable_windy(monkeypatch):
    """Habilita Windy para los tests de este módulo."""
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "windy_api_key", "test-key", raising=False)
    monkeypatch.setattr(cfg.settings, "windy_base_url", WINDY_URL, raising=False)
    monkeypatch.setattr(cfg.settings, "windy_model", "gfs", raising=False)


# ---------------------------------------------------------------------------
# Fallo concurrente — la causa raíz del bug
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_fetch_failure_no_keyerror():
    """N coroutines concurrentes, el fetch falla → todas reciben la excepción real (no KeyError)."""
    with respx.mock(assert_all_called=False) as mock:
        async def slow_fail(request):
            await asyncio.sleep(0.05)
            return httpx.Response(500)

        mock.post(WINDY_URL).mock(side_effect=slow_fail)

        results = await asyncio.gather(
            *[_fetch_raw(-34.6, -58.4) for _ in range(4)],
            return_exceptions=True,
        )

    assert len(results) == 4
    for r in results:
        assert isinstance(r, Exception), f"Esperaba excepción, got {type(r)}"
        # Nunca debe ser KeyError
        assert not isinstance(r, KeyError), "KeyError no debe propagarse a las waiters"
        # Nunca debe ser un dict (datos parciales)
        assert not isinstance(r, dict)


@pytest.mark.asyncio
async def test_concurrent_fetch_timeout_no_keyerror():
    """Timeout en el fetch → waiters reciben TimeoutException, no KeyError."""
    with respx.mock(assert_all_called=False) as mock:
        async def slow_timeout(request):
            await asyncio.sleep(0.05)
            raise httpx.TimeoutException("simulated timeout")

        mock.post(WINDY_URL).mock(side_effect=slow_timeout)

        results = await asyncio.gather(
            *[_fetch_raw(-34.6, -58.4) for _ in range(3)],
            return_exceptions=True,
        )

    for r in results:
        assert isinstance(r, Exception)
        assert not isinstance(r, KeyError)


@pytest.mark.asyncio
async def test_concurrent_fetch_success_dedup():
    """Éxito concurrente → 1 solo fetch, todas las waiters reciben el mismo dato."""
    call_count = 0

    with respx.mock(assert_all_called=False) as mock:
        async def slow_ok(request):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            return httpx.Response(200, json=_WINDY_MINIMAL)

        mock.post(WINDY_URL).mock(side_effect=slow_ok)

        results = await asyncio.gather(
            *[_fetch_raw(-34.6, -58.4) for _ in range(5)],
        )

    assert call_count == 1, f"Dedup fallido: se hicieron {call_count} fetches"
    assert all(r is results[0] for r in results), "Todas las waiters deben recibir el mismo objeto"


@pytest.mark.asyncio
async def test_concurrent_failure_same_exception_type():
    """Todas las waiters reciben la misma excepción que lanzó el fetcher."""
    with respx.mock(assert_all_called=False) as mock:
        async def slow_fail(request):
            await asyncio.sleep(0.05)
            return httpx.Response(503)

        mock.post(WINDY_URL).mock(side_effect=slow_fail)

        results = await asyncio.gather(
            *[_fetch_raw(-34.6, -58.4) for _ in range(3)],
            return_exceptions=True,
        )

    # httpx.HTTPStatusError para 503
    types = [type(r) for r in results]
    assert len(set(types)) == 1, f"Tipos inconsistentes: {types}"


# ---------------------------------------------------------------------------
# WindyNotConfiguredError — no debe pasar por el mecanismo de slot
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_windy_not_configured_raises_immediately(monkeypatch):
    """WindyNotConfiguredError se lanza antes de tocar el slot — no debe quedar slot huérfano."""
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "windy_api_key", "", raising=False)

    with pytest.raises(WindyNotConfiguredError):
        await _fetch_raw(-34.6, -58.4)

    # No debe quedar ningún slot en vuelo
    assert len(windy_module._fetch_events) == 0


# ---------------------------------------------------------------------------
# get_temp_850hpa_first — llamador directo sin wrapper de seguridad
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_temp_850hpa_first_concurrent_failure_no_keyerror():
    """get_temp_850hpa_first es un llamador directo de _fetch_raw sin try/except.

    Verifica que el fallo concurrente no produce KeyError sino la excepción real.
    """
    with respx.mock(assert_all_called=False) as mock:
        async def slow_fail(request):
            await asyncio.sleep(0.05)
            return httpx.Response(500)

        mock.post(WINDY_URL).mock(side_effect=slow_fail)

        results = await asyncio.gather(
            *[get_temp_850hpa_first(-34.6, -58.4) for _ in range(3)],
            return_exceptions=True,
        )

    for r in results:
        assert isinstance(r, Exception)
        assert not isinstance(r, KeyError)


@pytest.mark.asyncio
async def test_get_hourly_forecast_concurrent_failure_no_keyerror():
    """get_hourly_forecast en concurrencia con fallo → excepción real a todos."""
    with respx.mock(assert_all_called=False) as mock:
        async def slow_fail(request):
            await asyncio.sleep(0.05)
            return httpx.Response(429)

        mock.post(WINDY_URL).mock(side_effect=slow_fail)

        results = await asyncio.gather(
            *[get_hourly_forecast(-34.6, -58.4) for _ in range(3)],
            return_exceptions=True,
        )

    for r in results:
        assert isinstance(r, Exception)
        assert not isinstance(r, KeyError)


# ---------------------------------------------------------------------------
# Slot cleanup — no debe quedar basura en _fetch_events tras fallo
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_events_cleaned_up_after_failure():
    """Después de un fallo, _fetch_events debe estar vacío (no quedan slots huérfanos)."""
    with respx.mock(assert_all_called=False) as mock:
        mock.post(WINDY_URL).mock(return_value=httpx.Response(500))

        await asyncio.gather(
            *[_fetch_raw(-34.6, -58.4) for _ in range(2)],
            return_exceptions=True,
        )

    assert len(windy_module._fetch_events) == 0, "Slots huérfanos en _fetch_events"


@pytest.mark.asyncio
async def test_fetch_events_cleaned_up_after_success():
    """Después de éxito, _fetch_events debe estar vacío."""
    with respx.mock(assert_all_called=False) as mock:
        mock.post(WINDY_URL).mock(return_value=httpx.Response(200, json=_WINDY_MINIMAL))

        await asyncio.gather(*[_fetch_raw(-34.6, -58.4) for _ in range(2)])

    assert len(windy_module._fetch_events) == 0
