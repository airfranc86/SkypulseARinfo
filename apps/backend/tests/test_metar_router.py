"""Tests de integración del router /api/metar.

R1 — Sin CHECKWX_API_KEY → 503 checkwx_not_configured
R2 — Request válida (SAEZ) → 200 con payload CheckWX
R3 — Cuota agotada → 429 con Retry-After y body estructurado
R4 — ICAO inválido → 422
R5 — type=taf → 200 con payload TAF
R6 — Segundo request al mismo ICAO en <TTL → cache hit, counter no sube
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.core.counter import MemoryCounter, current_cycle
from app.services import checkwx as checkwx_svc

_METAR_PAYLOAD = {
    "results": 1,
    "data": [{"icao": "SAEZ", "raw_text": "SAEZ 011200Z 24010KT 9999 FEW020 22/14 Q1018"}],
}
_TAF_PAYLOAD = {
    "results": 1,
    "data": [{"icao": "SAEZ", "raw_text": "TAF SAEZ 011100Z 0112/0218 24010KT 9999 FEW020"}],
}


@pytest.fixture(autouse=True)
def setup_checkwx(monkeypatch):
    """API key configurada y counter limpio para cada test."""
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "checkwx_api_key", "test-key", raising=False)
    monkeypatch.setattr(cfg.settings, "checkwx_monthly_limit", 198, raising=False)

    counter = MemoryCounter()
    checkwx_svc.set_counter(counter)
    yield counter
    checkwx_svc._metar_cache.clear()
    checkwx_svc._taf_cache.clear()
    checkwx_svc.set_counter(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# R1 — sin API key
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_r1_no_api_key_returns_503(async_client: AsyncClient, monkeypatch):
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "checkwx_api_key", "", raising=False)

    response = await async_client.get("/api/metar?icao=SAEZ")

    assert response.status_code == 503
    assert response.json()["detail"] == "checkwx_not_configured"


# ---------------------------------------------------------------------------
# R2 — request válida → 200
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_r2_valid_request_returns_200(async_client: AsyncClient):
    with patch.object(checkwx_svc, "fetch_metar", new_callable=AsyncMock, return_value=_METAR_PAYLOAD):
        response = await async_client.get("/api/metar?icao=SAEZ")

    assert response.status_code == 200
    assert response.json()["results"] == 1
    assert response.json()["data"][0]["icao"] == "SAEZ"


# ---------------------------------------------------------------------------
# R3 — cuota agotada → 429
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_r3_quota_exhausted_returns_429(async_client: AsyncClient, setup_checkwx: MemoryCounter):
    cycle = current_cycle()
    for _ in range(198):
        await setup_checkwx.incr(cycle)

    with patch("app.core.notifier.sentry_sdk"):
        response = await async_client.get("/api/metar?icao=SAEZ")

    assert response.status_code == 429
    data = response.json()
    assert data["detail"]["error"] == "metar_quota_exceeded"
    assert data["detail"]["cycle"] == cycle
    assert data["detail"]["limit"] == 198
    assert "retry_after" in data["detail"]
    assert "Retry-After" in response.headers


# ---------------------------------------------------------------------------
# R4 — ICAO inválido → 422
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_r4_invalid_icao_returns_422(async_client: AsyncClient):
    response = await async_client.get("/api/metar?icao=XX")
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.integration
async def test_r4_icao_lowercase_accepted(async_client: AsyncClient):
    """ICAO en minúscula debe ser normalizado a mayúscula."""
    with patch.object(checkwx_svc, "fetch_metar", new_callable=AsyncMock, return_value=_METAR_PAYLOAD):
        response = await async_client.get("/api/metar?icao=saez")

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# R5 — type=taf → 200
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_r5_taf_request_returns_200(async_client: AsyncClient):
    with patch.object(checkwx_svc, "fetch_metar", new_callable=AsyncMock, return_value=_TAF_PAYLOAD):
        response = await async_client.get("/api/metar?icao=SAEZ&type=taf")

    assert response.status_code == 200
    assert response.json()["data"][0]["icao"] == "SAEZ"


# ---------------------------------------------------------------------------
# R6 — cache hit en segundo request
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_r6_cache_hit_does_not_increment_counter(async_client: AsyncClient, setup_checkwx: MemoryCounter):
    cycle = current_cycle()

    with patch.object(checkwx_svc, "_do_http_fetch", new_callable=AsyncMock, return_value=_METAR_PAYLOAD):
        await async_client.get("/api/metar?icao=SAEZ")
        await async_client.get("/api/metar?icao=SAEZ")

    assert await setup_checkwx.get(cycle) == 1
