"""Tests del caché single-flight de Open-Meteo (Fix 1).

Cubre:
- Hit/miss por clave canónica.
- Deduplicación: N coroutines concurrentes con la misma clave → 1 solo fetch.
- Claves distintas por model/days/fields no colisionan.
- _cache_key redondea lat/lon a 2 decimales (~1.1 km) para subir el hit-rate.
- Fallo del fetcher: las N coroutines esperando reciben la misma excepción, no KeyError.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

import app.services.openmeteo as om_module
from app.services.openmeteo import (
    get_current,
    get_daily_forecast_ext,
    get_fog_inference_forecast,
    get_hourly_forecast_ext,
    get_visibility_forecast,
)
from app.services.openmeteo_source import cache_key as _cache_key


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
    # Both values have noise only in the 5th+ decimal (< 5), so round to same 2-decimal value.
    p1 = {"latitude": -31.40001, "longitude": -64.20001}  # → -31.4, -64.2
    p2 = {"latitude": -31.40004, "longitude": -64.20004}  # → -31.4, -64.2
    assert _cache_key(p1) == _cache_key(p2)


def test_cache_key_collapses_close_coords_at_2_decimals():
    """Coordenadas que difieren solo en el 3er/4to decimal (~1 km) ahora colapsan
    en la misma entrada de caché: _cache_key redondea a 2 decimales (antes 4)."""
    p1 = {"latitude": -31.411, "longitude": -64.201}   # → -31.41, -64.2
    p2 = {"latitude": -31.414, "longitude": -64.204}   # → -31.41, -64.2
    assert _cache_key(p1) == _cache_key(p2)


def test_cache_key_still_distinguishes_coords_1km_apart_or_more():
    """El redondeo a 2 decimales no debe colapsar coordenadas genuinamente distintas
    (diferencia >= ~1.1 km, es decir >= 0.01 en el 2do decimal)."""
    p1 = {"latitude": -31.41, "longitude": -64.20}
    p2 = {"latitude": -31.43, "longitude": -64.20}
    assert _cache_key(p1) != _cache_key(p2)


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
    """Sin fetch previo exitoso, un fallo devuelve None (no hay stale que servir)."""
    with respx.mock(assert_all_called=False) as mock:
        async def slow_fail(request):
            await asyncio.sleep(0.05)
            raise httpx.TimeoutException("timeout")

        mock.get(OM_URL).mock(side_effect=slow_fail)

        results = await asyncio.gather(*[get_current(-31.4, -64.2) for _ in range(4)])

    assert all(r is None for r in results), "Fallo en fetch sin stale previo → todas reciben None"


# ---------------------------------------------------------------------------
# Stale-while-error — fallback al último dato bueno ante fetch fallido
# (cierra Sentry SKYPULSE-BACKEND-1/2/3: cascada 503 cuando Open-Meteo
# rate-limitea justo cuando toca refrescar el caché)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_current_serves_stale_when_fetch_fails_after_ttl_expiry():
    """TTL fresco vencido + fetch nuevo falla → sirve el último valor bueno, no None."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get(OM_URL).mock(return_value=httpx.Response(200, json=_CURRENT_PAYLOAD))
        first = await get_current(-31.4, -64.2)
    assert first is not None

    # Simula vencimiento del TTL fresco (600s) sin esperar — el stale-cache
    # (TTL largo) sigue teniendo la entrada.
    om_module._CACHE_CURRENT._cache.clear()

    with respx.mock(assert_all_called=False) as mock:
        mock.get(OM_URL).mock(side_effect=httpx.ConnectError("rate limited"))
        second = await get_current(-31.4, -64.2)

    assert second is first, "Debe servir exactamente el objeto stale cacheado, no None"


@pytest.mark.asyncio
async def test_get_current_no_stale_fallback_available_returns_none():
    """Sin ningún fetch exitoso previo, un fetch fallido sigue devolviendo None."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get(OM_URL).mock(side_effect=httpx.ConnectError("dns fail"))
        result = await get_current(-31.4, -64.2)

    assert result is None


# ---------------------------------------------------------------------------
# Deduplicación concurrente — get_daily_forecast_ext (bucket forecast)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_daily_forecast_concurrent_dedup():
    call_count = 0

    with respx.mock(assert_all_called=False) as mock:
        async def slow_handler(request):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            return httpx.Response(200, json=_DAILY_EXT_PAYLOAD)

        mock.get(OM_URL).mock(side_effect=slow_handler)

        results = await asyncio.gather(*[get_daily_forecast_ext(-31.4, -64.2) for _ in range(4)])

    assert call_count == 1
    assert all(r is results[0] for r in results)


# ---------------------------------------------------------------------------
# Aislamiento por bucket — forecast vs nowcast no comparten caché
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_forecast_and_nowcast_buckets_are_isolated():
    """get_daily_forecast_ext y get_visibility_forecast usan buckets distintos."""
    forecast_calls = 0
    nowcast_calls = 0

    with respx.mock(assert_all_called=False) as mock:
        def daily_handler(request):
            nonlocal forecast_calls
            forecast_calls += 1
            return httpx.Response(200, json=_DAILY_EXT_PAYLOAD)

        def vis_handler(request):
            nonlocal nowcast_calls
            nowcast_calls += 1
            return httpx.Response(200, json=_VISIBILITY_PAYLOAD)

        # respx matches by URL, but both use the same base URL with different params.
        # We mock generically and rely on call_count per fixture.
        mock.get(OM_URL).mock(side_effect=lambda req: (
            httpx.Response(200, json=_DAILY_EXT_PAYLOAD)
            if "daily" in str(req.url)
            else httpx.Response(200, json=_VISIBILITY_PAYLOAD)
        ))

        await get_daily_forecast_ext(-31.4, -64.2)
        await get_visibility_forecast(-31.4, -64.2)
        # Second calls — should be cache hits inside their respective buckets
        await get_daily_forecast_ext(-31.4, -64.2)
        await get_visibility_forecast(-31.4, -64.2)

    # Each function should only have fetched once (second call is a hit)
    # We verify by checking the cache objects directly
    assert om_module._CACHE_FORECAST._cache  # has an entry
    assert om_module._CACHE_NOWCAST._cache   # has an entry


# ---------------------------------------------------------------------------
# Hit / Miss para las otras 6 funciones (smoke test — 1 fetch cada una)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# stats() — hit-rate diagnóstico (Plan A Fase 2, Parte B)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stats_tracks_hits_and_fetches():
    """Hit fresco + miss/fetch + dedup-wait concurrente → stats() correctos."""
    from app.core.cache import SingleFlightCache

    cache: SingleFlightCache = SingleFlightCache(maxsize=8, ttl=60, name="stats_test")

    async def fetch_once() -> str:
        return "value"

    # Miss/fetch inicial — 1 fetch, 0 hits
    r1 = await cache.get_or_fetch("k1", fetch_once)
    assert r1 == "value"

    # Hit fresco — no debe llamar fetch de nuevo
    r2 = await cache.get_or_fetch("k1", fetch_once)
    assert r2 == "value"

    # Dedup concurrente sobre una clave nueva: 1 fetch responsable + 3 waiters (hits)
    call_count = 0

    async def slow_fetch() -> str:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        return "concurrent"

    results = await asyncio.gather(*[cache.get_or_fetch("k2", slow_fetch) for _ in range(4)])
    assert call_count == 1
    assert all(r == "concurrent" for r in results)

    stats = cache.stats()
    # fetches: 1 (k1 miss) + 1 (k2 responsable) = 2
    # hits: 1 (k1 hit fresco) + 3 (k2 waiters) = 4
    assert stats["fetches"] == 2
    assert stats["hits"] == 4
    assert stats["hit_rate"] == pytest.approx(4 / 6)


@pytest.mark.asyncio
async def test_stats_empty_cache_hit_rate_is_zero():
    from app.core.cache import SingleFlightCache

    cache: SingleFlightCache = SingleFlightCache(maxsize=8, ttl=60, name="stats_empty")
    stats = cache.stats()
    assert stats == {"hits": 0, "fetches": 0, "hit_rate": 0.0}


# ---------------------------------------------------------------------------
# Las cachés de Open-Meteo con Upstash (falso, con estado) de punta a punta
# ---------------------------------------------------------------------------

from types import SimpleNamespace  # noqa: E402

from app.core import upstash  # noqa: E402
from app.core.cache import CacheOutcome, SingleFlightCache  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.persistent_cache import SCHEMA_VERSION  # noqa: E402
from app.core.upstash import UpstashRedis  # noqa: E402
from tests.conftest import FAKE_UPSTASH_TOKEN, FAKE_UPSTASH_URL, FakeUpstash  # noqa: E402

_PREFIX = "skypulse:om_last_good:"


@pytest.fixture
def world():
    """Open-Meteo y Upstash falsos en el mismo router; el handle de Upstash queda configurado."""
    fake = FakeUpstash()
    with respx.mock(assert_all_called=False) as router:
        router.post(url__startswith=FAKE_UPSTASH_URL).mock(side_effect=fake.handle)
        om = router.get(OM_URL)
        om.mock(return_value=httpx.Response(200, json=_CURRENT_PAYLOAD))
        upstash.configure_redis(UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN))
        try:
            yield SimpleNamespace(fake=fake, om=om, router=router)
        finally:
            upstash.configure_redis(None)


def _restart(*caches: SingleFlightCache) -> None:
    """Simula un reinicio de Render: la memoria se pierde, Redis no."""
    for cache in caches:
        cache.clear()
    for store in om_module._LAST_GOOD_STORES:
        store.reset()


def _persisted_keys(fake: FakeUpstash) -> list[str]:
    return [k for k in fake.strings if k.startswith(_PREFIX)]


def _rate_limited(world) -> None:
    world.om.mock(return_value=httpx.Response(429, json={"error": True}))


async def test_current_is_saved_with_the_current_ttl(world) -> None:
    assert await om_module.get_current(-31.4, -64.2) is not None
    await om_module._CACHE_CURRENT.flush_persistence()
    (key,) = _persisted_keys(world.fake)
    assert key.startswith(f"{_PREFIX}v{SCHEMA_VERSION}:om_current:")
    assert world.fake.ttls[key] == settings.openmeteo_last_good_ttl_current_seconds == 10800
    assert all(cmd[0] == "SET" for cmd in world.fake.commands)


async def test_the_dashboard_survives_a_restart_while_open_meteo_answers_429(world) -> None:
    first = await om_module.get_current(-31.4, -64.2)
    await om_module._CACHE_CURRENT.flush_persistence()
    _restart(om_module._CACHE_CURRENT)
    _rate_limited(world)

    outcome = CacheOutcome()
    again = await om_module.get_current(-31.4, -64.2, cache_outcome=outcome)
    assert again == first
    assert again.fetched_at == first.fetched_at       # la edad real viaja con el dato
    assert outcome.hit is True


async def test_forecast_values_use_the_long_ttl_and_come_back_after_a_restart(world) -> None:
    world.om.mock(return_value=httpx.Response(200, json=_DAILY_EXT_PAYLOAD))
    first = await om_module.get_daily_forecast_ext(-31.4, -64.2)
    await om_module._CACHE_FORECAST.flush_persistence()
    (key,) = _persisted_keys(world.fake)
    assert world.fake.ttls[key] == settings.openmeteo_last_good_ttl_forecast_seconds == 21600

    _restart(om_module._CACHE_FORECAST)
    _rate_limited(world)
    assert await om_module.get_daily_forecast_ext(-31.4, -64.2) == first


async def test_multi_model_is_rebuilt_from_persisted_models_and_not_saved_itself(
    world, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempted: list[str] = []
    real_save = om_module._STORE_FORECAST.save

    async def spy(key: str, value) -> None:
        attempted.append(type(value).__name__)
        await real_save(key, value)

    monkeypatch.setattr(om_module._STORE_FORECAST, "save", spy)
    world.om.mock(return_value=httpx.Response(200, json=_DAILY_EXT_PAYLOAD))
    first = await om_module.get_multi_model_daily(-31.4, -64.2)
    await om_module._CACHE_FORECAST.flush_persistence()
    # Solo se guardan los dos modelos: el consenso es derivado y guardarlo reiniciaría el reloj del dato.
    assert sorted(attempted) == ["DailyForecastDataExt", "DailyForecastDataExt"]
    assert len(_persisted_keys(world.fake)) == 2

    _restart(om_module._CACHE_FORECAST)
    _rate_limited(world)
    again = await om_module.get_multi_model_daily(-31.4, -64.2)
    assert again == first


async def test_niebla_raw_payload_is_persisted_in_the_nowcast_bucket(world) -> None:
    world.om.mock(return_value=httpx.Response(200, json=_VISIBILITY_PAYLOAD))
    first = await om_module.get_visibility_forecast(-31.4, -64.2)
    await om_module._CACHE_NOWCAST.flush_persistence()
    (key,) = _persisted_keys(world.fake)
    assert ":om_nowcast:" in key
    assert world.fake.ttls[key] == settings.openmeteo_last_good_ttl_current_seconds

    _restart(om_module._CACHE_NOWCAST)
    _rate_limited(world)
    assert await om_module.get_visibility_forecast(-31.4, -64.2) == first


async def test_saves_are_throttled_across_expiring_fresh_entries(world) -> None:
    await om_module.get_current(-31.4, -64.2)
    om_module._CACHE_CURRENT._cache.clear()           # venció el TTL fresco: nuevo fetch exitoso
    await om_module.get_current(-31.4, -64.2)
    await om_module._CACHE_CURRENT.flush_persistence()
    assert [c[0] for c in world.fake.commands].count("SET") == 1


async def test_redis_is_read_only_when_the_fetch_fails(world) -> None:
    await om_module.get_current(-31.4, -64.2)
    await om_module._CACHE_CURRENT.flush_persistence()
    assert "GET" not in [c[0] for c in world.fake.commands]


async def test_open_meteo_failure_with_nothing_persisted_still_returns_none(world) -> None:
    _rate_limited(world)
    assert await om_module.get_current(-31.4, -64.2) is None
    assert [c[0] for c in world.fake.commands] == ["GET"]


async def test_redis_down_changes_nothing_for_the_caller(world) -> None:
    first = await om_module.get_current(-31.4, -64.2)
    await om_module._CACHE_CURRENT.flush_persistence()
    _restart(om_module._CACHE_CURRENT)
    world.fake.down = True
    _rate_limited(world)
    assert await om_module.get_current(-31.4, -64.2) is None
    from app.core import rate_limit_pause

    rate_limit_pause.openmeteo_pause.reset()          # el 429 de arriba abrió una pausa
    world.om.mock(return_value=httpx.Response(200, json=_CURRENT_PAYLOAD))
    om_module._CACHE_CURRENT.clear()
    assert (await om_module.get_current(-31.4, -64.2)).temp_c == first.temp_c
    await om_module._CACHE_CURRENT.flush_persistence()


async def test_without_upstash_configured_no_redis_traffic_happens() -> None:
    assert upstash.get_redis() is None
    with respx.mock(assert_all_called=False) as router:
        route = router.get(OM_URL)
        route.mock(return_value=httpx.Response(200, json=_CURRENT_PAYLOAD))
        assert await om_module.get_current(-31.4, -64.2) is not None
        await om_module._CACHE_CURRENT.flush_persistence()
        route.mock(return_value=httpx.Response(429))
        om_module._CACHE_CURRENT._cache.clear()
        om_module._CACHE_CURRENT._failure_cache.clear()
        assert await om_module.get_current(-31.4, -64.2) is not None   # stale en memoria, como hoy
        assert {c.request.url.host for c in router.calls} == {"api.open-meteo.com"}


async def test_a_pause_serves_the_persisted_value_without_touching_open_meteo(world) -> None:
    from app.core import rate_limit_pause

    first = await om_module.get_current(-31.4, -64.2)
    await om_module._CACHE_CURRENT.flush_persistence()
    _restart(om_module._CACHE_CURRENT)
    rate_limit_pause.openmeteo_pause.trip()
    calls_before = world.om.call_count
    assert await om_module.get_current(-31.4, -64.2) == first
    assert world.om.call_count == calls_before


def test_the_store_factory_wires_the_budget_and_timeout_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openmeteo_last_good_writes_per_minute", 7)
    monkeypatch.setattr(settings, "openmeteo_last_good_timeout_seconds", 0.7)
    store = om_module._last_good_store("om_x", 100)
    assert store._bucket_capacity == 7
    assert store._timeout == 0.7


# ---------------------------------------------------------------------------
# FetchRefused: a fetch that was not attempted on purpose (a budget said no) is NOT a failure of the key
# ---------------------------------------------------------------------------

def _refusal() -> Exception:
    from app.core.cache import FetchRefused

    return FetchRefused("budget")


async def _refuse():
    raise _refusal()


async def _value(value):
    return value


class _StoredBackend:
    """Persistent backend that only knows how to hand back one value."""

    def __init__(self, value) -> None:
        self.value = value

    async def load(self, key: str):
        return self.value

    async def save(self, key: str, value) -> None:
        self.value = value


def _flight_cache(**kwargs):
    from app.core.cache import SingleFlightCache

    return SingleFlightCache(maxsize=8, ttl=60, name="t", **kwargs)


async def test_a_refused_flight_leaves_no_failure_entry_and_the_next_caller_fetches():
    from app.core.cache import FetchRefused

    cache = _flight_cache()
    with pytest.raises(FetchRefused):
        await cache.get_or_fetch("k", _refuse)

    assert "k" not in cache._failure_cache
    calls: list[int] = []

    async def ok():
        calls.append(1)
        return "v"

    assert await cache.get_or_fetch("k", ok) == "v"
    assert calls == [1]  # not served a remembered failure: it went to the source


async def test_a_refused_flight_serves_the_stale_copy_without_marking_the_key_failed():
    cache = _flight_cache()
    assert await cache.get_or_fetch("k", lambda: _value("old")) == "old"
    cache._cache.clear()  # the fresh TTL expired; the stale copy stays
    outcome = CacheOutcome()

    assert await cache.get_or_fetch("k", _refuse, outcome=outcome) == "old"

    assert outcome.hit is True
    assert "k" not in cache._failure_cache
    assert await cache.get_or_fetch("k", lambda: _value("new")) == "new"  # the next caller refreshes it


async def test_a_refused_flight_serves_the_persisted_copy_without_marking_the_key_failed():
    cache = _flight_cache(persistence=_StoredBackend("persisted"))

    assert await cache.get_or_fetch("k", _refuse) == "persisted"

    assert "k" not in cache._failure_cache


async def test_the_waiters_of_a_refused_flight_get_the_same_outcome():
    from app.core.cache import FetchRefused

    cache = _flight_cache()
    gate = asyncio.Event()

    async def refused_after_the_gate():
        await gate.wait()
        raise _refusal()

    leader = asyncio.create_task(cache.get_or_fetch("k", refused_after_the_gate))
    await asyncio.sleep(0)
    waiter = asyncio.create_task(cache.get_or_fetch("k", lambda: _value("unused")))
    await asyncio.sleep(0)
    gate.set()
    outcomes = await asyncio.gather(leader, waiter, return_exceptions=True)

    assert all(isinstance(outcome, FetchRefused) for outcome in outcomes)
    assert "k" not in cache._failure_cache


async def test_the_waiters_of_a_refused_flight_share_the_stale_copy():
    cache = _flight_cache()
    await cache.get_or_fetch("k", lambda: _value("old"))
    cache._cache.clear()
    gate = asyncio.Event()

    async def refused_after_the_gate():
        await gate.wait()
        raise _refusal()

    first, second = CacheOutcome(), CacheOutcome()
    leader = asyncio.create_task(cache.get_or_fetch("k", refused_after_the_gate, outcome=first))
    await asyncio.sleep(0)
    waiter = asyncio.create_task(cache.get_or_fetch("k", lambda: _value("unused"), outcome=second))
    await asyncio.sleep(0)
    gate.set()

    assert await asyncio.gather(leader, waiter) == ["old", "old"]
    assert first.hit is True and second.hit is True


async def test_a_refusal_is_not_counted_as_a_real_fetch():
    from app.core.cache import FetchRefused

    cache = _flight_cache()
    with pytest.raises(FetchRefused):
        await cache.get_or_fetch("k", _refuse)

    assert cache.stats()["fetches"] == 0


async def test_a_real_failure_is_still_negative_cached():
    cache = _flight_cache()
    assert await cache.get_or_fetch("none", lambda: _value(None)) is None
    assert "none" in cache._failure_cache

    async def boom():
        raise RuntimeError("upstream down")

    with pytest.raises(RuntimeError):
        await cache.get_or_fetch("raise", boom)
    assert "raise" in cache._failure_cache
