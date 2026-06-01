"""Cliente httpx compartido — lifecycle gestionado por el lifespan de FastAPI."""
from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx

from app.core.config import settings

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    """Retorna el cliente global. Raise RuntimeError si no fue inicializado."""
    if _client is None:
        raise RuntimeError(
            "httpx.AsyncClient no inicializado. "
            "Verificá que create_client() se llamó en el lifespan startup."
        )
    return _client


async def create_client() -> None:
    """Crea el cliente global. Llamar una vez en startup."""
    global _client
    _client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.http_timeout_seconds),
        limits=httpx.Limits(max_connections=40, max_keepalive_connections=10),
    )


async def close_client() -> None:
    """Cierra el cliente global. Llamar una vez en shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

def _backoff_delay(attempt: int) -> float:
    """Exponential backoff with ±25 % jitter. First delay ≈ 0.5 s."""
    base = min(0.5 * (2 ** attempt), 2.0)
    return base + random.uniform(0, base * 0.25)


async def fetch_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_attempts: int = 2,
    retry_after_cap: float = 3.0,
    **kwargs: Any,
) -> httpx.Response:
    """HTTP request with transparent retry on transient errors.

    Retries on: TimeoutException, TransportError, HTTP 429, HTTP 5xx.
    On 429 + Retry-After > retry_after_cap: aborts immediately without waiting.
    Raises on final failure — caller decides how to degrade.
    """
    for attempt in range(max_attempts):
        is_last = attempt == max_attempts - 1
        try:
            response = await client.request(method, url, **kwargs)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            if is_last:
                raise
            await asyncio.sleep(_backoff_delay(attempt))
            continue

        # 2xx / 3xx / non-retryable 4xx
        if response.status_code != 429 and response.status_code < 500:
            response.raise_for_status()
            return response

        # 429 or 5xx — retryable
        if is_last:
            response.raise_for_status()

        # Compute wait
        if response.status_code == 429 and "Retry-After" in response.headers:
            try:
                requested = float(response.headers["Retry-After"])
            except ValueError:
                requested = retry_after_cap + 1.0
            if requested > retry_after_cap:
                response.raise_for_status()  # abort: server asked to wait too long
            delay: float = requested
        else:
            delay = _backoff_delay(attempt)

        await asyncio.sleep(delay)

    raise httpx.RequestError("fetch_with_retry: exhausted without returning")
