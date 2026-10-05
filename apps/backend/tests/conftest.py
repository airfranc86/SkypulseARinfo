"""Fixtures comunes para toda la suite."""
from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
import respx
from httpx import AsyncClient, ASGITransport

from app.main import app
import app.core.http_client as _http_client_module


# ---------------------------------------------------------------------------
# Payloads de ejemplo — basados en la estructura real de cada API
# ---------------------------------------------------------------------------

# Estructura real de la API SMN: campos meteo bajo la clave "weather".
# "date" se mantiene en raíz para el test de parseo UTC (legacy field).
SMN_SAMPLE_PAYLOAD = [
    {
        "name": "CÓRDOBA AEROPUERTO",
        "lat": -31.323,
        "lon": -64.208,
        "date": "2024-01-15 14:00",
        "weather": {
            "temp": "22",
            "humidity": "55",
            "wind_speed": "15",
            "wind_deg": "270",
            "pressure": "1013",
            "description": "Despejado",
        },
    },
    {
        "name": "VILLA MARÍA",
        "lat": -32.407,
        "lon": -63.243,
        "date": "2024-01-15 14:00",
        "weather": {
            "temp": "21",
            "humidity": "60",
            "wind_speed": "10",
            "wind_deg": "180",
            "pressure": "1012",
            "description": "Parcialmente nublado",
        },
    },
    {
        "name": "SANTIAGO DEL ESTERO",
        "lat": -27.783,
        "lon": -64.267,
        "date": "2024-01-15 14:00",
        "weather": {
            "temp": "30",
            "humidity": "40",
            "wind_speed": "8",
            "wind_deg": "90",
            "pressure": "1008",
            "description": "Soleado",
        },
    },
]

OPENMETEO_SAMPLE_PAYLOAD = {
    "latitude": -31.4,
    "longitude": -64.2,
    "timezone": "America/Argentina/Buenos_Aires",
    "current": {
        "time": "2024-01-15T14:00",
        "temperature_2m": 23.5,
        "relative_humidity_2m": 52,
        "apparent_temperature": 22.1,
        "surface_pressure": 1014.2,
        "wind_speed_10m": 18.0,
        "wind_direction_10m": 270,
        "precipitation": 0.0,
        "cloud_cover": 10,
        "weather_code": 0,
    },
    "current_units": {
        "temperature_2m": "°C",
        "wind_speed_unit": "km/h",
    },
}


# ---------------------------------------------------------------------------
# Limpiar caches entre tests para garantizar aislamiento
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_smn_cache():
    """Limpia el TTLCache global de SMN y su caché negativo de fallos antes de cada test."""
    import app.services.smn as smn_module
    smn_module._station_cache.clear()
    smn_module._failure_backoff_until = 0.0
    yield
    smn_module._station_cache.clear()
    smn_module._failure_backoff_until = 0.0


@pytest.fixture
def smn_enabled(monkeypatch):
    """Enciende `settings.smn_enabled` (apagado por defecto desde FRA-319) para tests del camino SMN."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "smn_enabled", True)


@pytest.fixture(autouse=True)
def clear_openmeteo_caches():
    """Limpia los tres buckets de caché de Open-Meteo antes y después de cada test."""
    import app.services.openmeteo as om_module
    om_module._CACHE_CURRENT.clear()
    om_module._CACHE_FORECAST.clear()
    om_module._CACHE_NOWCAST.clear()
    yield
    om_module._CACHE_CURRENT.clear()
    om_module._CACHE_FORECAST.clear()
    om_module._CACHE_NOWCAST.clear()


@pytest.fixture(autouse=True)
def clear_metar_observation_cache():
    """Limpia la caché del METAR del "ahora" del dashboard (FRA-320) antes y después de cada test."""
    import app.services.metar_observation as metar_obs_module
    metar_obs_module._CACHE.clear()
    yield
    metar_obs_module._CACHE.clear()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live_current_observation: el dashboard pide de verdad el METAR (respx) y el Open-Meteo "
        "current en vez de los dobles por defecto",
    )


@pytest.fixture(autouse=True)
def stub_dashboard_current_observation(request: pytest.FixtureRequest, monkeypatch):
    """Dobles por defecto para las dos llamadas nuevas del dashboard (FRA-320).

    Los tests del dashboard parchean `aggregate_current` y el pronóstico, pero no sabían de la
    observación METAR ni de la ráfaga de Open-Meteo `current`: sin este doble saldrían a la red de
    verdad. Los tests marcados `live_current_observation` los ejercitan (con respx o parches propios).
    """
    if request.node.get_closest_marker("live_current_observation") is not None:
        return
    from unittest.mock import AsyncMock

    from app.services.metar_observation import MetarSelection

    unavailable = MetarSelection(
        reason="metar_unavailable", icao="", name="", distance_km=0.0, observation=None
    )
    monkeypatch.setattr(
        "app.routers.weather.get_nearest_metar_observation",
        AsyncMock(return_value=unavailable),
    )
    monkeypatch.setattr("app.routers.weather.get_openmeteo_current", AsyncMock(return_value=None))


# ---------------------------------------------------------------------------
# Caché de EMSC entre tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_emsc_cache():
    """Limpia el TTLCache de EMSC antes y después de cada test."""
    import app.services.emsc as emsc_module
    emsc_module._event_cache.clear()
    yield
    emsc_module._event_cache.clear()


# ---------------------------------------------------------------------------
# Cliente async para el router FastAPI (httpx >= 0.23 usa ASGITransport)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# Singleton httpx client — inicializado para tests que usan get_client()
# directamente (ej. test_openmeteo.py). respx.mock() intercepta el transport
# del cliente, por lo que necesitamos que el singleton use MockTransport.
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(autouse=True)
async def init_shared_http_client():
    """Inicializa el singleton httpx para tests que llaman get_client() directamente.

    respx.mock() intercepta a nivel de MockRouter global — el singleton necesita
    ser un AsyncClient normal; respx lo intercepta automáticamente cuando está
    activo como context manager durante el test.
    """
    client = AsyncClient()
    _http_client_module._client = client
    yield
    await client.aclose()
    _http_client_module._client = None
