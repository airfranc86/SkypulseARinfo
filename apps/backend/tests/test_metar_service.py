"""Tests mínimos para app.services.reportes_aeronauticos (METAR/TAF de AWC/NOAA, sin cuota).

No existía un archivo de test dedicado para este servicio (solo el router
CheckWX en test_metar_router.py, que es una fuente DISTINTA — ver docstring de
app/services/reportes_aeronauticos). Se crea este archivo únicamente para cubrir la Parte A4
del plan de instrumentación mínima: usage_counter.record('metar_awc') en los
puntos reales de fetch a AviationWeather/NOAA.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import httpx
import pytest
import respx

import app.services.reportes_aeronauticos.metar as metar_module
import app.services.reportes_aeronauticos.taf as taf_module
from app.services.reportes_aeronauticos import awc, get_metar_visibility, get_taf_for_icao
from app.services.reportes_aeronauticos.awc import AWC_METAR_BASE, AWC_TAF_BASE


@pytest.fixture(autouse=True)
def clear_metar_caches():
    metar_module._metar_cache.clear()
    taf_module._taf_cache.clear()
    yield
    metar_module._metar_cache.clear()
    taf_module._taf_cache.clear()


@pytest.mark.asyncio
async def test_get_metar_visibility_records_usage(monkeypatch):
    mock_record = MagicMock()
    monkeypatch.setattr(awc.usage_counter, "record", mock_record)

    payload = [{"icao": "SAEZ", "visib": "6", "obsTime": int(time.time()) - 600}]
    with respx.mock:
        respx.get(AWC_METAR_BASE).mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = await get_metar_visibility("SAEZ")

    assert result is not None
    mock_record.assert_called_once_with("metar_awc")


@pytest.mark.asyncio
async def test_get_taf_for_icao_records_usage(monkeypatch):
    mock_record = MagicMock()
    monkeypatch.setattr(awc.usage_counter, "record", mock_record)

    payload = [
        {
            "icao": "SAEZ",
            "fcsts": [{"timeFrom": 0, "timeTo": 9999999999, "visib": "6"}],
        }
    ]
    with respx.mock:
        respx.get(AWC_TAF_BASE).mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = await get_taf_for_icao("SAEZ")

    assert result is not None
    mock_record.assert_called_once_with("metar_awc")
