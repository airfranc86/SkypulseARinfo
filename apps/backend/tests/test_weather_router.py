"""Tests de integración para el router GET /api/weather/current."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient

from app.schemas.weather import WeatherCurrentResponse, SourceMeta, StationMeta


def _make_response() -> WeatherCurrentResponse:
    station = StationMeta(
        name="CÓRDOBA AEROPUERTO",
        lat=-31.323,
        lon=-64.208,
        distance_km=15.2,
        observed_at=datetime.now(timezone.utc),
    )
    meta = SourceMeta(
        source="smn",
        reason="smn_nearby_fresh",
        station=station,
        fetched_at=datetime.now(timezone.utc),
        cache_hit=False,
    )
    return WeatherCurrentResponse(
        lat=-31.4,
        lon=-64.2,
        temp_c=22.0,
        feels_like_c=21.0,
        humidity=55.0,
        wind_speed_kmh=15.0,
        wind_dir_deg=270.0,
        wind_dir_cardinal="W",
        pressure_hpa=1013.0,
        precip_1h_mm=None,
        cloud_cover=None,
        description="Despejado",
        meta=meta,
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_happy_path_cordoba(async_client: AsyncClient):
    """Debe retornar 200 con payload completo para coordenadas válidas."""
    mock_response = _make_response()

    with patch(
        "app.routers.weather.aggregate_current",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        response = await async_client.get("/api/weather/current?lat=-31.4&lon=-64.2")

    assert response.status_code == 200
    data = response.json()
    assert data["temp_c"] == pytest.approx(22.0)
    assert data["meta"]["source"] == "smn"
    assert data["meta"]["reason"] == "smn_nearby_fresh"
    assert data["wind_dir_cardinal"] == "W"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_outside_argentina_lat_too_low_returns_422(async_client: AsyncClient):
    """lat=-60 está fuera del rango [-55, -21]."""
    response = await async_client.get("/api/weather/current?lat=-60&lon=-64.2")
    assert response.status_code == 422
    data = response.json()
    assert data["error"] in ("outside_argentina", "invalid_coordinates")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_outside_argentina_lat_too_high_returns_422(async_client: AsyncClient):
    """lat=-10 está por encima del rango."""
    response = await async_client.get("/api/weather/current?lat=-10&lon=-64.2")
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.integration
async def test_lon_outside_returns_422(async_client: AsyncClient):
    """lon=-50 está fuera del rango [-74, -53]."""
    response = await async_client.get("/api/weather/current?lat=-34.6&lon=-50")
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.integration
async def test_invalid_type_returns_422(async_client: AsyncClient):
    """lat='abc' debe fallar en validación de tipo."""
    response = await async_client.get("/api/weather/current?lat=abc&lon=-64.2")
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.integration
async def test_missing_params_returns_422(async_client: AsyncClient):
    """Sin lat ni lon debe retornar 422."""
    response = await async_client.get("/api/weather/current")
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.integration
async def test_503_when_all_sources_down(async_client: AsyncClient):
    """Cuando ambas fuentes fallan debe retornar 503."""
    from fastapi import HTTPException

    with patch(
        "app.routers.weather.aggregate_current",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=503, detail="all_sources_unavailable"),
    ):
        response = await async_client.get("/api/weather/current?lat=-34.6&lon=-58.4")

    assert response.status_code == 503


# ---------------------------------------------------------------------------
# Bordes inclusivos de coordenadas
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_lat_minus_55_exact_returns_200_or_503(async_client: AsyncClient):
    """lat=-55 es el borde inferior inclusivo — debe pasar validación (200 o 503)."""
    mock_response = _make_response()
    with patch(
        "app.routers.weather.aggregate_current",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        response = await async_client.get("/api/weather/current?lat=-55&lon=-64.2")
    assert response.status_code in (200, 503)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_lat_minus_21_exact_returns_200_or_503(async_client: AsyncClient):
    """lat=-21 es el borde superior inclusivo — debe pasar validación."""
    mock_response = _make_response()
    with patch(
        "app.routers.weather.aggregate_current",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        response = await async_client.get("/api/weather/current?lat=-21&lon=-64.2")
    assert response.status_code in (200, 503)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_lon_minus_74_exact_returns_200_or_503(async_client: AsyncClient):
    """lon=-74 es el borde oeste inclusivo — debe pasar validación."""
    mock_response = _make_response()
    with patch(
        "app.routers.weather.aggregate_current",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        response = await async_client.get("/api/weather/current?lat=-34.6&lon=-74")
    assert response.status_code in (200, 503)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_lon_minus_53_exact_returns_200_or_503(async_client: AsyncClient):
    """lon=-53 es el borde este inclusivo — debe pasar validación."""
    mock_response = _make_response()
    with patch(
        "app.routers.weather.aggregate_current",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        response = await async_client.get("/api/weather/current?lat=-34.6&lon=-53")
    assert response.status_code in (200, 503)


# ---------------------------------------------------------------------------
# Guards NaN / Infinito (nuevo field_validator en WeatherCurrentResponse)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_lat_nan_returns_422_invalid_coordinates(async_client: AsyncClient):
    """lat=NaN (string) debe retornar 422 con error invalid_coordinates."""
    response = await async_client.get("/api/weather/current?lat=NaN&lon=-64.2")
    assert response.status_code == 422
    data = response.json()
    assert data["error"] == "invalid_coordinates"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_lat_infinity_returns_422(async_client: AsyncClient):
    """lat=Infinity debe retornar 422."""
    response = await async_client.get("/api/weather/current?lat=Infinity&lon=-64.2")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Verificación explícita del campo "error" en respuestas de error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_outside_argentina_response_has_error_field(async_client: AsyncClient):
    """Coordenadas fuera de Argentina deben tener error='outside_argentina'."""
    response = await async_client.get("/api/weather/current?lat=-60&lon=-64.2")
    assert response.status_code == 422
    data = response.json()
    assert data["error"] == "outside_argentina"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_invalid_type_response_has_error_field(async_client: AsyncClient):
    """Tipo inválido (string no numérico) debe tener error='invalid_coordinates'."""
    response = await async_client.get("/api/weather/current?lat=abc&lon=-64.2")
    assert response.status_code == 422
    data = response.json()
    assert data["error"] == "invalid_coordinates"


# ---------------------------------------------------------------------------
# CORS preflight
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_cors_preflight_returns_correct_headers(async_client: AsyncClient):
    """OPTIONS con Origin permitido debe retornar headers CORS."""
    response = await async_client.options(
        "/api/weather/current",
        headers={
            "Origin": "https://skypulse-ar.vercel.app",
            "Access-Control-Request-Method": "GET",
        },
    )
    # FastAPI puede responder 200 o 204 en preflight
    assert response.status_code in (200, 204)
    assert "access-control-allow-origin" in response.headers
