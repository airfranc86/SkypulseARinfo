"""Tests mínimos para app.services.metar (cliente AWC/NOAA, sin cuota).

No existía un archivo de test dedicado para este servicio (solo el router
CheckWX en test_metar_router.py, que es una fuente DISTINTA — ver docstring de
app/services/metar.py). Se crea este archivo únicamente para cubrir la Parte A4
del plan de instrumentación mínima: usage_counter.record('metar_awc') en los
puntos reales de fetch a AviationWeather/NOAA.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
import respx

import app.services.metar as metar_module
from app.services.metar import get_metar_visibility, get_taf_for_icao


@pytest.fixture(autouse=True)
def clear_metar_caches():
    metar_module._metar_cache.clear()
    metar_module._taf_cache.clear()
    yield
    metar_module._metar_cache.clear()
    metar_module._taf_cache.clear()


@pytest.mark.asyncio
async def test_get_metar_visibility_records_usage(monkeypatch):
    mock_record = MagicMock()
    monkeypatch.setattr(metar_module.usage_counter, "record", mock_record)

    payload = [{"icao": "SAEZ", "visib": "6", "obsTime": 1705320000}]
    with respx.mock:
        respx.get(metar_module.AWC_METAR_BASE).mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = await get_metar_visibility("SAEZ")

    assert result is not None
    mock_record.assert_called_once_with("metar_awc")


@pytest.mark.asyncio
async def test_get_taf_for_icao_records_usage(monkeypatch):
    mock_record = MagicMock()
    monkeypatch.setattr(metar_module.usage_counter, "record", mock_record)

    payload = [
        {
            "icao": "SAEZ",
            "fcsts": [{"timeFrom": 0, "timeTo": 9999999999, "visib": "6"}],
        }
    ]
    with respx.mock:
        respx.get(metar_module.AWC_TAF_BASE).mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = await get_taf_for_icao("SAEZ")

    assert result is not None
    mock_record.assert_called_once_with("metar_awc")
