"""Tests para fetch_with_retry (Fix 4c).

Cubre:
- Éxito al primer intento → 0 waits, respuesta devuelta.
- 503 → 1 retry; si el segundo también falla → HTTPStatusError.
- 429 sin Retry-After → backoff calculado, 1 retry.
- 429 con Retry-After ≤ cap → espera ese valor, 1 retry.
- 429 con Retry-After > cap → abort inmediato, sin sleep.
- Timeout → 1 retry.
- TransportError → 1 retry.
- 404 (no retryable) → HTTPStatusError inmediato, 0 retries.
- Éxito en el segundo intento (primera falla 503, segunda 200).
- get_current end-to-end: 429 → retry → 200 → devuelve datos.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch, call

import httpx
import pytest
import respx

from app.core.http_client import fetch_with_retry, get_client
from app.services.openmeteo import get_current
from tests.conftest import OPENMETEO_SAMPLE_PAYLOAD

OM_URL = "https://api.open-meteo.com/v1/forecast"
DUMMY_URL = "https://example.com/api"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_client():
    return httpx.AsyncClient()


# ---------------------------------------------------------------------------
# Éxito al primer intento — 0 sleeps
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_success_first_attempt_no_sleep(mock_client):
    with respx.mock() as mock, \
         patch("app.core.http_client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock.get(DUMMY_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
        response = await fetch_with_retry(mock_client, "GET", DUMMY_URL)

    assert response.status_code == 200
    mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# 5xx → retry, falla ambas → HTTPStatusError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_503_retries_once_then_raises(mock_client):
    call_count = 0

    with respx.mock() as mock, \
         patch("app.core.http_client.asyncio.sleep", new_callable=AsyncMock):
        def handler(request):
            nonlocal call_count
            call_count += 1
            return httpx.Response(503)

        mock.get(DUMMY_URL).mock(side_effect=handler)

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await fetch_with_retry(mock_client, "GET", DUMMY_URL)

    assert call_count == 2, "Debe haber exactamente 1 retry (2 intentos total)"
    assert exc_info.value.response.status_code == 503


@pytest.mark.asyncio
async def test_503_sleeps_before_retry(mock_client):
    with respx.mock() as mock, \
         patch("app.core.http_client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock.get(DUMMY_URL).mock(return_value=httpx.Response(503))

        with pytest.raises(httpx.HTTPStatusError):
            await fetch_with_retry(mock_client, "GET", DUMMY_URL)

    mock_sleep.assert_called_once()
    delay = mock_sleep.call_args[0][0]
    assert 0.5 <= delay <= 0.5 * 1.25 + 0.01, f"Delay fuera de rango: {delay}"


# ---------------------------------------------------------------------------
# 5xx → retry → 200 (éxito en segundo intento)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_5xx_then_success_returns_response(mock_client):
    responses = [httpx.Response(503), httpx.Response(200, json={"ok": True})]

    with respx.mock() as mock, \
         patch("app.core.http_client.asyncio.sleep", new_callable=AsyncMock):
        mock.get(DUMMY_URL).mock(side_effect=responses)
        response = await fetch_with_retry(mock_client, "GET", DUMMY_URL)

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# 429 sin Retry-After → backoff calculado
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_429_no_retry_after_uses_backoff(mock_client):
    responses = [httpx.Response(429), httpx.Response(200, json={"ok": True})]

    with respx.mock() as mock, \
         patch("app.core.http_client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock.get(DUMMY_URL).mock(side_effect=responses)
        response = await fetch_with_retry(mock_client, "GET", DUMMY_URL)

    assert response.status_code == 200
    mock_sleep.assert_called_once()


# ---------------------------------------------------------------------------
# 429 con Retry-After ≤ cap → respeta el header
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_429_retry_after_within_cap_respects_header(mock_client):
    headers = {"Retry-After": "1.5"}
    responses = [
        httpx.Response(429, headers=headers),
        httpx.Response(200, json={"ok": True}),
    ]

    with respx.mock() as mock, \
         patch("app.core.http_client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock.get(DUMMY_URL).mock(side_effect=responses)
        response = await fetch_with_retry(mock_client, "GET", DUMMY_URL, retry_after_cap=3.0)

    assert response.status_code == 200
    mock_sleep.assert_called_once_with(1.5)


# ---------------------------------------------------------------------------
# 429 con Retry-After > cap → abort, sin sleep
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_429_retry_after_exceeds_cap_aborts_immediately(mock_client):
    headers = {"Retry-After": "10"}

    with respx.mock() as mock, \
         patch("app.core.http_client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock.get(DUMMY_URL).mock(return_value=httpx.Response(429, headers=headers))

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await fetch_with_retry(mock_client, "GET", DUMMY_URL, retry_after_cap=3.0)

    mock_sleep.assert_not_called()
    assert exc_info.value.response.status_code == 429


# ---------------------------------------------------------------------------
# Timeout → 1 retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_timeout_retries_once_then_raises(mock_client):
    call_count = 0

    with respx.mock() as mock, \
         patch("app.core.http_client.asyncio.sleep", new_callable=AsyncMock):
        def handler(request):
            nonlocal call_count
            call_count += 1
            raise httpx.TimeoutException("timeout")

        mock.get(DUMMY_URL).mock(side_effect=handler)

        with pytest.raises(httpx.TimeoutException):
            await fetch_with_retry(mock_client, "GET", DUMMY_URL)

    assert call_count == 2


@pytest.mark.asyncio
async def test_timeout_then_success_returns_response(mock_client):
    responses: list = [
        httpx.TimeoutException("timeout"),
        httpx.Response(200, json={"ok": True}),
    ]

    with respx.mock() as mock, \
         patch("app.core.http_client.asyncio.sleep", new_callable=AsyncMock):
        mock.get(DUMMY_URL).mock(side_effect=responses)
        response = await fetch_with_retry(mock_client, "GET", DUMMY_URL)

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# TransportError → 1 retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transport_error_retries_once(mock_client):
    call_count = 0

    with respx.mock() as mock, \
         patch("app.core.http_client.asyncio.sleep", new_callable=AsyncMock):
        def handler(request):
            nonlocal call_count
            call_count += 1
            raise httpx.ConnectError("connection refused")

        mock.get(DUMMY_URL).mock(side_effect=handler)

        with pytest.raises(httpx.ConnectError):
            await fetch_with_retry(mock_client, "GET", DUMMY_URL)

    assert call_count == 2


# ---------------------------------------------------------------------------
# 404 (no retryable) → HTTPStatusError inmediato, 1 solo intento
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_404_not_retried(mock_client):
    call_count = 0

    with respx.mock() as mock, \
         patch("app.core.http_client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        def handler(request):
            nonlocal call_count
            call_count += 1
            return httpx.Response(404)

        mock.get(DUMMY_URL).mock(side_effect=handler)

        with pytest.raises(httpx.HTTPStatusError):
            await fetch_with_retry(mock_client, "GET", DUMMY_URL)

    assert call_count == 1, "404 no debe reintentarse"
    mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# Integración end-to-end: get_current con 429 → retry → 200
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_current_recovers_from_429():
    """get_current debe devolver datos si el primer intento da 429 y el segundo 200."""
    responses = [
        httpx.Response(429),
        httpx.Response(200, json=OPENMETEO_SAMPLE_PAYLOAD),
    ]

    with respx.mock(assert_all_called=False) as mock, \
         patch("app.core.http_client.asyncio.sleep", new_callable=AsyncMock):
        mock.get(OM_URL).mock(side_effect=responses)
        result = await get_current(-31.4, -64.2)

    assert result is not None
    assert result.temp_c == pytest.approx(23.5)


@pytest.mark.asyncio
async def test_get_current_returns_none_after_two_503():
    """Dos 503 consecutivos → get_current devuelve None (degradación limpia)."""
    with respx.mock(assert_all_called=False) as mock, \
         patch("app.core.http_client.asyncio.sleep", new_callable=AsyncMock):
        mock.get(OM_URL).mock(return_value=httpx.Response(503))
        result = await get_current(-31.4, -64.2)

    assert result is None
