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
    """Limpia el TTLCache global de SMN antes de cada test."""
    import app.services.smn as smn_module
    smn_module._station_cache.clear()
    yield
    smn_module._station_cache.clear()


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


# ---------------------------------------------------------------------------
# Forzar Windy desactivado por defecto en tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def disable_windy_by_default(monkeypatch):
    """
    Garantiza que `settings.windy_api_key` está vacío durante los tests, salvo
    que un test lo sobreescriba explícitamente. Esto asegura que los endpoints
    que intentan Windy primero caigan determinísticamente al fallback Open-Meteo
    (que es donde apuntan los mocks existentes).

    También limpia el cache crudo de Windy y fire_danger entre tests.
    """
    import app.core.config as cfg
    import app.services.windy as windy_module
    import app.services.fire_danger as fire_module

    monkeypatch.setattr(cfg.settings, "windy_api_key", "", raising=False)
    windy_module._raw_cache.clear()
    fire_module._fire_raw_cache.clear()

    import app.services.emsc as emsc_module
    emsc_module._event_cache.clear()

    yield
    windy_module._raw_cache.clear()
    fire_module._fire_raw_cache.clear()
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
