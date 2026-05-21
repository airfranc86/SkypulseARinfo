"""Fixtures comunes para toda la suite."""
from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app


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
# Limpiar el cache de SMN entre tests para garantizar aislamiento
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_smn_cache():
    """Limpia el TTLCache global de SMN antes de cada test."""
    import app.services.smn as smn_module
    smn_module._station_cache.clear()
    yield
    smn_module._station_cache.clear()


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

    También limpia el cache crudo de Windy entre tests.
    """
    import app.core.config as cfg
    import app.services.windy as windy_module

    monkeypatch.setattr(cfg.settings, "windy_api_key", "", raising=False)
    windy_module._raw_cache.clear()
    yield
    windy_module._raw_cache.clear()


# ---------------------------------------------------------------------------
# Cliente async para el router FastAPI (httpx >= 0.23 usa ASGITransport)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
