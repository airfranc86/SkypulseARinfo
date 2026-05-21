"""Tests para el cliente Open-Meteo."""
from __future__ import annotations

import pytest
import respx
import httpx

from app.services.openmeteo import get_current
from tests.conftest import OPENMETEO_SAMPLE_PAYLOAD


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_current_returns_dataclass():
    """Debe parsear el payload de Open-Meteo y devolver el dataclass."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json=OPENMETEO_SAMPLE_PAYLOAD)
        )
        result = await get_current(-31.4, -64.2)

    assert result is not None
    assert result.temp_c == pytest.approx(23.5)
    assert result.feels_like_c == pytest.approx(22.1)
    assert result.humidity == pytest.approx(52.0)
    assert result.wind_speed_kmh == pytest.approx(18.0)
    assert result.wind_dir_deg == pytest.approx(270.0)
    assert result.pressure_hpa == pytest.approx(1014.2)
    assert result.precip_1h_mm == pytest.approx(0.0)
    assert result.cloud_cover == pytest.approx(10.0)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_current_returns_none_on_timeout():
    with respx.mock() as mock:
        mock.get("https://api.open-meteo.com/v1/forecast").mock(
            side_effect=httpx.TimeoutException("timeout")
        )
        result = await get_current(-34.6, -58.4)

    assert result is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_current_returns_none_on_5xx():
    with respx.mock() as mock:
        mock.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(500)
        )
        result = await get_current(-34.6, -58.4)

    assert result is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_current_uses_best_match_by_default():
    """Sin parámetro 'models' → Open-Meteo usa best_match automáticamente.
    ecmwf_ifs04 fue removido porque tiene delay de publicación y devuelve nulls
    para el slot actual, lo que dispara all_sources_unavailable en producción."""
    captured_request = None

    with respx.mock(assert_all_called=False) as mock:
        def capture(request: httpx.Request):
            nonlocal captured_request
            captured_request = request
            return httpx.Response(200, json=OPENMETEO_SAMPLE_PAYLOAD)

        mock.get("https://api.open-meteo.com/v1/forecast").mock(side_effect=capture)
        await get_current(-31.4, -64.2)

    assert captured_request is not None
    params = dict(httpx.URL(str(captured_request.url)).params)
    assert "models" not in params, "No debe forzar modelo: Open-Meteo elige best_match"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_current_sends_wind_speed_in_kmh():
    """El request debe solicitar wind_speed_unit=kmh."""
    captured_request = None

    with respx.mock(assert_all_called=False) as mock:
        def capture(request: httpx.Request):
            nonlocal captured_request
            captured_request = request
            return httpx.Response(200, json=OPENMETEO_SAMPLE_PAYLOAD)

        mock.get("https://api.open-meteo.com/v1/forecast").mock(side_effect=capture)
        await get_current(-31.4, -64.2)

    assert captured_request is not None
    params = dict(httpx.URL(str(captured_request.url)).params)
    assert params.get("wind_speed_unit") == "kmh"
