"""Descripción de /api/tools/cota-de-nieve: el rango abarca los métodos disponibles.

El promedio sale de tres métodos (Alcaide, gradiente y 850 hPa). La descripción tiene que
mostrar el mínimo y el máximo de todos ellos, para que ninguno ni el promedio queden afuera.
"""
from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.services.calculators import SnowLevelResult
from tests.hourly_fixtures import make_uniform_hourly
from tests.test_tools_router import HOURLY, _make_weather_response, _patch_hourly

URL = "/api/tools/cota-de-nieve?lat=-38.0&lon=-70.0"
RANGE_RE = re.compile(r"entre (\d+) y (\d+) msnm \(promedio (\d+) msnm\)")


def _fixed_result(alcaide: float, gradiente: float, m850: float | None, average: float) -> SnowLevelResult:
    return SnowLevelResult(
        alcaide_m=alcaide,
        gradiente_m=gradiente,
        m850_hpa_m=m850,
        average_m=average,
        temp_c=10.0,
        station_altitude_m=750.0,
    )


async def _get_with_fixed(async_client: AsyncClient, result: SnowLevelResult) -> dict:
    with _patch_hourly(make_uniform_hourly(temp_850=5.0, elevation_m=750.0)), patch(
        "app.routers.tools.aggregate_current",
        new_callable=AsyncMock,
        return_value=_make_weather_response(temp_c=10.0),
    ), patch("app.routers.tools.calculators.compute_cota_de_nieve", return_value=result):
        response = await async_client.get(URL)
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_description_range_includes_the_850_hpa_value(async_client: AsyncClient):
    """Caso real: Alcaide 2797, gradiente 2935, 850 hPa 2593, promedio 2775."""
    data = await _get_with_fixed(async_client, _fixed_result(2797.0, 2935.0, 2593.0, 2775.0))
    assert data["description"] == (
        "Cota de nieve estimada entre 2593 y 2935 msnm (promedio 2775 msnm)"
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_description_range_when_850_hpa_is_the_highest(async_client: AsyncClient):
    data = await _get_with_fixed(async_client, _fixed_result(1000.0, 1200.0, 1800.0, 1333.0))
    assert data["description"] == (
        "Cota de nieve estimada entre 1000 y 1800 msnm (promedio 1333 msnm)"
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_description_range_when_alcaide_is_above_the_gradient(async_client: AsyncClient):
    """Con mucho frío Alcaide queda por encima del gradiente: el rango no depende del orden."""
    data = await _get_with_fixed(async_client, _fixed_result(900.0, 400.0, 700.0, 667.0))
    assert data["description"] == (
        "Cota de nieve estimada entre 400 y 900 msnm (promedio 667 msnm)"
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_description_without_850_hpa_keeps_the_two_method_form(async_client: AsyncClient):
    data = await _get_with_fixed(async_client, _fixed_result(2797.0, 2935.0, None, 2866.0))
    assert data["description"] == (
        "Cota de nieve estimada entre 2797 y 2935 msnm (sin datos de nivel 850 hPa)"
    )


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize(
    ("temp_c", "temp_850", "elevation_m"),
    [
        (16.4, 5.0, 415.0),   # 850 hPa por debajo de los otros dos
        (10.0, 12.0, 750.0),  # 850 hPa por encima
        (10.0, 5.0, 750.0),   # 850 hPa en el medio
        (-8.0, -12.0, 1500.0),  # frío: Alcaide queda por encima del gradiente
        (2.0, -4.0, 0.0),
    ],
)
async def test_every_method_and_the_average_fall_inside_the_description_range(
    async_client: AsyncClient, temp_c: float, temp_850: float, elevation_m: float
):
    forecast = make_uniform_hourly(temp_c=temp_c, temp_850=temp_850, elevation_m=elevation_m)
    with patch(HOURLY, new_callable=AsyncMock, return_value=forecast), patch(
        "app.routers.tools.aggregate_current",
        new_callable=AsyncMock,
        return_value=_make_weather_response(temp_c=temp_c),
    ):
        response = await async_client.get(URL)

    assert response.status_code == 200
    data = response.json()
    match = RANGE_RE.search(data["description"])
    assert match is not None, data["description"]
    low, high, average_text = (int(g) for g in match.groups())
    assert low <= high
    for value in (data["alcaide_m"], data["gradiente_m"], data["m850_hpa_m"], data["average_m"]):
        assert low <= round(value) <= high, (value, data["description"])
    assert int(average_text) == round(data["average_m"])
