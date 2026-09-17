"""Tests de integración para GET /api/alertas-smn."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.schemas.smn_alertas import SmnAlerta, SmnAlertasResponse


@pytest.mark.asyncio
@pytest.mark.integration
async def test_alertas_smn_happy_path(async_client: AsyncClient):
    fake_response = SmnAlertasResponse(
        alertas=[
            SmnAlerta(
                nivel="rojo",
                tipo="Tormenta",
                fecha_desde=datetime(2026, 1, 15, tzinfo=timezone.utc),
                fecha_hasta=datetime(2026, 1, 16, tzinfo=timezone.utc),
                descripcion="Tormenta severa en la región serrana",
            )
        ],
        available=True,
        fetched_at=datetime.now(timezone.utc),
    )
    with patch(
        "app.routers.smn_alertas.get_smn_alertas",
        new_callable=AsyncMock,
        return_value=fake_response,
    ):
        response = await async_client.get("/api/alertas-smn")

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert len(data["alertas"]) == 1
    assert data["alertas"][0]["nivel"] == "rojo"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_alertas_smn_unavailable_still_returns_200(async_client: AsyncClient):
    """Fuente caída no debe ser un 5xx — el frontend decide qué mostrar con available=false."""
    fake_response = SmnAlertasResponse(alertas=[], available=False, fetched_at=datetime.now(timezone.utc))
    with patch(
        "app.routers.smn_alertas.get_smn_alertas",
        new_callable=AsyncMock,
        return_value=fake_response,
    ):
        response = await async_client.get("/api/alertas-smn")

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is False
    assert data["alertas"] == []
