"""H1: /api/niebla solo usa el METAR si el aeropuerto está a <= 20 km y el reporte tiene <= 90 min.

Antes, `get_nearest_metar_visibility` mostraba como "visibilidad ahora" el METAR del aeropuerto más
cercano sin límite de distancia ni de antigüedad (y la caché de 30 min solo guardaba el valor).
Ahora aplica los mismos límites que el dashboard (`settings.metar_max_distance_km` /
`settings.metar_max_age_minutes`, inclusivos) y, si no se cumplen, devuelve `visibility_m=None`
para que el router caiga a Open-Meteo. La antigüedad se verifica en cada lectura, también en cache hit.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from httpx import AsyncClient

import app.services.reportes_aeronauticos.metar as metar_module
from app.core.config import Settings
from app.core.rate_limit import limiter
from app.services.openmeteo import VisibilityData
from app.services.reportes_aeronauticos.aeropuertos import AR_AIRPORTS
from app.services.reportes_aeronauticos.awc import AWC_METAR_BASE
from app.services.reportes_aeronauticos.metar import get_metar_visibility, get_nearest_metar_visibility

NOW = datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc)

ROSARIO = (-32.95, -60.65)                # SAAR ~13 km
QUILMES = (-34.72, -58.25)                # SABE ~23.5 km: entre 20 y 30 km (antes pasaba, ahora no)
SANTIAGO_DEL_ESTERO = (-27.78, -64.27)    # SANT a más de 100 km
SAAR = next(a for a in AR_AIRPORTS if a.icao == "SAAR")


def _ts(moment: datetime) -> int:
    return int(moment.timestamp())


def _payload(obs: datetime | None, icao: str = "SAAR", **extra: object) -> list[dict]:
    entry: dict = {"icao": icao, "visib": "6+", **extra}
    if obs is not None:
        entry["obsTime"] = _ts(obs)
    return [entry]


def _fresh_payload(icao: str = "SAAR") -> list[dict]:
    """METAR de hace 10 min respecto del reloj real (para los tests de punta a punta)."""
    return _payload(datetime.now(timezone.utc) - timedelta(minutes=10), icao)


@pytest.fixture(autouse=True)
def fresh_state():
    """/api/niebla permite 30 req/min con un limiter compartido por toda la sesión."""
    limiter.reset()
    metar_module._metar_cache.clear()
    yield
    limiter.reset()
    metar_module._metar_cache.clear()


@pytest.fixture
def at_distance(monkeypatch):
    """Fija la distancia al aeropuerto más cercano (Rosario/SAAR) para probar los bordes."""

    def _set(km: float) -> None:
        monkeypatch.setattr(metar_module, "nearest_airport_with_distance", lambda lat, lon: (SAAR, km))

    return _set


# ---------------------------------------------------------------------------
# Valores por defecto
# ---------------------------------------------------------------------------

def test_default_limits_are_20_km_and_90_minutes():
    assert Settings.model_fields["metar_max_distance_km"].default == 20.0
    assert Settings.model_fields["metar_max_age_minutes"].default == 90


# ---------------------------------------------------------------------------
# Distancia: más de 20 km se descarta y no se llama a AWC
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_airport_between_20_and_30_km_is_discarded_without_calling_awc():
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(AWC_METAR_BASE).mock(
            return_value=httpx.Response(200, json=_payload(NOW - timedelta(minutes=10), "SABE"))
        )
        result = await get_nearest_metar_visibility(*QUILMES, now=NOW)

    assert result.visibility_m is None
    assert result.observed_at is None
    assert result.icao == "SABE"
    assert result.station_name == "Aeroparque"
    assert 20.0 < result.distance_km < 30.0
    assert route.call_count == 0


@pytest.mark.asyncio
async def test_far_airport_is_discarded_without_calling_awc():
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(AWC_METAR_BASE).mock(
            return_value=httpx.Response(200, json=_payload(NOW - timedelta(minutes=10), "SANT"))
        )
        result = await get_nearest_metar_visibility(*SANTIAGO_DEL_ESTERO, now=NOW)

    assert result.visibility_m is None
    assert result.icao == "SANT"
    assert result.distance_km > 100
    assert route.call_count == 0


@pytest.mark.asyncio
async def test_exactly_20_km_still_uses_the_metar(at_distance):
    at_distance(20.0)
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(AWC_METAR_BASE).mock(
            return_value=httpx.Response(200, json=_payload(NOW - timedelta(minutes=10)))
        )
        result = await get_nearest_metar_visibility(*ROSARIO, now=NOW)

    assert result.visibility_m == 10_000.0
    assert result.distance_km == 20.0
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_a_hair_beyond_20_km_is_discarded(at_distance):
    at_distance(20.01)
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(AWC_METAR_BASE).mock(
            return_value=httpx.Response(200, json=_payload(NOW - timedelta(minutes=10)))
        )
        result = await get_nearest_metar_visibility(*ROSARIO, now=NOW)

    assert result.visibility_m is None
    assert result.icao == "SAAR"
    assert result.distance_km == 20.0   # se informa redondeado, como hoy
    assert route.call_count == 0


@pytest.mark.asyncio
async def test_a_close_fresh_metar_is_used_and_carries_its_observation_time():
    obs = NOW - timedelta(minutes=25)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=_payload(obs)))
        result = await get_nearest_metar_visibility(*ROSARIO, now=NOW)

    assert result.visibility_m == 10_000.0
    assert result.icao == "SAAR"
    assert result.observed_at == obs


# ---------------------------------------------------------------------------
# Antigüedad: más de 90 min se descarta, también desde la caché
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exactly_90_minutes_old_still_passes():
    obs = NOW - timedelta(minutes=90)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=_payload(obs)))
        result = await get_nearest_metar_visibility(*ROSARIO, now=NOW)

    assert result.visibility_m == 10_000.0
    assert result.observed_at == obs


@pytest.mark.asyncio
async def test_older_than_90_minutes_is_discarded():
    obs = NOW - timedelta(minutes=90, seconds=1)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=_payload(obs)))
        result = await get_nearest_metar_visibility(*ROSARIO, now=NOW)

    assert result.visibility_m is None
    assert result.observed_at is None
    assert result.icao == "SAAR"          # la estación y la distancia se siguen informando
    assert result.station_name == "Rosario"


@pytest.mark.asyncio
async def test_stale_report_is_not_cached_so_a_newer_one_is_picked_up_next_time():
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(AWC_METAR_BASE)
        route.mock(return_value=httpx.Response(200, json=_payload(NOW - timedelta(hours=3))))
        first = await get_nearest_metar_visibility(*ROSARIO, now=NOW)
        assert "SAAR" not in metar_module._metar_cache

        route.mock(return_value=httpx.Response(200, json=_payload(NOW - timedelta(minutes=5))))
        second = await get_nearest_metar_visibility(*ROSARIO, now=NOW)

    assert first.visibility_m is None
    assert second.visibility_m == 10_000.0
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_cache_hit_within_the_limit_makes_no_request_and_keeps_the_observation_time():
    obs = NOW - timedelta(minutes=60)
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(AWC_METAR_BASE).mock(
            return_value=httpx.Response(200, json=_payload(obs))
        )
        first = await get_nearest_metar_visibility(*ROSARIO, now=NOW)
        second = await get_nearest_metar_visibility(*ROSARIO, now=NOW + timedelta(minutes=30))   # 90 min exactos

    assert first.visibility_m == second.visibility_m == 10_000.0
    assert second.observed_at == obs
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_cache_hit_that_has_become_older_than_90_minutes_is_discarded():
    obs = NOW - timedelta(minutes=60)
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(AWC_METAR_BASE).mock(
            return_value=httpx.Response(200, json=_payload(obs))
        )
        first = await get_nearest_metar_visibility(*ROSARIO, now=NOW)
        later = NOW + timedelta(minutes=31)                                       # el reporte ya tiene 91 min
        second = await get_nearest_metar_visibility(*ROSARIO, now=later)

    assert first.visibility_m == 10_000.0
    assert second.visibility_m is None
    assert second.observed_at is None
    assert route.call_count == 2        # la entrada vencida se descarta y se vuelve a consultar a AWC


@pytest.mark.asyncio
async def test_stale_cache_hit_is_replaced_by_a_newer_report_from_awc():
    old = NOW - timedelta(minutes=60)
    newer = NOW + timedelta(minutes=25)
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(AWC_METAR_BASE)
        route.mock(return_value=httpx.Response(200, json=_payload(old)))
        await get_nearest_metar_visibility(*ROSARIO, now=NOW)

        route.mock(return_value=httpx.Response(200, json=_payload(newer, visib="3")))
        second = await get_nearest_metar_visibility(*ROSARIO, now=NOW + timedelta(minutes=31))

    assert second.visibility_m == pytest.approx(4_828.032, abs=0.5)
    assert second.observed_at == newer


@pytest.mark.asyncio
async def test_get_metar_visibility_applies_the_age_limit_too():
    obs = NOW - timedelta(minutes=120)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=_payload(obs)))
        assert await get_metar_visibility("SAAR", now=NOW) is None
        assert await get_metar_visibility("SAAR", now=obs + timedelta(minutes=90)) == 10_000.0


# ---------------------------------------------------------------------------
# Sin obsTime válido se descarta (como el dashboard)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("obs_time", [None, "abc", "", "nan", "inf", 1e30])
async def test_missing_or_invalid_obs_time_is_discarded_and_not_cached(obs_time):
    entry = {"icao": "SAAR", "visib": "6+"}
    if obs_time is not None:
        entry["obsTime"] = obs_time
    with respx.mock(assert_all_called=False) as mock:
        mock.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=[entry]))
        result = await get_nearest_metar_visibility(*ROSARIO, now=NOW)

    assert result.visibility_m is None
    assert result.observed_at is None
    assert "SAAR" not in metar_module._metar_cache


# ---------------------------------------------------------------------------
# De punta a punta: el router cae a Open-Meteo y sigue informando la estación
# ---------------------------------------------------------------------------

@pytest.fixture
def stub_other_sources(monkeypatch):
    """Open-Meteo "ahora" distinguible del METAR (3 km); TAF e inferencia apagados."""
    open_meteo = VisibilityData(
        current_m=3_000.0,
        weather_code=1,
        fog_level=2,
        fog_label="Neblina o bruma",
        fog_color="#f0a020",
        hourly_m=[3_000.0] * 12,
        hourly_labels=[f"{h:02d}:00" for h in range(12)],
    )
    monkeypatch.setattr("app.routers.niebla.get_visibility_forecast", AsyncMock(return_value=open_meteo))
    monkeypatch.setattr("app.routers.niebla.get_nearest_taf_hourly", AsyncMock(return_value=None))
    monkeypatch.setattr("app.routers.niebla.get_fog_inference_forecast", AsyncMock(return_value=None))


@pytest.mark.asyncio
async def test_endpoint_uses_a_close_fresh_metar(async_client: AsyncClient, stub_other_sources):
    with respx.mock(assert_all_called=False) as mock:
        mock.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=_fresh_payload()))
        resp = await async_client.get("/api/niebla", params={"lat": ROSARIO[0], "lon": ROSARIO[1]})

    body = resp.json()
    assert resp.status_code == 200
    assert body["source"] == "metar"
    assert body["metar_station"] == "SAAR"
    assert body["visibility_m"] == 10_000.0


@pytest.mark.asyncio
async def test_endpoint_falls_back_to_open_meteo_when_the_airport_is_beyond_20_km(
    async_client: AsyncClient, stub_other_sources,
):
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(AWC_METAR_BASE).mock(
            return_value=httpx.Response(200, json=_fresh_payload("SABE"))
        )
        resp = await async_client.get("/api/niebla", params={"lat": QUILMES[0], "lon": QUILMES[1]})

    body = resp.json()
    assert resp.status_code == 200
    assert body["source"] == "openmeteo"
    assert body["visibility_m"] == 3_000.0
    assert body["metar_station"] == "SABE"
    assert body["metar_station_name"] == "Aeroparque"
    assert 20.0 < body["metar_distance_km"] < 30.0
    assert route.call_count == 0


@pytest.mark.asyncio
async def test_endpoint_falls_back_to_open_meteo_when_the_metar_is_older_than_90_minutes(
    async_client: AsyncClient, stub_other_sources,
):
    stale = _payload(datetime.now(timezone.utc) - timedelta(hours=2))
    with respx.mock(assert_all_called=False) as mock:
        mock.get(AWC_METAR_BASE).mock(return_value=httpx.Response(200, json=stale))
        resp = await async_client.get("/api/niebla", params={"lat": ROSARIO[0], "lon": ROSARIO[1]})

    body = resp.json()
    assert resp.status_code == 200
    assert body["source"] == "openmeteo"
    assert body["visibility_m"] == 3_000.0
    assert body["metar_station"] == "SAAR"
    assert body["metar_station_name"] == "Rosario"
    assert 0 < body["metar_distance_km"] <= 20.0


@pytest.mark.asyncio
async def test_endpoint_falls_back_to_open_meteo_when_the_metar_has_no_obs_time(
    async_client: AsyncClient, stub_other_sources,
):
    with respx.mock(assert_all_called=False) as mock:
        mock.get(AWC_METAR_BASE).mock(
            return_value=httpx.Response(200, json=_payload(None))
        )
        resp = await async_client.get("/api/niebla", params={"lat": ROSARIO[0], "lon": ROSARIO[1]})

    body = resp.json()
    assert body["source"] == "openmeteo"
    assert body["metar_station"] == "SAAR"
