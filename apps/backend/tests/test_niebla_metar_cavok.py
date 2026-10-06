"""FRA-331: con un METAR CAVOK ("visib": "6+") /api/niebla usa el METAR y no cae a Open-Meteo."""
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from httpx import AsyncClient

import app.services.metar as metar_module
from app.core.rate_limit import limiter
from app.services.openmeteo import VisibilityData

ROSARIO = (-32.95, -60.65)  # SAAR ~13 km


@pytest.fixture(autouse=True)
def fresh_state():
    """/api/niebla permite 30 req/min con un limiter compartido por toda la sesión."""
    limiter.reset()
    metar_module._metar_cache.clear()
    yield
    limiter.reset()
    metar_module._metar_cache.clear()


@pytest.fixture(autouse=True)
def stub_other_sources(monkeypatch):
    """Open-Meteo "ahora" distinguible del METAR (3 km → "Reducida"); TAF e inferencia apagados."""
    open_meteo = VisibilityData(
        current_m=3_000.0,
        weather_code=1,
        fog_level=2,
        fog_label="Reducida",
        fog_color="#c8a84b",
        hourly_m=[3_000.0] * 12,
        hourly_labels=[f"{h:02d}:00" for h in range(12)],
    )
    monkeypatch.setattr("app.routers.niebla.get_visibility_forecast", AsyncMock(return_value=open_meteo))
    monkeypatch.setattr("app.routers.niebla.get_nearest_taf_hourly", AsyncMock(return_value=None))
    monkeypatch.setattr("app.routers.niebla.get_fog_inference_forecast", AsyncMock(return_value=None))


@pytest.mark.asyncio
async def test_cavok_metar_is_used_and_does_not_fall_back_to_open_meteo(async_client: AsyncClient):
    with respx.mock:
        respx.get(metar_module.AWC_METAR_BASE).mock(
            return_value=httpx.Response(200, json=[{"icao": "SAAR", "visib": "6+", "obsTime": 1705320000}])
        )
        resp = await async_client.get("/api/niebla", params={"lat": ROSARIO[0], "lon": ROSARIO[1]})

    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "metar"
    assert body["metar_station"] == "SAAR"
    assert body["visibility_m"] == 10_000.0
    assert body["fog_label"] == "Despejada"


@pytest.mark.asyncio
async def test_unparseable_metar_still_falls_back_to_open_meteo(async_client: AsyncClient):
    with respx.mock:
        respx.get(metar_module.AWC_METAR_BASE).mock(
            return_value=httpx.Response(200, json=[{"icao": "SAAR", "visib": "abc"}])
        )
        resp = await async_client.get("/api/niebla", params={"lat": ROSARIO[0], "lon": ROSARIO[1]})

    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "openmeteo"
    assert body["metar_station"] == "SAAR"
    assert body["visibility_m"] == 3_000.0
