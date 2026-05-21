"""Tests para el endpoint /healthz."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
@pytest.mark.integration
async def test_healthz_returns_ok(async_client: AsyncClient):
    """GET /healthz debe retornar 200 con {"status": "ok"}."""
    response = await async_client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
