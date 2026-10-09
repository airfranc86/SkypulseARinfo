"""FRA-331: `get_metar_visibility` entiende el `visib` de AWC con CAVOK ("6+", "P6SM").

AWC devuelve el string "6+" cuando el METAR trae CAVOK (visto en SAEZ y SAAR). Antes el
`float()` fallaba y el METAR se descartaba justo cuando hay buena visibilidad. Una visibilidad
de 6 o más millas vale el tope de 10 km, no 6 SM = 9.656 m: la clasificación de niebla separa
"Despejada" (>= 10 km) de "Buena" (>= 5 km).
"""
from __future__ import annotations

import time

import httpx
import pytest
import respx

import app.services.reportes_aeronauticos.metar as metar_module
from app.services.reportes_aeronauticos.awc import AWC_METAR_BASE
from app.services.reportes_aeronauticos.metar import get_metar_visibility


@pytest.fixture(autouse=True)
def clear_metar_caches():
    metar_module._metar_cache.clear()
    yield
    metar_module._metar_cache.clear()


def _fresh_obs_time() -> int:
    """Hora de observación de hace 10 min: `get_metar_visibility` descarta los METAR de más de 90 min."""
    return int(time.time()) - 600


async def _visibility_for(entry: dict, icao: str = "SAEZ") -> float | None:
    with respx.mock:
        respx.get(AWC_METAR_BASE).mock(
            return_value=httpx.Response(200, json=[{"icao": icao, "obsTime": _fresh_obs_time(), **entry}])
        )
        return await get_metar_visibility(icao)


@pytest.mark.asyncio
@pytest.mark.parametrize("visib", ["6+", "P6SM", "10", 10, 10.0])
async def test_cavok_and_cap_values_are_ten_km(visib):
    assert await _visibility_for({"visib": visib}) == 10_000.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("visib", "expected_m"),
    [
        ("6", 9_656.064),
        (6, 9_656.064),
        ("3", 4_828.032),
        ("1/2", 804.672),
        ("1 1/2", 2_414.016),
        ("0", 0.0),
    ],
)
async def test_numeric_and_fractional_values_convert_to_meters(visib, expected_m):
    assert await _visibility_for({"visib": visib}) == pytest.approx(expected_m, abs=0.5)


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", [{}, {"visib": None}, {"visib": "abc"}, {"visib": ""}, {"visib": "1/0"}])
async def test_missing_or_garbage_visib_is_none(entry):
    assert await _visibility_for(entry) is None
    assert "SAEZ" not in metar_module._metar_cache


@pytest.mark.asyncio
async def test_empty_list_is_none():
    with respx.mock:
        respx.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=[]))
        assert await get_metar_visibility("SAEZ") is None


@pytest.mark.asyncio
async def test_http_error_is_none_and_not_cached():
    with respx.mock:
        respx.get(AWC_METAR_BASE).mock(return_value=httpx.Response(500))
        assert await get_metar_visibility("SAEZ") is None
    assert "SAEZ" not in metar_module._metar_cache


@pytest.mark.asyncio
async def test_cavok_value_is_cached_second_call_makes_no_request():
    with respx.mock:
        route = respx.get(AWC_METAR_BASE).mock(
            return_value=httpx.Response(200, json=[{"icao": "SAAR", "visib": "6+", "obsTime": _fresh_obs_time()}])
        )
        first = await get_metar_visibility("SAAR")
        second = await get_metar_visibility("SAAR")

    assert first == second == 10_000.0
    assert route.call_count == 1
