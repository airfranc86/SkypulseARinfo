"""Tests para el cliente SMN — haversine, fetch, cache."""
from __future__ import annotations

import pytest
import pytest_asyncio
import respx
import httpx
from unittest.mock import patch
from datetime import datetime, timezone

from app.services.smn import get_nearest_observation, haversine
from tests.conftest import SMN_SAMPLE_PAYLOAD


# ---------------------------------------------------------------------------
# haversine
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_haversine_buenos_aires_to_cordoba():
    """Buenos Aires (-34.6, -58.4) → Córdoba (-31.4, -64.2) ≈ 640 km."""
    dist = haversine(-34.6037, -58.3816, -31.4135, -64.1810)
    assert 620 < dist < 660, f"Expected ~640 km, got {dist:.1f}"


@pytest.mark.unit
def test_haversine_same_point_is_zero():
    dist = haversine(-34.6, -58.4, -34.6, -58.4)
    assert dist == pytest.approx(0.0, abs=0.01)


@pytest.mark.unit
def test_haversine_symmetric():
    d1 = haversine(-34.6, -58.4, -31.4, -64.2)
    d2 = haversine(-31.4, -64.2, -34.6, -58.4)
    assert d1 == pytest.approx(d2, rel=1e-6)


# ---------------------------------------------------------------------------
# get_nearest_observation — éxito
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_nearest_observation_returns_closest_station():
    """Debe retornar la estación más cercana a Córdoba."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://ws.smn.gob.ar/map_items/weather").mock(
            return_value=httpx.Response(200, json=SMN_SAMPLE_PAYLOAD)
        )
        obs = await get_nearest_observation(-31.4, -64.2)

    assert obs is not None
    assert obs.station_name == "CÓRDOBA AEROPUERTO"
    assert obs.temp_c == pytest.approx(22.0)
    assert obs.humidity == pytest.approx(55.0)
    assert obs.wind_speed_kmh == pytest.approx(15.0)
    assert obs.wind_dir_deg == pytest.approx(270.0)
    assert obs.pressure_hpa == pytest.approx(1013.0)
    assert obs.distance_km < 50  # aeropuerto CBA está muy cerca


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_nearest_observation_parses_observed_at_as_utc():
    """El campo 'date' de SMN (UTC-3) debe convertirse a UTC."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://ws.smn.gob.ar/map_items/weather").mock(
            return_value=httpx.Response(200, json=SMN_SAMPLE_PAYLOAD)
        )
        obs = await get_nearest_observation(-31.4, -64.2)

    assert obs is not None
    # UTC-3 → UTC: 14:00 local = 17:00 UTC
    assert obs.observed_at.tzinfo is not None
    assert obs.observed_at.hour == 17


# ---------------------------------------------------------------------------
# get_nearest_observation — errores
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_nearest_observation_returns_none_on_timeout():
    with respx.mock() as mock:
        mock.get("https://ws.smn.gob.ar/map_items/weather").mock(
            side_effect=httpx.TimeoutException("timeout")
        )
        obs = await get_nearest_observation(-34.6, -58.4)

    assert obs is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_nearest_observation_returns_none_on_5xx():
    with respx.mock() as mock:
        mock.get("https://ws.smn.gob.ar/map_items/weather").mock(
            return_value=httpx.Response(503)
        )
        obs = await get_nearest_observation(-34.6, -58.4)

    assert obs is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_nearest_observation_returns_none_on_invalid_json():
    with respx.mock() as mock:
        mock.get("https://ws.smn.gob.ar/map_items/weather").mock(
            return_value=httpx.Response(200, text="not json {{")
        )
        obs = await get_nearest_observation(-34.6, -58.4)

    assert obs is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_nearest_observation_returns_none_on_empty_array():
    with respx.mock() as mock:
        mock.get("https://ws.smn.gob.ar/map_items/weather").mock(
            return_value=httpx.Response(200, json=[])
        )
        obs = await get_nearest_observation(-34.6, -58.4)

    assert obs is None


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_smn_cache_works_within_ttl():
    """Segunda llamada NO debe hacer HTTP — la lista ya está cacheada."""
    import app.services.smn as smn_module

    call_count = 0

    async def fake_fetch(url: str) -> list:
        nonlocal call_count
        call_count += 1
        return SMN_SAMPLE_PAYLOAD

    with patch.object(smn_module, "_fetch_stations", side_effect=fake_fetch):
        obs1 = await get_nearest_observation(-31.4, -64.2)
        obs2 = await get_nearest_observation(-31.4, -64.2)

    assert obs1 is not None
    assert obs2 is not None
    assert call_count == 1, f"Expected 1 HTTP call, got {call_count}"


# ---------------------------------------------------------------------------
# Tests adicionales BLOQUE F
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_parse_observed_at_converts_argentina_local_to_utc():
    """'2024-01-15 14:00' (UTC-3 local) → datetime UTC con hour=17."""
    from app.services.smn import _parse_observed_at

    result = _parse_observed_at("2024-01-15 14:00")
    assert result.tzinfo is not None
    assert result.hour == 17
    assert result.minute == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_all_stations_have_invalid_lat_lon_returns_none():
    """Si todas las estaciones tienen lat/lon inválidos → retorna None."""
    bad_payload = [
        {"name": "BAD1", "lat": "", "lon": "", "temp": "20", "humidity": "50", "date": "2024-01-15 14:00"},
        {"name": "BAD2", "lat": None, "lon": None, "temp": "21", "humidity": "55", "date": "2024-01-15 14:00"},
    ]
    with patch("app.services.smn._fetch_stations", return_value=bad_payload):
        obs = await get_nearest_observation(-31.4, -64.2)

    assert obs is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_smn_uses_pres_when_pressure_missing():
    """Si la estación tiene 'pres' pero no 'pressure', debe usar 'pres'."""
    payload = [
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
                "pres": "1015",   # usa 'pres', sin 'pressure'
                "description": "Despejado",
            },
        }
    ]
    with patch("app.services.smn._fetch_stations", return_value=payload):
        obs = await get_nearest_observation(-31.4, -64.2)

    assert obs is not None
    assert obs.pressure_hpa == pytest.approx(1015.0)
