"""Tests del aeropuerto argentino más cercano (lookup puro, sin llamadas externas).

Unit: `nearest_airport_with_distance` y el haversine.
Integración: GET /api/metar/nearest?lat=&lon=
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.services.reportes_aeronauticos.aeropuertos import haversine_km, nearest_airport_with_distance

URL = "/api/metar/nearest"


def test_haversine_zero_distance() -> None:
    assert haversine_km(-31.3, -64.2, -31.3, -64.2) == pytest.approx(0.0, abs=1e-9)


def test_haversine_one_degree_latitude_is_about_111_km() -> None:
    assert haversine_km(-31.0, -64.0, -32.0, -64.0) == pytest.approx(111.2, abs=0.5)


def test_nearest_with_distance_cordoba_city() -> None:
    airport, km = nearest_airport_with_distance(-31.42, -64.18)
    assert airport.icao == "SACO"
    assert 5 < km < 20


def test_nearest_with_distance_exact_airport_is_zero() -> None:
    airport, km = nearest_airport_with_distance(-31.323, -64.208)
    assert airport.icao == "SACO"
    assert km == pytest.approx(0.0, abs=1e-6)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_nearest_cordoba_returns_saco(async_client: AsyncClient) -> None:
    response = await async_client.get(URL, params={"lat": -31.42, "lon": -64.18})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"icao", "name", "lat", "lon", "distance_km"}
    assert body["icao"] == "SACO"
    assert body["name"] == "Córdoba"
    assert body["lat"] == pytest.approx(-31.323)
    assert body["lon"] == pytest.approx(-64.208)
    assert 5 < body["distance_km"] < 20


@pytest.mark.asyncio
@pytest.mark.integration
async def test_nearest_buenos_aires_returns_aeroparque_or_ezeiza(async_client: AsyncClient) -> None:
    response = await async_client.get(URL, params={"lat": -34.6037, "lon": -58.3816})

    assert response.status_code == 200
    # Obelisco: el más cercano de la lista es Aeroparque (SABE).
    assert response.json()["icao"] == "SABE"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_nearest_does_not_collide_with_metar_route(async_client: AsyncClient, monkeypatch) -> None:
    import app.core.config as cfg

    monkeypatch.setattr(cfg.settings, "checkwx_api_key", "test-key", raising=False)
    # `/api/metar?icao=...` sigue siendo la ruta de CheckWX (422 con ICAO inválido).
    response = await async_client.get("/api/metar", params={"icao": "!!!!"})
    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_icao"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize(
    "params",
    [
        {"lat": 10.0, "lon": -64.0},
        {"lat": -31.0, "lon": 20.0},
        {"lat": "SECRETO", "lon": -64.0},
    ],
)
async def test_nearest_out_of_bounds_422_without_echo(async_client: AsyncClient, params: dict) -> None:
    response = await async_client.get(URL, params=params)

    assert response.status_code == 422
    assert "SECRETO" not in response.text
    assert "input" not in response.text


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("params", [{}, {"lat": -31.0}, {"lon": -64.0}])
async def test_nearest_missing_param_422(async_client: AsyncClient, params: dict) -> None:
    response = await async_client.get(URL, params=params)
    assert response.status_code == 422
