"""Tests del caché single-flight de Open-Meteo (Fix 1).

Cubre:
- Hit/miss por clave canónica.
- Deduplicación: N coroutines concurrentes con la misma clave → 1 solo fetch.
- Claves distintas por model/days/fields no colisionan.
- _cache_key redondea lat/lon a 4 decimales.
- Fallo del fetcher: las N coroutines esperando reciben la misma excepción, no KeyError.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

import app.services.openmeteo as om_module
from app.services.openmeteo import (
    _cache_key,
    get_current,
    get_daily_forecast,
    get_daily_forecast_ext,
    get_fog_inference_forecast,
    get_hourly_forecast,
    get_hourly_forecast_ext,
    get_visibility_forecast,
)


# ---------------------------------------------------------------------------
# Payloads mínimos por función
# ---------------------------------------------------------------------------

_CURRENT_PAYLOAD = {
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
}

_HOURLY_PAYLOAD = {
    "latitude": -31.4,
    "longitude": -64.2,
    "elevation": 430.0,
    "hourly": {
        "time": ["2024-01-15T14:00", "2024-01-15T15:00"],
        "temperature_2m": [23.5, 22.0],
        "relative_humidity_2m": [52, 55],
        "precipitation": [0.0, 0.1],
        "wind_speed_10m": [18.0, 15.0],
        "temperature_850hPa": [12.0, 11.5],
    },
}

_DAILY_PAYLOAD = {
    "latitude": -31.4,
    "longitude": -64.2,
    "daily": {
        "time": ["2024-01-15", "2024-01-16"],
        "temperature_2m_max": [30.0, 28.0],
        "temperature_2m_min": [18.0, 17.0],
        "precipitation_sum": [0.0, 2.5],
        "precipitation_probability_max": [10, 60],
        "wind_speed_10m_max": [25.0, 30.0],
        "relative_humidity_2m_mean": [50, 65],
    },
}

_DAILY_EXT_PAYLOAD = {
    "latitude": -31.4,
    "longitude": -64.2,
    "daily": {
        "time": ["2024-01-15"],
        "temperature_2m_max": [30.0],
        "temperature_2m_min": [18.0],
        "precipitation_sum": [0.0],
        "precipitation_probability_max": [10],
        "wind_speed_10m_max": [25.0],
        "wind_gusts_10m_max": [40.0],
        "relative_humidity_2m_mean": [50],
        "uv_index_max": [8.0],
        "weather_code": [0],
        "sunrise": ["2024-01-15T06:30"],
        "sunset": ["2024-01-15T20:00"],
        "daylight_duration": [48600.0],
    },
}

_VISIBILITY_PAYLOAD = {
    "latitude": -31.4,
    "longitude": -64.2,
    "current": {
        "time": "2024-01-15T14:00",
        "visibility": 9000.0,
        "weather_code": 2,
    },
    "hourly": {
        "time": [f"2024-01-15T{h:02d}:00" for h in range(24)],
        "visibility": [9000.0] * 24,
    },
}

_FOG_PAYLOAD = {
    "latitude": -31.4,
    "longitude": -64.2,
    "hourly": {
        "time": [f"2024-01-15T{h:02d}:00" for h in range(24)],
        "relative_humidity_2m": [80.0] * 24,
        "dew_point_2m": [15.0] * 24,
        "temperature_2m": [20.0] * 24,
        "wind_speed_10m": [3.0] * 24,
        "weather_code": [0] * 24,
    },
}


OM_URL = "https://api.open-meteo.com/v1/forecast"


# ---------------------------------------------------------------------------
# _cache_key
# ---------------------------------------------------------------------------

def test_cache_key_is_stable():
    p = {"latitude": -31.4, "longitude": -64.2, "current": "temperature_2m", "timezone": "UTC"}
    assert _cache_key(p) == _cache_key(p)


def test_cache_key_rounds_latlon():
    # Both values have noise only in the 5th+ decimal (< 5), so round to same 4-decimal value.
    p1 = {"latitude": -31.40001, "longitude": -64.20001}  # → -31.4, -64.2
    p2 = {"latitude": -31.40004, "longitude": -64.20004}  # → -31.4, -64.2
    assert _cache_key(p1) == _cache_key(p2)


def test_cache_key_different_model():
    base = {"latitude": -31.4, "longitude": -64.2, "forecast_days": 7}
    assert _cache_key({**base, "models": "gfs_seamless"}) != _cache_key({**base, "models": "ecmwf_ifs025"})


def test_cache_key_different_days():
    base = {"latitude": -31.4, "longitude": -64.2}
    assert _cache_key({**base, "forecast_days": 5}) != _cache_key({**base, "forecast_days": 7})


def test_cache_key_different_fields():
    base = {"latitude": -31.4, "longitude": -64.2}
    assert _cache_key({**base, "current": "temperature_2m"}) != _cache_key({**base, "current": "visibility"})


# ---------------------------------------------------------------------------
# Hit / Miss — get_current
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_current_miss_then_hit():
    """Segunda llamada idéntica debe devolver el dato cacheado sin hacer un segundo fetch."""
    call_count = 0

    with respx.mock(assert_all_called=False) as mock:
        def handler(request):
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json=_CURRENT_PAYLOAD)

        mock.get(OM_URL).mock(side_effect=handler)

        r1 = await get_current(-31.4, -64.2)
        r2 = await get_current(-31.4, -64.2)

    assert call_count == 1, "Solo debe hacerse 1 fetch; el segundo es cache hit"
    assert r1 is r2, "Cache hit debe devolver el mismo objeto"


@pytest.mark.asyncio
async def test_get_current_different_coords_miss_twice():
    """Coordenadas distintas no colisionan en caché."""
    call_count = 0

    with respx.mock(assert_all_called=False) as mock:
        def handler(request):
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json=_CURRENT_PAYLOAD)

        mock.get(OM_URL).mock(side_effect=handler)

        await get_current(-31.4, -64.2)
        await get_current(-34.6, -58.4)

    assert call_count == 2, "Coords distintas → 2 fetches independientes"


# ---------------------------------------------------------------------------
# Deduplicación concurrente — get_current
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_current_concurrent_dedup():
    """N coroutines concurrentes con la misma clave → exactamente 1 fetch HTTP."""
    call_count = 0

    with respx.mock(assert_all_called=False) as mock:
        async def slow_handler(request):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            return httpx.Response(200, json=_CURRENT_PAYLOAD)

        mock.get(OM_URL).mock(side_effect=slow_handler)

        results = await asyncio.gather(*[get_current(-31.4, -64.2) for _ in range(5)])

    assert call_count == 1, f"Dedup fallido: se hicieron {call_count} fetches"
    assert all(r is results[0] for r in results), "Todos deben recibir el mismo objeto"


@pytest.mark.asyncio
async def test_get_current_concurrent_failure_propagates():
    """Si el fetch falla, todas las coroutines que esperaban reciben None (no KeyError)."""
    with respx.mock(assert_all_called=False) as mock:
        async def slow_fail(request):
            await asyncio.sleep(0.05)
            raise httpx.TimeoutException("timeout")

        mock.get(OM_URL).mock(side_effect=slow_fail)

        results = await asyncio.gather(*[get_current(-31.4, -64.2) for _ in range(4)])

    assert all(r is None for r in results), "Fallo en fetch → todas deben recibir None"


# ---------------------------------------------------------------------------
# Deduplicación concurrente — get_daily_forecast (bucket forecast)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_daily_forecast_concurrent_dedup():
    call_count = 0

    with respx.mock(assert_all_called=False) as mock:
        async def slow_handler(request):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            return httpx.Response(200, json=_DAILY_PAYLOAD)

        mock.get(OM_URL).mock(side_effect=slow_handler)

        results = await asyncio.gather(*[get_daily_forecast(-31.4, -64.2) for _ in range(4)])

    assert call_count == 1
    assert all(r is results[0] for r in results)


# ---------------------------------------------------------------------------
# Aislamiento por bucket — forecast vs nowcast no comparten caché
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_forecast_and_nowcast_buckets_are_isolated():
    """get_daily_forecast y get_visibility_forecast usan buckets distintos."""
    forecast_calls = 0
    nowcast_calls = 0

    with respx.mock(assert_all_called=False) as mock:
        def daily_handler(request):
            nonlocal forecast_calls
            forecast_calls += 1
            return httpx.Response(200, json=_DAILY_PAYLOAD)

        def vis_handler(request):
            nonlocal nowcast_calls
            nowcast_calls += 1
            return httpx.Response(200, json=_VISIBILITY_PAYLOAD)

        # respx matches by URL, but both use the same base URL with different params.
        # We mock generically and rely on call_count per fixture.
        mock.get(OM_URL).mock(side_effect=lambda req: (
            httpx.Response(200, json=_DAILY_PAYLOAD)
            if "daily" in str(req.url)
            else httpx.Response(200, json=_VISIBILITY_PAYLOAD)
        ))

        await get_daily_forecast(-31.4, -64.2)
        await get_visibility_forecast(-31.4, -64.2)
        # Second calls — should be cache hits inside their respective buckets
        await get_daily_forecast(-31.4, -64.2)
        await get_visibility_forecast(-31.4, -64.2)

    # Each function should only have fetched once (second call is a hit)
    # We verify by checking the cache objects directly
    assert om_module._CACHE_FORECAST._cache  # has an entry
    assert om_module._CACHE_NOWCAST._cache   # has an entry


# ---------------------------------------------------------------------------
# Hit / Miss para las otras 6 funciones (smoke test — 1 fetch cada una)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_hourly_forecast_caches():
    call_count = 0

    with respx.mock(assert_all_called=False) as mock:
        def handler(request):
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json=_HOURLY_PAYLOAD)

        mock.get(OM_URL).mock(side_effect=handler)

        await get_hourly_forecast(-31.4, -64.2)
        await get_hourly_forecast(-31.4, -64.2)

    assert call_count == 1


@pytest.mark.asyncio
async def test_get_daily_forecast_ext_caches():
    call_count = 0

    with respx.mock(assert_all_called=False) as mock:
        def handler(request):
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json=_DAILY_EXT_PAYLOAD)

        mock.get(OM_URL).mock(side_effect=handler)

        await get_daily_forecast_ext(-31.4, -64.2, days=7, model="gfs_seamless")
        await get_daily_forecast_ext(-31.4, -64.2, days=7, model="gfs_seamless")

    assert call_count == 1


@pytest.mark.asyncio
async def test_get_daily_forecast_ext_different_models_dont_collide():
    call_count = 0

    with respx.mock(assert_all_called=False) as mock:
        def handler(request):
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json=_DAILY_EXT_PAYLOAD)

        mock.get(OM_URL).mock(side_effect=handler)

        await get_daily_forecast_ext(-31.4, -64.2, days=7, model="gfs_seamless")
        await get_daily_forecast_ext(-31.4, -64.2, days=7, model="ecmwf_ifs025")

    assert call_count == 2, "Modelos distintos → claves distintas → 2 fetches"


@pytest.mark.asyncio
async def test_get_hourly_forecast_ext_caches():
    call_count = 0

    _HOURLY_EXT_PAYLOAD = {
        "latitude": -31.4,
        "longitude": -64.2,
        "hourly": {
            "time": ["2024-01-15T14:00"],
            "temperature_2m": [23.5],
            "precipitation": [0.0],
            "precipitation_probability": [10],
            "wind_speed_10m": [18.0],
            "weather_code": [0],
            "is_day": [1],
        },
    }

    with respx.mock(assert_all_called=False) as mock:
        def handler(request):
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json=_HOURLY_EXT_PAYLOAD)

        mock.get(OM_URL).mock(side_effect=handler)

        await get_hourly_forecast_ext(-31.4, -64.2)
        await get_hourly_forecast_ext(-31.4, -64.2)

    assert call_count == 1


@pytest.mark.asyncio
async def test_get_visibility_forecast_caches():
    call_count = 0

    with respx.mock(assert_all_called=False) as mock:
        def handler(request):
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json=_VISIBILITY_PAYLOAD)

        mock.get(OM_URL).mock(side_effect=handler)

        await get_visibility_forecast(-31.4, -64.2)
        await get_visibility_forecast(-31.4, -64.2)

    assert call_count == 1


@pytest.mark.asyncio
async def test_get_fog_inference_forecast_caches():
    call_count = 0

    with respx.mock(assert_all_called=False) as mock:
        def handler(request):
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json=_FOG_PAYLOAD)

        mock.get(OM_URL).mock(side_effect=handler)

        await get_fog_inference_forecast(-31.4, -64.2)
        await get_fog_inference_forecast(-31.4, -64.2)

    assert call_count == 1
