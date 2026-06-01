"""Tests de integración para GET /api/weather/dashboard."""
from __future__ import annotations

from datetime import datetime, timezone
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
from app.services.windy import WindyDailyEntry, WindyHourlyEntry


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


def _make_daily_ext(model_name: str = "ecmwf_ifs025") -> DailyForecastDataExt:
    dates = [
        "2026-05-20", "2026-05-21", "2026-05-22",
        "2026-05-23", "2026-05-24", "2026-05-25", "2026-05-26",
    ]
    n = len(dates)
    return DailyForecastDataExt(
        dates=dates,
        day_labels=["miércoles", "jueves", "viernes", "sábado", "domingo", "lunes", "martes"],
        temp_max=[22.0] * n,
        temp_min=[10.0] * n,
        precip_sum=[0.0] * n,
        precip_prob_max=[5.0] * n,
        wind_speed_max=[15.0] * n,
        wind_gusts_max=[25.0] * n,
        humidity_mean=[60.0] * n,
        uv_max=[4.0] * n,
        weather_codes=[0] * n,
        sunrise=["2026-05-20T07:00"] * n,
        sunset=["2026-05-20T18:30"] * n,
        daylight_seconds=[41400.0] * n,  # 11h 30m
    )


def _make_multi_model() -> MultiModelDailyData:
    daily = _make_daily_ext()
    return MultiModelDailyData(
        models={
            "ecmwf_ifs025": daily,
            "gfs_seamless": daily,
            "icon_seamless": daily,
        },
        consensus_pct_per_day=[100.0] * 7,
        rain_consensus_per_day=["all_agree_dry"] * 7,
    )


def _make_hourly() -> HourlyForecastExt:
    n = 48
    timestamps = [1716220800 + i * 3600 for i in range(n)]
    return HourlyForecastExt(
        timestamps=timestamps,
        hour_labels=[f"{i % 24:02d}:00" for i in range(n)],
        dates=["2026-05-20"] * 24 + ["2026-05-21"] * 24,
        temps_c=[18.0] * n,
        precipitations=[0.0] * n,
        precip_probs=[5.0] * n,
        wind_speeds=[12.0] * n,
        weather_codes=[0] * n,
        is_day=[True if 6 <= (i % 24) <= 20 else False for i in range(n)],
    )


# ---------------------------------------------------------------------------
# Test: happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_happy_path(async_client: AsyncClient):
    """Debe retornar 200 con todos los campos requeridos."""
    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_make_current_response()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=_make_multi_model()),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=_make_hourly()),
    ):
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
    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_make_current_response()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=_make_multi_model()),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=_make_hourly()),
    ):
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    data = response.json()
    assert data["location"]["lat"] == pytest.approx(-31.4)
    assert data["location"]["lon"] == pytest.approx(-64.2)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_current_fields(async_client: AsyncClient):
    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_make_current_response()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=_make_multi_model()),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=_make_hourly()),
    ):
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
    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_make_current_response()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=_make_multi_model()),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=_make_hourly()),
    ):
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    moon = response.json()["moon_phase"]
    assert "name" in moon
    assert "illumination" in moon
    assert "icon" in moon
    assert 0.0 <= moon["illumination"] <= 1.0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_day_arc_shape(async_client: AsyncClient):
    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_make_current_response()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=_make_multi_model()),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=_make_hourly()),
    ):
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
    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_make_current_response()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=_make_multi_model()),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=_make_hourly()),
    ):
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    forecast = response.json()["forecast_7d"]
    assert len(forecast) == 7


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_forecast_7d_entry_shape(async_client: AsyncClient):
    """Cada entrada del forecast debe tener los campos esperados."""
    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_make_current_response()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=_make_multi_model()),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=_make_hourly()),
    ):
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
    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_make_current_response()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=_make_multi_model()),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=_make_hourly()),
    ):
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    for entry in response.json()["forecast_7d"]:
        assert entry["confidence_label"] in ("ALTA", "MEDIA", "BAJA")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_hourly_entries(async_client: AsyncClient):
    """hourly.entries debe tener registros con los campos correctos."""
    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_make_current_response()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=_make_multi_model()),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=_make_hourly()),
    ):
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    hourly = response.json()["hourly"]
    assert "entries" in hourly
    assert "rain_consensus_label" in hourly
    assert "rain_probability_pct" in hourly
    assert len(hourly["entries"]) == 48
    entry = hourly["entries"][0]
    assert "timestamp" in entry
    assert "hour_label" in entry
    assert "icon" in entry


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_rain_today_shape(async_client: AsyncClient):
    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_make_current_response()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=_make_multi_model()),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=_make_hourly()),
    ):
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    rain = response.json()["rain_today"]
    assert "status_text" in rain
    assert "has_rain_today" in rain
    assert "confidence_label" in rain
    assert rain["confidence_label"] in ("alta", "media", "baja")


# ---------------------------------------------------------------------------
# Test: 503 cuando current falla
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
async def test_dashboard_503_when_om_and_windy_both_fail(async_client: AsyncClient):
    """503 solo cuando TANTO Open-Meteo COMO Windy fallan (sin datos de pronóstico)."""
    # disable_windy_by_default fixture deja windy_api_key="" → _safe_windy_daily devuelve None
    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_make_current_response()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=None),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=_make_hourly()),
    ):
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    assert response.status_code == 503


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_200_when_om_fails_but_windy_available(
    async_client: AsyncClient, monkeypatch
):
    """Cuando Open-Meteo falla (ej. 429) pero Windy está disponible, debe retornar 200
    usando el fallback sintético (weather codes heurísticos + sunrise/sunset astronómico)."""
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "windy_api_key", "fake-key", raising=False)

    windy_daily = _make_windy_daily_ext()
    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_make_current_response()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=None),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=None),
        patch("app.routers.weather.windy_get_hourly_forecast", new_callable=AsyncMock, return_value=_make_windy_hourly_ext()),
        patch("app.routers.weather.windy_get_daily_forecast", new_callable=AsyncMock, return_value=windy_daily),
    ):
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    assert response.status_code == 200
    data = response.json()
    assert len(data["forecast_7d"]) == 7
    # Fallback sintético: temp_max viene de Windy (23.0)
    assert data["forecast_7d"][0]["temp_max"] == pytest.approx(23.0)
    # DayArc debe tener sunrise/sunset calculados astronómicamente
    assert "sunrise" in data["day_arc"]
    assert "sunset" in data["day_arc"]
    assert "h" in data["day_arc"]["daylight_label"]


# ---------------------------------------------------------------------------
# Test: hourly opcional — si falla, el dashboard igualmente devuelve 200
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_200_when_hourly_unavailable(async_client: AsyncClient):
    """Si el horario falla, el dashboard no bloquea — hourly.entries queda vacío."""
    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_make_current_response()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=_make_multi_model()),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=None),
    ):
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    assert response.status_code == 200
    data = response.json()
    assert data["hourly"]["entries"] == []
    assert data["hourly"]["rain_consensus_label"] == "Sin datos"


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
    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_make_current_response()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=single_model),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=_make_hourly()),
    ):
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    assert response.status_code == 200
    assert len(response.json()["forecast_7d"]) == 7


# ---------------------------------------------------------------------------
# Windy GFS integration tests
# ---------------------------------------------------------------------------

def _make_windy_hourly_ext() -> list[WindyHourlyEntry]:
    base_ts_ms = 1716220800 * 1000  # alineado con _make_hourly()
    out: list[WindyHourlyEntry] = []
    for i in range(16):  # 16 slots de 3h ≈ 48h
        ts_ms = base_ts_ms + i * 3 * 3600 * 1000
        out.append(
            WindyHourlyEntry(
                timestamp_ms=ts_ms,
                timestamp_s=ts_ms // 1000,
                date="2026-05-20" if i < 8 else "2026-05-21",
                hour_label=f"{(i * 3) % 24:02d}:00",
                temp_c=19.0,
                humidity=58.0,
                wind_speed_kmh=14.0,
                wind_gust_kmh=22.0,
                wind_dir_deg=180.0,
                wind_dir_cardinal="S",
                precip_3h_mm=0.0,
                cloud_cover_pct=25.0,
                dewpoint_c=11.0,
                temp_850_c=5.0,
            )
        )
    return out


def _make_windy_daily_ext() -> list[WindyDailyEntry]:
    dates = [
        "2026-05-20", "2026-05-21", "2026-05-22",
        "2026-05-23", "2026-05-24", "2026-05-25", "2026-05-26",
    ]
    return [
        WindyDailyEntry(
            date=d,
            temp_max_c=23.0,
            temp_min_c=11.0,
            humidity_mean=58.0,
            wind_speed_max_kmh=18.0,
            wind_speed_mean_kmh=12.0,
            wind_gust_max_kmh=27.0,
            wind_dir_cardinal="S",
            precip_sum_mm=0.0,
            precip_prob=0.0,
            cloud_cover_mean=25.0,
        )
        for d in dates
    ]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_uses_windy_when_available(
    async_client: AsyncClient, monkeypatch
):
    """Cuando Windy GFS está disponible, forecast_source debe reflejarlo."""
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "windy_api_key", "fake-key", raising=False)

    windy_hourly = _make_windy_hourly_ext()
    windy_daily = _make_windy_daily_ext()
    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_make_current_response()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=_make_multi_model()),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=_make_hourly()),
        patch("app.routers.weather.windy_get_hourly_forecast", new_callable=AsyncMock, return_value=windy_hourly),
        patch("app.routers.weather.windy_get_daily_forecast", new_callable=AsyncMock, return_value=windy_daily),
    ):
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    assert response.status_code == 200
    data = response.json()
    # Con Windy disponible la fuente es 'mixed' (Windy datos + OM weather codes)
    assert data["forecast_source"] == "mixed"
    # temp_max viene de OM (primario para agregados nativos del modelo), no de Windy (max snapshots 3h)
    assert data["forecast_7d"][0]["temp_max"] == pytest.approx(22.0)
    # precip_prob viene de OM (Windy no tiene este campo nativo); fixture OM = 5.0
    assert data["forecast_7d"][0]["precip_prob"] == pytest.approx(5.0)
    # precip_sum viene de Windy (mayor resolución temporal 3h); fixture Windy = 0.0
    assert data["forecast_7d"][0]["precip_sum"] == pytest.approx(0.0)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_falls_back_to_openmeteo_when_windy_fails(
    async_client: AsyncClient, monkeypatch
):
    """Si Windy falla, el dashboard usa Open-Meteo como pronóstico."""
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "windy_api_key", "fake-key", raising=False)

    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_make_current_response()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=_make_multi_model()),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=_make_hourly()),
        patch("app.routers.weather.windy_get_hourly_forecast", new_callable=AsyncMock, side_effect=RuntimeError("windy 500")),
        patch("app.routers.weather.windy_get_daily_forecast", new_callable=AsyncMock, side_effect=RuntimeError("windy 500")),
    ):
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    assert response.status_code == 200
    data = response.json()
    assert data["forecast_source"] == "openmeteo_fallback"
    # OM temp_max = 22.0
    assert data["forecast_7d"][0]["temp_max"] == pytest.approx(22.0)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_default_source_is_openmeteo_when_windy_not_configured(
    async_client: AsyncClient,
):
    """Sin API key Windy, el dashboard usa Open-Meteo."""
    # disable_windy_by_default ya pone windy_api_key vacío
    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_make_current_response()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=_make_multi_model()),
        patch("app.routers.weather.get_hourly_forecast_ext", new_callable=AsyncMock, return_value=_make_hourly()),
    ):
        response = await async_client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")

    assert response.status_code == 200
    assert response.json()["forecast_source"] == "openmeteo_fallback"
