"""Tests para weather_aggregator — los 6 escenarios del árbol de decisión."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException

from app.services.smn import SmnObservation
from app.services.openmeteo import OpenMeteoCurrent
from app.services.weather_aggregator import aggregate_current


def _make_smn_obs(
    distance_km: float = 20.0,
    age_minutes: int = 30,
    temp_c: float | None = 22.0,
    humidity: float | None = 55.0,
) -> SmnObservation:
    observed_at = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
    return SmnObservation(
        station_name="CÓRDOBA AEROPUERTO",
        station_lat=-31.323,
        station_lon=-64.208,
        distance_km=distance_km,
        observed_at=observed_at,
        temp_c=temp_c,
        humidity=humidity,
        wind_speed_kmh=15.0,
        wind_dir_deg=270.0,
        pressure_hpa=1013.0,
        precip_1h_mm=None,
        description="Despejado",
    )


def _make_openmeteo() -> OpenMeteoCurrent:
    return OpenMeteoCurrent(
        temp_c=23.5,
        feels_like_c=22.1,
        humidity=52.0,
        wind_speed_kmh=18.0,
        wind_dir_deg=270.0,
        pressure_hpa=1014.2,
        precip_1h_mm=0.0,
        cloud_cover=10.0,
        weather_code=0,
        description=None,
        fetched_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Escenario 1 — SMN nearby & fresh
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_smn_nearby_fresh_uses_smn():
    smn_obs = _make_smn_obs(distance_km=20.0, age_minutes=30)

    with (
        patch("app.services.weather_aggregator.smn.get_nearest_observation", new_callable=AsyncMock, return_value=smn_obs),
        patch("app.services.weather_aggregator.openmeteo.get_current", new_callable=AsyncMock) as mock_om,
    ):
        result = await aggregate_current(-31.4, -64.2)

    assert result.meta.source == "smn"
    assert result.meta.reason == "smn_nearby_fresh"
    assert result.temp_c == pytest.approx(22.0)
    mock_om.assert_not_called()


# ---------------------------------------------------------------------------
# Escenario 2 — SMN too far
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_smn_too_far_uses_openmeteo():
    smn_obs = _make_smn_obs(distance_km=120.0)
    om = _make_openmeteo()

    with (
        patch("app.services.weather_aggregator.smn.get_nearest_observation", new_callable=AsyncMock, return_value=smn_obs),
        patch("app.services.weather_aggregator.openmeteo.get_current", new_callable=AsyncMock, return_value=om),
    ):
        result = await aggregate_current(-31.4, -64.2)

    assert result.meta.source == "openmeteo"
    assert result.meta.reason == "smn_too_far"


# ---------------------------------------------------------------------------
# Escenario 3 — SMN stale (obs hace 2 horas)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_smn_stale_uses_openmeteo():
    smn_obs = _make_smn_obs(distance_km=20.0, age_minutes=130)  # 2h10m
    om = _make_openmeteo()

    with (
        patch("app.services.weather_aggregator.smn.get_nearest_observation", new_callable=AsyncMock, return_value=smn_obs),
        patch("app.services.weather_aggregator.openmeteo.get_current", new_callable=AsyncMock, return_value=om),
    ):
        result = await aggregate_current(-31.4, -64.2)

    assert result.meta.source == "openmeteo"
    assert result.meta.reason == "smn_stale"


# ---------------------------------------------------------------------------
# Escenario 4 — SMN missing fields (sin temp)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_smn_missing_fields_uses_openmeteo():
    smn_obs = _make_smn_obs(distance_km=20.0, temp_c=None)
    om = _make_openmeteo()

    with (
        patch("app.services.weather_aggregator.smn.get_nearest_observation", new_callable=AsyncMock, return_value=smn_obs),
        patch("app.services.weather_aggregator.openmeteo.get_current", new_callable=AsyncMock, return_value=om),
    ):
        result = await aggregate_current(-31.4, -64.2)

    assert result.meta.source == "openmeteo"
    assert result.meta.reason == "smn_missing_fields"


# ---------------------------------------------------------------------------
# Escenario 5 — SMN unavailable (None)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_smn_unavailable_uses_openmeteo():
    om = _make_openmeteo()

    with (
        patch("app.services.weather_aggregator.smn.get_nearest_observation", new_callable=AsyncMock, return_value=None),
        patch("app.services.weather_aggregator.openmeteo.get_current", new_callable=AsyncMock, return_value=om),
    ):
        result = await aggregate_current(-31.4, -64.2)

    assert result.meta.source == "openmeteo"
    assert result.meta.reason == "smn_unavailable"


# ---------------------------------------------------------------------------
# Escenario 6 — Ambas fuentes caídas → 503
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_both_sources_down_raises_503():
    with (
        patch("app.services.weather_aggregator.smn.get_nearest_observation", new_callable=AsyncMock, return_value=None),
        patch("app.services.weather_aggregator.openmeteo.get_current", new_callable=AsyncMock, return_value=None),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await aggregate_current(-34.6, -58.4)

    assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# Cardinal helper
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_degrees_to_cardinal():
    from app.services.weather_aggregator import degrees_to_cardinal

    assert degrees_to_cardinal(0) == "N"
    assert degrees_to_cardinal(360) == "N"
    assert degrees_to_cardinal(45) == "NE"
    assert degrees_to_cardinal(90) == "E"
    assert degrees_to_cardinal(135) == "SE"
    assert degrees_to_cardinal(180) == "S"
    assert degrees_to_cardinal(225) == "SW"
    assert degrees_to_cardinal(270) == "W"
    assert degrees_to_cardinal(315) == "NW"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_wind_dir_cardinal_is_set_in_response():
    smn_obs = _make_smn_obs(distance_km=20.0)  # wind_dir_deg=270 → W

    with (
        patch("app.services.weather_aggregator.smn.get_nearest_observation", new_callable=AsyncMock, return_value=smn_obs),
        patch("app.services.weather_aggregator.openmeteo.get_current", new_callable=AsyncMock),
    ):
        result = await aggregate_current(-31.4, -64.2)

    assert result.wind_dir_cardinal == "W"


# ---------------------------------------------------------------------------
# Guards de valores cero (0.0 es válido, no falsy)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_smn_temp_zero_is_valid():
    """temp_c=0.0 es una temperatura válida — debe usar SMN, no Open-Meteo."""
    smn_obs = _make_smn_obs(distance_km=20.0, age_minutes=30, temp_c=0.0, humidity=50.0)

    with (
        patch("app.services.weather_aggregator.smn.get_nearest_observation", new_callable=AsyncMock, return_value=smn_obs),
        patch("app.services.weather_aggregator.openmeteo.get_current", new_callable=AsyncMock) as mock_om,
    ):
        result = await aggregate_current(-31.4, -64.2)

    assert result.meta.source == "smn"
    assert result.temp_c == pytest.approx(0.0)
    mock_om.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_smn_humidity_zero_is_valid():
    """humidity=0.0 es válida — no debe forzar fallback a Open-Meteo."""
    smn_obs = _make_smn_obs(distance_km=20.0, age_minutes=30, temp_c=15.0, humidity=0.0)

    with (
        patch("app.services.weather_aggregator.smn.get_nearest_observation", new_callable=AsyncMock, return_value=smn_obs),
        patch("app.services.weather_aggregator.openmeteo.get_current", new_callable=AsyncMock) as mock_om,
    ):
        result = await aggregate_current(-31.4, -64.2)

    assert result.meta.source == "smn"
    mock_om.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_smn_distance_exactly_80_uses_smn():
    """distance_km=80.0 exacto es el umbral inclusivo — debe usar SMN."""
    smn_obs = _make_smn_obs(distance_km=80.0, age_minutes=30)

    with (
        patch("app.services.weather_aggregator.smn.get_nearest_observation", new_callable=AsyncMock, return_value=smn_obs),
        patch("app.services.weather_aggregator.openmeteo.get_current", new_callable=AsyncMock) as mock_om,
    ):
        result = await aggregate_current(-31.4, -64.2)

    assert result.meta.source == "smn"
    mock_om.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_smn_age_exactly_90_uses_smn():
    """Observación < 90 min es el umbral inclusivo — debe usar SMN (89 min para evitar race timing)."""
    smn_obs = _make_smn_obs(distance_km=20.0, age_minutes=89)

    with (
        patch("app.services.weather_aggregator.smn.get_nearest_observation", new_callable=AsyncMock, return_value=smn_obs),
        patch("app.services.weather_aggregator.openmeteo.get_current", new_callable=AsyncMock) as mock_om,
    ):
        result = await aggregate_current(-31.4, -64.2)

    assert result.meta.source == "smn"
    mock_om.assert_not_called()
