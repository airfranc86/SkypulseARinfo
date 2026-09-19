"""Tests de integración para GET /api/weather/dashboard."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.schemas.weather import (
    SourceMeta,
    StationMeta,
    WeatherCurrentResponse,
)
from app.services.openmeteo import (
    DailyForecastDataExt,
    HourlyForecastExt,
    MultiModelDailyData,
)
from tests.hourly_fixtures import AR, make_hourly


# ---------------------------------------------------------------------------
# Helpers — datos de ejemplo
# ---------------------------------------------------------------------------

def _make_current_response() -> WeatherCurrentResponse:
    station = StationMeta(
        name="CÓRDOBA AEROPUERTO",
        lat=-31.323,
        lon=-64.208,
        distance_km=15.2,
        observed_at=datetime.now(timezone.utc),
    )
    meta = SourceMeta(
        source="smn",
        reason="smn_nearby_fresh",
        station=station,
        fetched_at=datetime.now(timezone.utc),
        cache_hit=False,
    )
    return WeatherCurrentResponse(
        lat=-31.4,
        lon=-64.2,
        temp_c=18.5,
        feels_like_c=17.0,
        humidity=65.0,
        wind_speed_kmh=12.0,
        wind_dir_deg=270.0,
        wind_dir_cardinal="W",
        pressure_hpa=1013.0,
        precip_1h_mm=0.0,
        cloud_cover=20.0,
        description="Despejado",
        meta=meta,
    )


def _make_daily_ext(
    model_name: str = "ecmwf_ifs025",
    *,
    start: date | None = None,
    precip_sum: list[float | None] | None = None,
    precip_prob_max: list[float | None] | None = None,
) -> DailyForecastDataExt:
    first = start or date(2026, 5, 20)
    dates = [(first + timedelta(days=i)).isoformat() for i in range(7)]
    n = len(dates)
    return DailyForecastDataExt(
        dates=dates,
        day_labels=["miércoles", "jueves", "viernes", "sábado", "domingo", "lunes", "martes"],
        temp_max=[22.0] * n,
        temp_min=[10.0] * n,
        precip_sum=precip_sum or [0.0] * n,
        precip_prob_max=precip_prob_max or [5.0] * n,
        wind_speed_max=[15.0] * n,
        wind_gusts_max=[25.0] * n,
        humidity_mean=[60.0] * n,
        uv_max=[4.0] * n,
        weather_codes=[0] * n,
        sunrise=["2026-05-20T07:00"] * n,
        sunset=["2026-05-20T18:30"] * n,
        daylight_seconds=[41400.0] * n,  # 11h 30m
    )


def _make_multi_model(**daily_kwargs) -> MultiModelDailyData:
    daily = _make_daily_ext(**daily_kwargs)
    return MultiModelDailyData(
        models={
            "ecmwf_ifs025": daily,
            "gfs_seamless": daily,
            "icon_seamless": daily,
        },
        consensus_pct_per_day=[100.0] * 7,
        rain_consensus_per_day=["all_agree_dry"] * 7,
    )


def _today_midnight() -> datetime:
    """00:00 de hoy en Argentina: la serie horaria arranca hoy, así hay franjas por venir a cualquier hora."""
    return datetime.now(AR).replace(hour=0, minute=0, second=0, microsecond=0)


def _make_hourly(**overrides) -> HourlyForecastExt:
    return make_hourly(48, start=_today_midnight(), **overrides)


@contextmanager
def _dashboard_mocks(
    *,
    current: WeatherCurrentResponse | None = None,
    daily: MultiModelDailyData | None = None,
    hourly: HourlyForecastExt | None | Any = "default",
):
    """Parchea las tres fuentes del dashboard: la observación y Open-Meteo diario y horario."""
    hourly_value = _make_hourly() if hourly == "default" else hourly
    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=current or _make_current_response()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=daily or _make_multi_model()),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=hourly_value),
    ):
        yield


# ---------------------------------------------------------------------------
# Test: happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_happy_path(async_client: AsyncClient):
    """Debe retornar 200 con todos los campos requeridos."""
    with _dashboard_mocks():
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    assert response.status_code == 200
    data = response.json()

    # Campos de primer nivel
    assert "location" in data
    assert "current" in data
    assert "day_arc" in data
    assert "moon_phase" in data
    assert "rain_today" in data
    assert "hourly" in data
    assert "forecast_7d" in data
    assert "fetched_at" in data


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_location_fields(async_client: AsyncClient):
    with _dashboard_mocks():
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    data = response.json()
    assert data["location"]["lat"] == pytest.approx(-31.4)
    assert data["location"]["lon"] == pytest.approx(-64.2)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_current_fields(async_client: AsyncClient):
    with _dashboard_mocks():
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    current = response.json()["current"]
    assert current["temp_c"] == pytest.approx(18.5)
    assert current["humidity"] == pytest.approx(65.0)
    assert "description" in current
    assert "icon" in current
    assert "is_day" in current


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_moon_phase_shape(async_client: AsyncClient):
    with _dashboard_mocks():
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    moon = response.json()["moon_phase"]
    assert "name" in moon
    assert "illumination" in moon
    assert "icon" in moon
    assert 0.0 <= moon["illumination"] <= 1.0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_day_arc_shape(async_client: AsyncClient):
    with _dashboard_mocks():
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    arc = response.json()["day_arc"]
    assert "sunrise" in arc
    assert "sunset" in arc
    assert "current_position_pct" in arc
    assert "daylight_label" in arc
    assert "is_day" in arc
    assert "h" in arc["daylight_label"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_forecast_7d_count(async_client: AsyncClient):
    """El forecast debe tener exactamente 7 entradas."""
    with _dashboard_mocks():
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    forecast = response.json()["forecast_7d"]
    assert len(forecast) == 7


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_forecast_7d_entry_shape(async_client: AsyncClient):
    """Cada entrada del forecast debe tener los campos esperados."""
    with _dashboard_mocks():
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    entry = response.json()["forecast_7d"][0]
    required_fields = {
        "date", "day_label", "day_label_long",
        "temp_max", "temp_min", "precip_sum", "precip_prob",
        "wind_speed_max", "snow_level_m", "weather_code", "icon",
        "confidence_pct", "confidence_label",
    }
    for field in required_fields:
        assert field in entry, f"Campo '{field}' ausente en forecast_7d entry"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_confidence_label_valid(async_client: AsyncClient):
    """confidence_label debe ser ALTA, MEDIA o BAJA."""
    with _dashboard_mocks():
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    for entry in response.json()["forecast_7d"]:
        assert entry["confidence_label"] in ("ALTA", "MEDIA", "BAJA")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_hourly_entries(async_client: AsyncClient):
    """hourly.entries: una franja cada 3 h (48 h de datos → 16 franjas) con los campos correctos."""
    with _dashboard_mocks():
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    hourly = response.json()["hourly"]
    assert "entries" in hourly
    assert "rain_consensus_label" in hourly
    assert "rain_probability_pct" in hourly
    assert len(hourly["entries"]) == 16
    entry = hourly["entries"][0]
    assert "timestamp" in entry
    assert "hour_label" in entry
    assert "icon" in entry
    assert [e["hour_label"] for e in hourly["entries"][:3]] == ["00:00", "03:00", "06:00"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_rain_today_shape(async_client: AsyncClient):
    with _dashboard_mocks():
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    rain = response.json()["rain_today"]
    assert "status_text" in rain
    assert "has_rain_today" in rain
    assert "confidence_label" in rain
    assert rain["confidence_label"] in ("alta", "media", "baja")


# ---------------------------------------------------------------------------
# Test: 503 cuando falla lo obligatorio
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_503_when_current_fails(async_client: AsyncClient):
    from fastapi import HTTPException

    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock,
              side_effect=HTTPException(status_code=503, detail="all_sources_unavailable")),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=_make_multi_model()),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=_make_hourly()),
    ):
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    assert response.status_code == 503


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_503_when_the_daily_forecast_fails(async_client: AsyncClient):
    """Sin el pronóstico diario de Open-Meteo no hay dashboard: 503, no un pronóstico inventado."""
    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_make_current_response()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=None),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=_make_hourly()),
    ):
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    assert response.status_code == 503
    assert response.json()["detail"] == "forecast_unavailable"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_503_when_the_daily_forecast_raises(async_client: AsyncClient):
    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_make_current_response()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, side_effect=RuntimeError("429")),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=_make_hourly()),
    ):
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    assert response.status_code == 503


# ---------------------------------------------------------------------------
# Test: hourly opcional — si falla, el dashboard igualmente devuelve 200
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_200_when_hourly_unavailable(async_client: AsyncClient):
    """Si el horario falla, el dashboard no bloquea — hourly.entries queda vacío."""
    with _dashboard_mocks(hourly=None):
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    assert response.status_code == 200
    data = response.json()
    assert data["hourly"]["entries"] == []
    assert data["hourly"]["rain_consensus_label"] == "Sin datos"
    # Sin serie horaria no se afirma que no vaya a llover
    assert data["rain_today"]["status_text"] == "Sin datos de lluvia"


# ---------------------------------------------------------------------------
# Test: coordenadas inválidas → 422
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_invalid_lat_returns_422(async_client: AsyncClient):
    response = await async_client.get("/api/weather/dashboard?lat=-60&lon=-64.2")
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_invalid_lon_returns_422(async_client: AsyncClient):
    response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-50")
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_missing_params_returns_422(async_client: AsyncClient):
    response = await async_client.get("/api/weather/dashboard")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Test: un solo modelo disponible (los otros dos fallan)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_single_model_available(async_client: AsyncClient):
    """Con un solo modelo exitoso debe seguir funcionando."""
    single_model = MultiModelDailyData(
        models={"ecmwf_ifs025": _make_daily_ext()},
        consensus_pct_per_day=[100.0] * 7,
        rain_consensus_per_day=["all_agree_dry"] * 7,
    )
    with _dashboard_mocks(daily=single_model):
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    assert response.status_code == 200
    assert len(response.json()["forecast_7d"]) == 7


# ---------------------------------------------------------------------------
# Windy no alimenta el dashboard (plan Testing: datos mezclados al azar)
# ---------------------------------------------------------------------------

@contextmanager
def _windy_tripwire(monkeypatch):
    """Windy configurado y sano en apariencia: si el dashboard lo consulta, el test lo detecta."""
    import app.core.config as cfg

    monkeypatch.setattr(cfg.settings, "windy_api_key", "fake-key", raising=False)
    with (
        patch("app.services.windy.get_hourly_forecast", new_callable=AsyncMock, return_value=[]) as hourly,
        patch("app.services.windy.get_daily_forecast", new_callable=AsyncMock, return_value=[]) as daily,
        patch("app.services.windy.fetch_raw", new_callable=AsyncMock, return_value={}) as raw,
    ):
        yield [hourly, daily, raw]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_never_consults_windy_even_when_configured(async_client: AsyncClient, monkeypatch):
    with _windy_tripwire(monkeypatch) as windy_calls, _dashboard_mocks():
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    assert response.status_code == 200
    for call in windy_calls:
        call.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_has_no_windy_fallback_when_open_meteo_fails(async_client: AsyncClient, monkeypatch):
    """Antes, si Open-Meteo diario fallaba, el pronóstico se sintetizaba desde Windy."""
    with (
        _windy_tripwire(monkeypatch) as windy_calls,
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_make_current_response()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=None),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=None),
    ):
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    assert response.status_code == 503
    for call in windy_calls:
        call.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_forecast_source_is_openmeteo(async_client: AsyncClient):
    with _dashboard_mocks():
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    assert response.json()["forecast_source"] == "openmeteo"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_forecast_7d_comes_from_open_meteo(async_client: AsyncClient):
    with _dashboard_mocks():
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    first = response.json()["forecast_7d"][0]
    assert first["temp_max"] == pytest.approx(22.0)
    assert first["precip_prob"] == pytest.approx(5.0)
    assert first["precip_sum"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# El día y las horas cuentan la misma historia de lluvia (el bug que motivó el cambio)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_day_and_hours_agree_on_a_rainy_tomorrow(async_client: AsyncClient):
    """Mañana en el pronóstico real de Open-Meteo: GFS 16,8 mm y ECMWF 14 mm, probabilidad 100 / 97 %,
    lluvia entre las 16 y las 21 h. Antes la tarjeta del día decía "Lluvia 100 %" (Open-Meteo) mientras
    la tira horaria decía 0,0 mm y "Sin lluvia prevista" (Windy)."""
    today = datetime.now(AR).date()
    rainy = 1  # mañana
    sums = [0.0] * 7
    probs = [5.0] * 7
    sums[rainy], probs[rainy] = 15.4, 100.0
    daily = _make_multi_model(start=today, precip_sum=sums, precip_prob_max=probs)
    hourly = _make_hourly(
        precipitations={24 + 16: 4.4, 24 + 17: 1.7, 24 + 18: 2.3, 24 + 19: 1.7, 24 + 20: 4.8, 24 + 21: 1.5},
        precip_probs={24 + 16: 42.0, 24 + 17: 67.0, 24 + 18: 86.0, 24 + 19: 95.0, 24 + 20: 97.0, 24 + 21: 94.0},
        weather_codes={24 + 16: 96, 24 + 18: 95, 24 + 20: 81},
    )

    with _dashboard_mocks(daily=daily, hourly=hourly):
        response = await async_client.get("/api/weather/dashboard?lat=-34.6&lon=-58.4")

    data = response.json()
    tomorrow = today + timedelta(days=1)
    day = next(d for d in data["forecast_7d"] if d["date"] == tomorrow.isoformat())
    slots = [e for e in data["hourly"]["entries"] if e["date"] == tomorrow.isoformat()]

    assert day["precip_prob"] == pytest.approx(100.0)
    assert day["precip_sum"] > 10
    assert sum(e["precip_mm"] for e in slots) > 10, "las horas de mañana tienen que sumar lluvia de verdad"
    rainy_slots = [e for e in slots if e["precip_mm"] > 0.1]
    assert len(rainy_slots) >= 2
    # y los íconos de esas franjas no contradicen la lluvia
    assert all(e["icon"] not in ("clear-day", "clear-night") for e in rainy_slots)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_hourly_slots_carry_gusts_and_convective_risk(async_client: AsyncClient):
    hourly = _make_hourly(
        wind_gusts_kmh={16: 55.5, 17: 40.0, 18: 30.0},
        cape_j_kg={16: 900.0, 17: 3200.0, 18: 1200.0},
    )

    with _dashboard_mocks(hourly=hourly):
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    today = datetime.now(AR).date().isoformat()
    slot = next(
        e for e in response.json()["hourly"]["entries"] if e["date"] == today and e["hour_label"] == "18:00"
    )
    assert slot["wind_gusts_kmh"] == pytest.approx(55.5)
    assert slot["convective_risk"] == "high"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_timestamps_are_real_instants(async_client: AsyncClient):
    """Cada franja lleva su instante real (no el del reloj del servidor): las 18:00 de Argentina son las 21:00 UTC."""
    with _dashboard_mocks():
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    today = datetime.now(AR).date()
    slot = next(
        e for e in response.json()["hourly"]["entries"]
        if e["date"] == today.isoformat() and e["hour_label"] == "18:00"
    )
    expected = datetime(today.year, today.month, today.day, 21, 0, tzinfo=timezone.utc)
    assert slot["timestamp"] == int(expected.timestamp())


# ---------------------------------------------------------------------------
# Cota de nieve: la temperatura a 850 hPa sale de Open-Meteo
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_snow_level_uses_the_850hpa_temperature_of_open_meteo(async_client: AsyncClient):
    with _dashboard_mocks(hourly=_make_hourly(temps_850_c={h: 10.0 for h in range(48)})):
        warm = (await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")).json()["snow_level_m"]

    with _dashboard_mocks(hourly=_make_hourly(temps_850_c={h: -5.0 for h in range(48)})):
        cold = (await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")).json()["snow_level_m"]

    assert cold < warm, "un aire más frío a 850 hPa baja la cota de nieve"


# ---------------------------------------------------------------------------
# sources / degraded — FRA-122 fase B
# ---------------------------------------------------------------------------

def _make_current_response_stale() -> WeatherCurrentResponse:
    """Igual a _make_current_response pero con meta.stale=True."""
    base = _make_current_response()
    return base.model_copy(update={"meta": base.meta.model_copy(update={"stale": True})})


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_sources_open_meteo_only_and_not_degraded(async_client: AsyncClient):
    """Open-Meteo es la única fuente; con la observación fresca no hay nada degradado."""
    with _dashboard_mocks():
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    data = response.json()
    assert data["degraded"] is False
    # windy_gfs sigue en la respuesta (compatibilidad) pero no se consulta
    assert data["sources"]["windy_gfs"] == {"available": False, "used": False}
    assert data["sources"]["open_meteo"] == {"available": True, "used": True}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_degraded_when_current_stale(async_client: AsyncClient):
    """current.meta.stale=True degrada el dashboard aunque Open-Meteo esté ok."""
    with _dashboard_mocks(current=_make_current_response_stale()):
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    data = response.json()
    assert data["degraded"] is True
    assert data["current"]["stale"] is True
