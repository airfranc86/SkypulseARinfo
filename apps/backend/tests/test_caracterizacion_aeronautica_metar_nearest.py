"""Characterization of GET /api/metar/nearest: a pure lookup over the local Argentine airport list.

No CheckWX, AWC or Open-Meteo request is involved, so nothing is mocked. The expected JSON bodies are
literal values taken from the real output of the route (distance rounded to 0.1 km).
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.helpers_caracterizacion_aeronautica import reset_aeronautical_state

pytestmark = pytest.mark.integration

URL = "/api/metar/nearest"


@pytest.fixture(autouse=True)
def _clean_state():
    reset_aeronautical_state()
    yield
    reset_aeronautical_state()


@pytest.mark.parametrize(
    ("lat", "lon", "expected"),
    [
        # Cordoba city
        (-31.42, -64.18, {"icao": "SACO", "name": "Córdoba", "lat": -31.323, "lon": -64.208, "distance_km": 11.1}),
        # Obelisco, Buenos Aires: Aeroparque, not Ezeiza
        (-34.6037, -58.3816, {"icao": "SABE", "name": "Aeroparque", "lat": -34.559, "lon": -58.416, "distance_km": 5.9}),
        # Moreno (Gran Buenos Aires): Ezeiza at 30 km
        (-34.6506, -58.7916, {"icao": "SAEZ", "name": "Ezeiza", "lat": -34.822, "lon": -58.536, "distance_km": 30.1}),
        # Ushuaia
        (-54.8019, -68.303, {"icao": "SAWH", "name": "Ushuaia", "lat": -54.843, "lon": -68.295, "distance_km": 4.6}),
        # Rosario
        (-32.95, -60.65, {"icao": "SAAR", "name": "Rosario", "lat": -32.919, "lon": -60.785, "distance_km": 13.1}),
        # Mendoza
        (-32.89, -68.84, {"icao": "SAME", "name": "Mendoza", "lat": -32.832, "lon": -68.793, "distance_km": 7.8}),
        # San Miguel de Tucuman
        (-26.83, -65.2, {"icao": "SANT", "name": "Tucumán", "lat": -26.841, "lon": -65.105, "distance_km": 9.5}),
        # Mar del Plata
        (-38.0, -57.55, {"icao": "SAZM", "name": "Mar del Plata", "lat": -37.934, "lon": -57.573, "distance_km": 7.6}),
        # Rio Gallegos region, 64 km away
        (-52.0, -70.0, {"icao": "SAWG", "name": "Río Gallegos", "lat": -51.609, "lon": -69.313, "distance_km": 64.2}),
        # Exactly on an airport: distance 0.0
        (-34.822, -58.536, {"icao": "SAEZ", "name": "Ezeiza", "lat": -34.822, "lon": -58.536, "distance_km": 0.0}),
    ],
)
async def test_nearest_airport_of_argentine_cities(async_client: AsyncClient, lat, lon, expected) -> None:
    response = await async_client.get(URL, params={"lat": lat, "lon": lon})

    assert response.status_code == 200
    assert response.json() == expected


@pytest.mark.parametrize(
    ("lat", "lon", "expected"),
    [
        # La Quiaca (Jujuy): the nearest airport of the list is Salta, 307 km away
        (-22.1, -65.6, {"icao": "SASA", "name": "Salta", "lat": -24.856, "lon": -65.486, "distance_km": 306.7}),
        # Posadas (Misiones): Concordia, 482 km away. There is no distance limit on this route
        (-27.37, -55.9, {"icao": "SAAC", "name": "Concordia", "lat": -31.297, "lon": -57.997, "distance_km": 481.6}),
        # North-east of Argentina, 1146 km from the nearest airport of the list
        (-22.0, -53.0, {"icao": "SAAC", "name": "Concordia", "lat": -31.297, "lon": -57.997, "distance_km": 1146.4}),
    ],
)
async def test_far_away_points_still_get_the_nearest_airport_with_its_distance(
    async_client: AsyncClient, lat, lon, expected
) -> None:
    response = await async_client.get(URL, params={"lat": lat, "lon": lon})

    assert response.status_code == 200
    assert response.json() == expected


@pytest.mark.parametrize("params", [{"lat": 10.0, "lon": -64.0}, {"lat": -31.0, "lon": 20.0}, {"lat": -31.0}, {}])
async def test_out_of_range_or_missing_coordinates_are_422(async_client: AsyncClient, params) -> None:
    response = await async_client.get(URL, params=params)

    assert response.status_code == 422
