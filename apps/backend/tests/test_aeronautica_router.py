"""Tests de integración para POST /api/v1/aeronautica/density-altitude."""
from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

URL = "/api/v1/aeronautica/density-altitude"

VALID_BODY = {
    "elev_ft": 5000,
    "qnh_hpa": 1013.25,
    "oat_c": 35,
    "td_c": 10,
    "wl_nom": 1.5,
    "ias_kt": 100,
    "aircraft_model": "piston",
}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_density_altitude_happy_path(async_client: AsyncClient):
    response = await async_client.post(URL, json=VALID_BODY)

    assert response.status_code == 200
    data = response.json()
    assert data["risk_level"] == "naranja"
    assert 6000 <= data["density_altitude_ft"] <= 9000
    assert data["wl_eff"] > 1.5
    assert data["engine_power_loss_pct"] is not None
    assert isinstance(data["decision_texts"], list) and data["decision_texts"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_density_altitude_turboprop_omits_piston_power_loss(async_client: AsyncClient):
    response = await async_client.post(URL, json={**VALID_BODY, "aircraft_model": "turboprop"})

    assert response.status_code == 200
    assert response.json()["engine_power_loss_pct"] is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dew_point_above_temperature_is_rejected(async_client: AsyncClient):
    response = await async_client.post(URL, json={**VALID_BODY, "oat_c": 10, "td_c": 20})

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize(
    "override",
    [
        {"aircraft_model": "jet"},
        {"wl_nom": 0},
        {"ias_kt": -5},
        {"qnh_hpa": 500},
        {"elev_ft": "abc"},
    ],
)
async def test_invalid_fields_return_422_without_echoing_input(async_client: AsyncClient, override):
    response = await async_client.post(URL, json={**VALID_BODY, **override})

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "invalid_request"
    assert "abc" not in response.text


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
async def test_non_finite_numbers_return_422_not_500(async_client: AsyncClient, token):
    # httpx no serializa NaN/Inf con json=; se manda el JSON crudo que aceptaría json.loads.
    raw = json.dumps({**VALID_BODY, "oat_c": "__TOKEN__"}).replace('"__TOKEN__"', token)
    response = await async_client.post(
        URL, content=raw, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.integration
async def test_missing_field_returns_422(async_client: AsyncClient):
    body = {k: v for k, v in VALID_BODY.items() if k != "td_c"}
    response = await async_client.post(URL, json=body)

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cors_preflight_allows_post(async_client: AsyncClient):
    response = await async_client.options(
        URL,
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert "POST" in response.headers["access-control-allow-methods"]
