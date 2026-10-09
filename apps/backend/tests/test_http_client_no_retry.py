"""`fetch_with_retry(no_retry_statuses=...)`: ciertos estados se propagan de inmediato, sin reintento.

Open-Meteo responde 429 por IP compartida: un reintento 0,5 s después solo duplica la carga. El valor
por defecto (conjunto vacío) deja a todos los demás llamadores exactamente como estaban.
"""
from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from app.core.http_client import fetch_with_retry

URL = "https://example.com/api"


@pytest.fixture
def client() -> httpx.AsyncClient:
    return httpx.AsyncClient()


async def test_a_listed_429_raises_immediately_without_retry_or_sleep(client) -> None:
    with respx.mock() as mock, patch("app.core.http_client.asyncio.sleep", new_callable=AsyncMock) as sleep:
        route = mock.get(URL).mock(return_value=httpx.Response(429))
        with pytest.raises(httpx.HTTPStatusError) as raised:
            await fetch_with_retry(client, "GET", URL, no_retry_statuses=frozenset({429}))
    assert raised.value.response.status_code == 429
    assert route.call_count == 1
    sleep.assert_not_called()


async def test_a_listed_429_with_a_short_retry_after_is_not_waited_for(client) -> None:
    with respx.mock() as mock, patch("app.core.http_client.asyncio.sleep", new_callable=AsyncMock) as sleep:
        route = mock.get(URL).mock(return_value=httpx.Response(429, headers={"Retry-After": "1"}))
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_with_retry(client, "GET", URL, no_retry_statuses=frozenset({429}))
    assert route.call_count == 1
    sleep.assert_not_called()


async def test_without_the_parameter_a_429_is_retried_as_before(client) -> None:
    with respx.mock() as mock, patch("app.core.http_client.asyncio.sleep", new_callable=AsyncMock):
        route = mock.get(URL).mock(return_value=httpx.Response(429))
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_with_retry(client, "GET", URL)
    assert route.call_count == 2


async def test_the_default_set_is_empty_and_immutable() -> None:
    default = inspect.signature(fetch_with_retry).parameters["no_retry_statuses"].default
    assert default == frozenset() and isinstance(default, frozenset)


async def test_statuses_outside_the_set_still_retry(client) -> None:
    with respx.mock() as mock, patch("app.core.http_client.asyncio.sleep", new_callable=AsyncMock):
        route = mock.get(URL).mock(return_value=httpx.Response(503))
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_with_retry(client, "GET", URL, no_retry_statuses=frozenset({429}))
    assert route.call_count == 2


async def test_a_listed_5xx_also_raises_at_once(client) -> None:
    with respx.mock() as mock, patch("app.core.http_client.asyncio.sleep", new_callable=AsyncMock):
        route = mock.get(URL).mock(return_value=httpx.Response(503))
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_with_retry(client, "GET", URL, no_retry_statuses=frozenset({503}))
    assert route.call_count == 1


async def test_a_listed_success_status_is_returned_normally(client) -> None:
    with respx.mock() as mock:
        mock.get(URL).mock(return_value=httpx.Response(200, json={"ok": True}))
        response = await fetch_with_retry(client, "GET", URL, no_retry_statuses=frozenset({200}))
    assert response.status_code == 200


async def test_timeouts_are_still_retried_when_the_set_is_given(client) -> None:
    with respx.mock() as mock, patch("app.core.http_client.asyncio.sleep", new_callable=AsyncMock):
        route = mock.get(URL).mock(
            side_effect=[httpx.ReadTimeout("lento"), httpx.Response(200, json={"ok": True})]
        )
        response = await fetch_with_retry(client, "GET", URL, no_retry_statuses=frozenset({429}))
    assert response.status_code == 200
    assert route.call_count == 2
