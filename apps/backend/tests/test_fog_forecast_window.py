"""FRA-339: "Próximas 12 h" de Niebla trae 12 horas que vienen, también de noche.

Regla de "hora actual" (la misma que usa el TAF en `metar.get_nearest_taf_hourly`): el primer
slot es la próxima hora redonda en Argentina (UTC-3). A las 22:50 arranca a las 23:00; a las
23:17, a las 00:00 del día siguiente; exactamente a las 00:00, a la 01:00 (esa hora ya pasó).

El Open-Meteo falso respeta `forecast_days` como el real: devuelve 24 h por día pedido, desde
las 00:00 locales del día de la consulta. Cada hora lleva un valor que identifica su posición
absoluta en la serie, así se distingue "las 00:00 de hoy" de "las 00:00 de mañana".
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from httpx import AsyncClient

import app.services.openmeteo as om_module
from app.core.config import settings
from app.core.rate_limit import limiter
from app.services.openmeteo import (
    _AR_TZ,
    get_fog_inference_forecast,
    get_visibility_forecast,
)

LAT, LON = -31.42, -64.19  # Córdoba
OM_URL = settings.openmeteo_base_url
_FOG_CODE = 45          # WMO niebla → la inferencia lo traduce a 300 m
_CLEAR_M = 10_000.0


def _at(day: int, hour: int, minute: int) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=_AR_TZ)


def _first_slot(now: datetime) -> datetime:
    """Próxima hora redonda: la que cierra la hora en curso."""
    return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def _series_start(series_day: date) -> datetime:
    return datetime.combine(series_day, time(0), tzinfo=_AR_TZ)


def _hour_index(series_day: date, instant: datetime) -> int:
    return int((instant - _series_start(series_day)).total_seconds() // 3600)


def _open_meteo(series_day: date, past_before: datetime, calls: list, force_days: int | None = None):
    """Respuesta de Open-Meteo con `forecast_days` × 24 horas.

    - `visibility` de la hora i vale 100·i m (identifica la hora absoluta de la serie).
    - Las horas anteriores a `past_before` traen código WMO de niebla: si alguna se cuela
      en la inferencia aparece como 300 m; las que vienen son despejadas (10 km).
    """
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        days = force_days or int(request.url.params.get("forecast_days", "7"))
        start = _series_start(series_day)
        instants = [start + timedelta(hours=i) for i in range(24 * days)]
        n = len(instants)
        return httpx.Response(200, json={
            "current": {"time": start.strftime("%Y-%m-%dT%H:%M"), "visibility": 9_000, "weather_code": 1},
            "hourly": {
                "time": [t.strftime("%Y-%m-%dT%H:%M") for t in instants],
                "visibility": [100.0 * i for i in range(n)],
                "relative_humidity_2m": [50.0] * n,
                "dew_point_2m": [5.0] * n,
                "temperature_2m": [20.0] * n,
                "wind_speed_10m": [10.0] * n,
                "weather_code": [_FOG_CODE if t < past_before else 1 for t in instants],
            },
        })
    return handler


@pytest.fixture
def freeze_now(monkeypatch):
    def _freeze(now: datetime) -> None:
        monkeypatch.setattr(om_module, "_ar_now", lambda: now)
    return _freeze


async def _both(now: datetime, freeze_now, calls: list, *, force_days: int | None = None):
    """Llama a las dos funciones como lo hace /api/niebla (con el reloj fijo en `now`)."""
    freeze_now(now)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(OM_URL).mock(side_effect=_open_meteo(now.date(), _first_slot(now), calls, force_days))
        vis = await get_visibility_forecast(LAT, LON)
        fog = await get_fog_inference_forecast(LAT, LON, hours=12)
    return vis, fog


def _expected_labels(now: datetime) -> list[str]:
    first = _first_slot(now)
    return [(first + timedelta(hours=k)).strftime("%H:%M") for k in range(12)]


def _expected_visibility(now: datetime) -> list[float]:
    first_idx = _hour_index(now.date(), _first_slot(now))
    return [100.0 * (first_idx + k) for k in range(12)]


# ---------------------------------------------------------------------------
# De noche: los casos que midió la auditoría y el cruce de medianoche
# ---------------------------------------------------------------------------

NIGHT_CASES = [
    pytest.param(_at(6, 22, 50), "23:00", id="22:50"),
    pytest.param(_at(6, 23, 17), "00:00", id="23:17"),
    pytest.param(_at(6, 23, 59), "00:00", id="23:59"),
    pytest.param(_at(7, 0, 0), "01:00", id="00:00"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("now, first_label", NIGHT_CASES)
async def test_at_night_visibility_brings_the_next_12_hours(now, first_label, freeze_now):
    vis, _ = await _both(now, freeze_now, [])

    assert vis is not None
    assert vis.hourly_labels[0] == first_label
    assert vis.hourly_labels == _expected_labels(now)
    # Las horas son las que vienen (incluidas las de mañana), no las de hoy ya pasadas.
    assert vis.hourly_m == _expected_visibility(now)


@pytest.mark.asyncio
@pytest.mark.parametrize("now, first_label", NIGHT_CASES)
async def test_at_night_fog_inference_brings_the_next_12_hours(now, first_label, freeze_now):
    _, fog = await _both(now, freeze_now, [])

    assert fog is not None
    assert [s.hour_label for s in fog] == _expected_labels(now)
    assert fog[0].hour_label == first_label
    # Ninguna hora ya pasada (las pasadas traen niebla en el Open-Meteo falso).
    assert [s.visibility_m for s in fog] == [_CLEAR_M] * 12


# ---------------------------------------------------------------------------
# Cualquier hora del día
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("hour", range(24))
async def test_any_hour_of_the_day_brings_12_upcoming_slots(hour, freeze_now):
    now = _at(6, hour, 30)
    vis, fog = await _both(now, freeze_now, [])

    assert vis is not None and fog is not None
    assert vis.hourly_labels == _expected_labels(now)
    assert vis.hourly_m == _expected_visibility(now)
    assert [s.hour_label for s in fog] == _expected_labels(now)
    assert all(s.visibility_m == _CLEAR_M for s in fog)


# ---------------------------------------------------------------------------
# Un único pedido a Open-Meteo
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_one_request_covers_both_functions_and_asks_for_two_days(freeze_now):
    calls: list[httpx.Request] = []
    await _both(_at(6, 23, 17), freeze_now, calls)

    assert len(calls) == 1
    assert int(calls[0].url.params["forecast_days"]) >= 2


@pytest.mark.asyncio
async def test_a_cached_response_still_brings_12_slots_after_midnight(freeze_now):
    # Traída a las 23:59 y reutilizada (caché de 15 min) a las 00:05: sin pedido extra.
    calls: list[httpx.Request] = []
    before, after = _at(6, 23, 59), _at(7, 0, 5)

    freeze_now(before)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(OM_URL).mock(side_effect=_open_meteo(before.date(), _first_slot(after), calls))
        await get_visibility_forecast(LAT, LON)
        freeze_now(after)
        vis = await get_visibility_forecast(LAT, LON)
        fog = await get_fog_inference_forecast(LAT, LON, hours=12)

    assert len(calls) == 1
    assert vis is not None and fog is not None
    assert vis.hourly_labels == _expected_labels(after)
    assert vis.hourly_m == [100.0 * (25 + k) for k in range(12)]   # 01:00 del día 7 = hora 25
    assert [s.visibility_m for s in fog] == [_CLEAR_M] * 12


# ---------------------------------------------------------------------------
# Serie que no llega a la próxima hora: nunca horas pasadas
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_series_that_ends_before_the_next_hour_brings_no_past_hours(freeze_now):
    # Open-Meteo devuelve solo el día de hoy (00:00 a 23:00) y ya son las 23:17.
    vis, fog = await _both(_at(6, 23, 17), freeze_now, [], force_days=1)

    assert vis is not None
    assert vis.hourly_m == []
    assert vis.hourly_labels == []
    assert fog is None


# ---------------------------------------------------------------------------
# De punta a punta: /api/niebla a las 23:17 sin TAF
# ---------------------------------------------------------------------------

@pytest.fixture
def niebla_without_taf(monkeypatch):
    limiter.reset()
    metar = SimpleNamespace(
        visibility_m=8_000.0, icao="SACO", station_name="Córdoba", distance_km=9.0, observed_at=None,
    )
    monkeypatch.setattr("app.routers.niebla.get_nearest_metar_visibility", AsyncMock(return_value=metar))
    monkeypatch.setattr("app.routers.niebla.get_nearest_taf_hourly", AsyncMock(return_value=None))
    yield
    limiter.reset()


@pytest.mark.asyncio
async def test_the_endpoint_shows_the_next_12_hours_at_night(
    async_client: AsyncClient, freeze_now, niebla_without_taf,
):
    now = _at(6, 23, 17)
    calls: list[httpx.Request] = []
    freeze_now(now)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(OM_URL).mock(side_effect=_open_meteo(now.date(), _first_slot(now), calls))
        resp = await async_client.get("/api/niebla", params={"lat": LAT, "lon": LON})

    assert resp.status_code == 200
    body = resp.json()
    assert body["hourly_source"] == "openmeteo_inference"
    assert [s["hour_label"] for s in body["hourly"]] == _expected_labels(now)
    assert all(s["visibility_m"] == _CLEAR_M for s in body["hourly"])
    assert len(calls) == 1
