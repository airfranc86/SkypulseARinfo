"""El 422 de un ICAO inválido no habla de coordenadas (FRA-367, PR B).

`/api/metar` y `/api/taf` reciben `icao`, no lat/lon; el handler global les devolvía «Coordenadas
inválidas». `/api/metar/nearest` sí recibe lat/lon y conserva sus mensajes de coordenadas.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "path",
    [
        "/api/taf?icao=SAC",  # demasiado corto
        "/api/taf?icao=SACOX",  # demasiado largo
        "/api/taf",  # falta el parámetro
        "/api/metar?icao=SAC",
        "/api/metar?icao=SACOX",
        "/api/metar",
        "/api/metar?icao=SACO&type=xyz",  # `type` solo admite metar o taf
    ],
)
async def test_an_invalid_icao_request_says_invalid_parameters_not_coordinates(
    async_client: AsyncClient, path: str
) -> None:
    response = await async_client.get(path)
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "invalid_request"
    assert body["message"] == "Parámetros inválidos"
    assert "oordenadas" not in response.text


async def test_the_422_does_not_echo_the_value_that_was_sent(async_client: AsyncClient) -> None:
    response = await async_client.get("/api/taf?icao=SECRETO")
    assert response.status_code == 422
    assert "SECRETO" not in response.text
    assert response.json()["detail"]["errors"] == [{"loc": ["query", "icao"], "type": "string_too_long"}]


async def test_nearest_airport_keeps_its_coordinate_messages(async_client: AsyncClient) -> None:
    not_a_number = await async_client.get("/api/metar/nearest?lat=abc&lon=-64.2")
    assert not_a_number.status_code == 422
    assert not_a_number.json()["error"] == "invalid_coordinates"
    out_of_range = await async_client.get("/api/metar/nearest?lat=89&lon=-64.2")
    assert out_of_range.status_code == 422
    assert out_of_range.json()["error"] == "outside_argentina"


async def test_other_routes_keep_the_coordinate_message(async_client: AsyncClient) -> None:
    response = await async_client.get("/api/niebla?lat=abc&lon=-64.2")
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_coordinates"
