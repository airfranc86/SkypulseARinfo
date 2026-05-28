"""Tests de integración para el router GET /api/tools/*."""
from __future__ import annotations

import pytest
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient

from app.schemas.weather import WeatherCurrentResponse, SourceMeta
from app.services.openmeteo import HourlyForecastData
from app.services.windy import (
    WindyDailyEntry,
    WindyHourlyEntry,
    WindyNotConfiguredError,
)


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

def _make_weather_response(
    temp_c: float = 22.0,
    humidity: float = 55.0,
    wind_speed_kmh: float = 15.0,
) -> WeatherCurrentResponse:
    meta = SourceMeta(
        source="openmeteo",
        reason="smn_unavailable",
        station=None,
        fetched_at=datetime.now(timezone.utc),
        cache_hit=False,
    )
    return WeatherCurrentResponse(
        lat=-34.6,
        lon=-58.4,
        temp_c=temp_c,
        feels_like_c=None,
        humidity=humidity,
        wind_speed_kmh=wind_speed_kmh,
        wind_dir_deg=270.0,
        wind_dir_cardinal="W",
        pressure_hpa=1013.0,
        precip_1h_mm=0.0,
        cloud_cover=None,
        description="Despejado",
        meta=meta,
    )


def _make_hourly_forecast(
    n: int = 48,
    temp_c: float = 22.0,
    humidity: float = 55.0,
    precip: float = 0.0,
    wind_speed: float = 15.0,
    temp_850: float | None = 8.0,
    elevation_m: float = 25.0,
) -> HourlyForecastData:
    """Construye un HourlyForecastData sintético con n horas."""
    base_ts = int(time.time()) + 3600  # 1h en el futuro — _filter_future conserva todos los slots
    base_hour = datetime.fromtimestamp(base_ts, tz=timezone.utc).hour
    timestamps = [base_ts + i * 3600 for i in range(n)]
    hour_labels = [f"{(base_hour + i) % 24:02d}:00" for i in range(n)]
    return HourlyForecastData(
        timestamps=timestamps,
        hour_labels=hour_labels,
        temps_c=[temp_c] * n,
        humidities=[humidity] * n,
        precipitations=[precip] * n,
        wind_speeds_kmh=[wind_speed] * n,
        temps_850hpa=[temp_850] * n,
        elevation_m=elevation_m,
    )


# ---------------------------------------------------------------------------
# /api/tools/tender-ropa
# ---------------------------------------------------------------------------

class TestTenderRopa:

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_happy_path_returns_200(self, async_client: AsyncClient):
        """Datos de forecast completos → 200 con ToolResult válido."""
        forecast = _make_hourly_forecast(
            temp_c=25.0, humidity=50.0, precip=0.0, wind_speed=15.0
        )
        with patch(
            "app.routers.tools.get_hourly_forecast",
            new_callable=AsyncMock,
            return_value=forecast,
        ):
            response = await async_client.get(
                "/api/tools/tender-ropa?lat=-34.6&lon=-58.4"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["tool"] == "tender-ropa"
        assert data["score"] >= 0
        assert data["label"] in ("Excelente", "Bueno", "Regular", "No apto")
        assert data["color"] in ("green", "yellow", "red")
        assert data["headline"]
        assert data["reason"]
        assert isinstance(data["hourly"], list)
        assert len(data["hourly"]) == 24

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_hourly_has_is_best_flag(self, async_client: AsyncClient):
        """Al menos una hora debe tener is_best=True si hay puntajes altos."""
        forecast = _make_hourly_forecast(
            temp_c=25.0, humidity=50.0, precip=0.0, wind_speed=15.0
        )
        with patch(
            "app.routers.tools.get_hourly_forecast",
            new_callable=AsyncMock,
            return_value=forecast,
        ):
            response = await async_client.get(
                "/api/tools/tender-ropa?lat=-34.6&lon=-58.4"
            )

        data = response.json()
        best_hours = [h for h in data["hourly"] if h["is_best"]]
        assert len(best_hours) >= 1

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_forecast_none_returns_503(self, async_client: AsyncClient):
        """Cuando forecast retorna None → 503 con detail='forecast_unavailable'."""
        with patch(
            "app.routers.tools.get_hourly_forecast",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = await async_client.get(
                "/api/tools/tender-ropa?lat=-34.6&lon=-58.4"
            )

        assert response.status_code == 503
        assert response.json()["detail"] == "forecast_unavailable"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_outside_argentina_returns_422(self, async_client: AsyncClient):
        """lat=-60 está fuera de Argentina → 422."""
        response = await async_client.get("/api/tools/tender-ropa?lat=-60&lon=-58.4")
        assert response.status_code == 422
        assert response.json()["error"] == "outside_argentina"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_missing_params_returns_422(self, async_client: AsyncClient):
        """Sin lat ni lon → 422."""
        response = await async_client.get("/api/tools/tender-ropa")
        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_best_window_present_when_high_score(self, async_client: AsyncClient):
        """Con condiciones ideales, best_window debe estar presente."""
        forecast = _make_hourly_forecast(
            temp_c=25.0, humidity=50.0, precip=0.0, wind_speed=15.0
        )
        with patch(
            "app.routers.tools.get_hourly_forecast",
            new_callable=AsyncMock,
            return_value=forecast,
        ):
            response = await async_client.get(
                "/api/tools/tender-ropa?lat=-34.6&lon=-58.4"
            )

        data = response.json()
        # Con score >= 70 en todas las horas, debe haber best_window
        assert data["best_window"] is not None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_best_window_none_when_all_low_score(self, async_client: AsyncClient):
        """Con condiciones malas en todas las horas, best_window = None."""
        forecast = _make_hourly_forecast(
            temp_c=5.0, humidity=90.0, precip=5.0, wind_speed=30.0
        )
        with patch(
            "app.routers.tools.get_hourly_forecast",
            new_callable=AsyncMock,
            return_value=forecast,
        ):
            response = await async_client.get(
                "/api/tools/tender-ropa?lat=-34.6&lon=-58.4"
            )

        data = response.json()
        assert data["best_window"] is None


# ---------------------------------------------------------------------------
# /api/tools/sensacion-termica
# ---------------------------------------------------------------------------

class TestSensacionTermica:

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_verano_returns_heat_index(self, async_client: AsyncClient):
        """Condiciones de verano (temp > 26, humidity > 40) → formula=heat_index."""
        weather = _make_weather_response(temp_c=30.0, humidity=70.0, wind_speed_kmh=5.0)
        with patch(
            "app.routers.tools.aggregate_current",
            new_callable=AsyncMock,
            return_value=weather,
        ):
            response = await async_client.get(
                "/api/tools/sensacion-termica?lat=-34.6&lon=-58.4"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["formula"] == "heat_index"
        assert data["feels_like_c"] > 30.0
        assert data["temp_c"] == pytest.approx(30.0)
        assert data["description"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_invierno_returns_wind_chill(self, async_client: AsyncClient):
        """Condiciones de invierno → formula=wind_chill."""
        weather = _make_weather_response(temp_c=5.0, humidity=80.0, wind_speed_kmh=25.0)
        with patch(
            "app.routers.tools.aggregate_current",
            new_callable=AsyncMock,
            return_value=weather,
        ):
            response = await async_client.get(
                "/api/tools/sensacion-termica?lat=-34.6&lon=-58.4"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["formula"] == "wind_chill"
        assert data["feels_like_c"] < 5.0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_temp_none_returns_503(self, async_client: AsyncClient):
        """Cuando temp_c es None → 503 weather_unavailable."""
        from fastapi import HTTPException
        with patch(
            "app.routers.tools.aggregate_current",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=503, detail="all_sources_unavailable"),
        ):
            response = await async_client.get(
                "/api/tools/sensacion-termica?lat=-34.6&lon=-58.4"
            )

        assert response.status_code == 503

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_outside_argentina_returns_422(self, async_client: AsyncClient):
        """Coordenadas fuera de Argentina → 422."""
        response = await async_client.get(
            "/api/tools/sensacion-termica?lat=-60&lon=-58.4"
        )
        assert response.status_code == 422
        assert response.json()["error"] == "outside_argentina"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_neutral_conditions_formula_none(self, async_client: AsyncClient):
        """Condiciones neutras → formula=none."""
        weather = _make_weather_response(temp_c=20.0, humidity=50.0, wind_speed_kmh=5.0)
        with patch(
            "app.routers.tools.aggregate_current",
            new_callable=AsyncMock,
            return_value=weather,
        ):
            response = await async_client.get(
                "/api/tools/sensacion-termica?lat=-34.6&lon=-58.4"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["formula"] == "none"
        assert data["feels_like_c"] == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# /api/tools/cota-de-nieve
# ---------------------------------------------------------------------------

class TestCotaDeNieve:

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_andina_returns_three_methods(self, async_client: AsyncClient):
        """Zona andina con temp_850 disponible → 3 métodos + average."""
        forecast = _make_hourly_forecast(
            temp_c=10.0, humidity=60.0, precip=0.0, wind_speed=10.0,
            temp_850=5.0, elevation_m=750.0,
        )
        weather = _make_weather_response(temp_c=10.0)
        with patch(
            "app.routers.tools.get_hourly_forecast",
            new_callable=AsyncMock,
            return_value=forecast,
        ), patch(
            "app.routers.tools.aggregate_current",
            new_callable=AsyncMock,
            return_value=weather,
        ):
            response = await async_client.get(
                "/api/tools/cota-de-nieve?lat=-38.0&lon=-70.0"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["alcaide_m"] >= 0
        assert data["gradiente_m"] >= 0
        assert data["m850_hpa_m"] is not None
        assert data["average_m"] >= 0
        assert data["description"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_weather_unavailable_returns_503(self, async_client: AsyncClient):
        """Cuando weather falla → 503."""
        from fastapi import HTTPException
        forecast = _make_hourly_forecast()
        with patch(
            "app.routers.tools.get_hourly_forecast",
            new_callable=AsyncMock,
            return_value=forecast,
        ), patch(
            "app.routers.tools.aggregate_current",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=503, detail="all_sources_unavailable"),
        ):
            response = await async_client.get(
                "/api/tools/cota-de-nieve?lat=-38.0&lon=-70.0"
            )

        assert response.status_code == 503

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_outside_argentina_returns_422(self, async_client: AsyncClient):
        """Coordenadas fuera de Argentina → 422."""
        response = await async_client.get(
            "/api/tools/cota-de-nieve?lat=-20&lon=-70.0"
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_elevation_none_uses_zero(self, async_client: AsyncClient):
        """Si elevation_m es None en el forecast, station_altitude_m = 0.0."""
        forecast = _make_hourly_forecast(elevation_m=None)
        # Need to rebuild with elevation_m None
        import dataclasses
        forecast = dataclasses.replace(forecast, elevation_m=None)
        weather = _make_weather_response(temp_c=15.0)
        with patch(
            "app.routers.tools.get_hourly_forecast",
            new_callable=AsyncMock,
            return_value=forecast,
        ), patch(
            "app.routers.tools.aggregate_current",
            new_callable=AsyncMock,
            return_value=weather,
        ):
            response = await async_client.get(
                "/api/tools/cota-de-nieve?lat=-34.6&lon=-58.4"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["station_altitude_m"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# /api/tools/hacer-deporte
# ---------------------------------------------------------------------------

class TestHacerDeporte:

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_happy_path_returns_200(self, async_client: AsyncClient):
        """Condiciones favorables → 200 con ToolResult válido."""
        forecast = _make_hourly_forecast(
            temp_c=20.0, humidity=50.0, precip=0.0, wind_speed=10.0
        )
        with patch(
            "app.routers.tools.get_hourly_forecast",
            new_callable=AsyncMock,
            return_value=forecast,
        ):
            response = await async_client.get(
                "/api/tools/hacer-deporte?lat=-34.6&lon=-58.4"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["tool"] == "hacer-deporte"
        assert data["score"] >= 0
        assert data["label"] in ("Excelente", "Bueno", "Regular", "No apto")
        assert isinstance(data["hourly"], list)
        assert len(data["hourly"]) == 12

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_forecast_none_returns_503(self, async_client: AsyncClient):
        """Forecast None → 503."""
        with patch(
            "app.routers.tools.get_hourly_forecast",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = await async_client.get(
                "/api/tools/hacer-deporte?lat=-34.6&lon=-58.4"
            )

        assert response.status_code == 503
        assert response.json()["detail"] == "forecast_unavailable"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_outside_argentina_returns_422(self, async_client: AsyncClient):
        """Coordenadas fuera de Argentina → 422."""
        response = await async_client.get(
            "/api/tools/hacer-deporte?lat=-60&lon=-58.4"
        )
        assert response.status_code == 422
        assert response.json()["error"] == "outside_argentina"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_best_window_when_high_score(self, async_client: AsyncClient):
        """Con score alto, best_window debe ser la mejor hora."""
        forecast = _make_hourly_forecast(
            temp_c=20.0, humidity=50.0, precip=0.0, wind_speed=10.0
        )
        with patch(
            "app.routers.tools.get_hourly_forecast",
            new_callable=AsyncMock,
            return_value=forecast,
        ):
            response = await async_client.get(
                "/api/tools/hacer-deporte?lat=-34.6&lon=-58.4"
            )

        data = response.json()
        # Con score >= 40, best_window debe existir (formato "A las HH:MM")
        assert data["best_window"] is not None
        assert "A las" in data["best_window"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_best_window_none_when_all_low(self, async_client: AsyncClient):
        """Con score < 40 en todas las horas, best_window = None."""
        forecast = _make_hourly_forecast(
            temp_c=5.0, humidity=90.0, precip=5.0, wind_speed=30.0
        )
        with patch(
            "app.routers.tools.get_hourly_forecast",
            new_callable=AsyncMock,
            return_value=forecast,
        ):
            response = await async_client.get(
                "/api/tools/hacer-deporte?lat=-34.6&lon=-58.4"
            )

        data = response.json()
        assert data["best_window"] is None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_hourly_has_is_best_flag(self, async_client: AsyncClient):
        """Exactamente una hora tiene is_best=True (la de mayor score)."""
        forecast = _make_hourly_forecast(
            temp_c=20.0, humidity=50.0, precip=0.0, wind_speed=10.0
        )
        with patch(
            "app.routers.tools.get_hourly_forecast",
            new_callable=AsyncMock,
            return_value=forecast,
        ):
            response = await async_client.get(
                "/api/tools/hacer-deporte?lat=-34.6&lon=-58.4"
            )

        data = response.json()
        best_hours = [h for h in data["hourly"] if h["is_best"]]
        assert len(best_hours) == 1


# ---------------------------------------------------------------------------
# Rate limiting (compartido entre endpoints)
# ---------------------------------------------------------------------------

class TestRateLimiting:

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rate_limit_returns_429(self, async_client: AsyncClient):
        """Más de 30 requests por minuto → 429."""
        forecast = _make_hourly_forecast()
        with patch(
            "app.routers.tools.get_hourly_forecast",
            new_callable=AsyncMock,
            return_value=forecast,
        ):
            responses = []
            for _ in range(35):
                r = await async_client.get(
                    "/api/tools/tender-ropa?lat=-34.6&lon=-58.4"
                )
                responses.append(r.status_code)

        assert 429 in responses


# ---------------------------------------------------------------------------
# Helpers: factories de Windy
# ---------------------------------------------------------------------------

def _make_windy_hourly(n: int = 12) -> list[WindyHourlyEntry]:
    """Slots horarios sintéticos de Windy con condiciones favorables."""
    base_ts_ms = 1747742400000  # 2026-05-20 12:00 UTC
    out: list[WindyHourlyEntry] = []
    for i in range(n):
        ts_ms = base_ts_ms + i * 3 * 3600 * 1000  # cada 3h
        out.append(
            WindyHourlyEntry(
                timestamp_ms=ts_ms,
                timestamp_s=ts_ms // 1000,
                date="2026-05-20" if i < 5 else "2026-05-21",
                hour_label=f"{(9 + i * 3) % 24:02d}:00",
                temp_c=20.0,
                humidity=55.0,
                wind_speed_kmh=12.0,
                wind_gust_kmh=20.0,
                wind_dir_deg=180.0,
                wind_dir_cardinal="S",
                precip_3h_mm=0.0,
                cloud_cover_pct=20.0,
                dewpoint_c=10.0,
                temp_850_c=5.0,
            )
        )
    return out


def _make_windy_daily(n: int = 5) -> list[WindyDailyEntry]:
    """Días sintéticos de Windy con condiciones favorables para lavar coche."""
    from datetime import date, timedelta
    base = date(2026, 5, 20)
    out: list[WindyDailyEntry] = []
    for i in range(n):
        out.append(
            WindyDailyEntry(
                date=(base + timedelta(days=i)).isoformat(),
                temp_max_c=24.0,
                temp_min_c=14.0,
                humidity_mean=55.0,
                wind_speed_max_kmh=18.0,
                wind_speed_mean_kmh=12.0,
                wind_gust_max_kmh=28.0,
                wind_dir_cardinal="S",
                precip_sum_mm=0.0,
                precip_prob=0.0,
                cloud_cover_mean=20.0,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Tests: Windy primary path para hacer-deporte, lavar-coche, cota-de-nieve
# ---------------------------------------------------------------------------

class TestHacerDeporteWindyPath:
    """Cuando Windy GFS está disponible, los endpoints deben preferirlo."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_uses_windy_when_available(
        self, async_client: AsyncClient, monkeypatch
    ):
        import app.core.config as cfg
        monkeypatch.setattr(cfg.settings, "windy_api_key", "fake-key", raising=False)

        windy_hourly = _make_windy_hourly(12)
        with patch(
            "app.routers.tools.windy_get_hourly_forecast",
            new_callable=AsyncMock,
            return_value=windy_hourly,
        ):
            response = await async_client.get(
                "/api/tools/hacer-deporte?lat=-34.6&lon=-58.4"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "windy_gfs"
        assert data["tool"] == "hacer-deporte"
        assert len(data["hourly"]) <= 12

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_falls_back_to_openmeteo_when_windy_errors(
        self, async_client: AsyncClient, monkeypatch
    ):
        import app.core.config as cfg
        monkeypatch.setattr(cfg.settings, "windy_api_key", "fake-key", raising=False)

        forecast = _make_hourly_forecast(temp_c=20.0, humidity=50.0, precip=0.0)
        with patch(
            "app.routers.tools.windy_get_hourly_forecast",
            new_callable=AsyncMock,
            side_effect=RuntimeError("windy down"),
        ), patch(
            "app.routers.tools.get_hourly_forecast",
            new_callable=AsyncMock,
            return_value=forecast,
        ):
            response = await async_client.get(
                "/api/tools/hacer-deporte?lat=-34.6&lon=-58.4"
            )

        assert response.status_code == 200
        assert response.json()["source"] == "openmeteo_fallback"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_uses_openmeteo_when_windy_not_configured(
        self, async_client: AsyncClient
    ):
        # disable_windy_by_default ya garantiza windy_api_key vacío
        forecast = _make_hourly_forecast(temp_c=20.0, humidity=50.0, precip=0.0)
        with patch(
            "app.routers.tools.get_hourly_forecast",
            new_callable=AsyncMock,
            return_value=forecast,
        ):
            response = await async_client.get(
                "/api/tools/hacer-deporte?lat=-34.6&lon=-58.4"
            )

        assert response.status_code == 200
        assert response.json()["source"] == "openmeteo_fallback"


class TestLavarCocheWindyPath:

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_uses_windy_when_available(
        self, async_client: AsyncClient, monkeypatch
    ):
        import app.core.config as cfg
        monkeypatch.setattr(cfg.settings, "windy_api_key", "fake-key", raising=False)

        windy_daily = _make_windy_daily(5)
        with patch(
            "app.routers.tools.windy_get_daily_forecast",
            new_callable=AsyncMock,
            return_value=windy_daily,
        ):
            response = await async_client.get(
                "/api/tools/lavar-coche?lat=-34.6&lon=-58.4"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "windy_gfs"
        assert len(data["days"]) == 5
        # Exactamente un día marcado como best
        best = [d for d in data["days"] if d["is_best"]]
        assert len(best) == 1

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_falls_back_to_openmeteo_when_windy_errors(
        self, async_client: AsyncClient, monkeypatch
    ):
        import app.core.config as cfg
        monkeypatch.setattr(cfg.settings, "windy_api_key", "fake-key", raising=False)

        from app.services.openmeteo import DailyForecastData
        daily = DailyForecastData(
            dates=["2026-05-20", "2026-05-21", "2026-05-22", "2026-05-23", "2026-05-24"],
            day_labels=["miércoles", "jueves", "viernes", "sábado", "domingo"],
            temp_max=[22.0] * 5,
            temp_min=[12.0] * 5,
            precip_sum=[0.0] * 5,
            wind_speed_max=[15.0] * 5,
            humidity_mean=[55.0] * 5,
        )
        with patch(
            "app.routers.tools.windy_get_daily_forecast",
            new_callable=AsyncMock,
            side_effect=RuntimeError("windy 500"),
        ), patch(
            "app.routers.tools.get_daily_forecast",
            new_callable=AsyncMock,
            return_value=daily,
        ):
            response = await async_client.get(
                "/api/tools/lavar-coche?lat=-34.6&lon=-58.4"
            )

        assert response.status_code == 200
        assert response.json()["source"] == "openmeteo_fallback"


class TestCotaDeNieveWindyPath:

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_uses_windy_for_temp_850(
        self, async_client: AsyncClient, monkeypatch
    ):
        import app.core.config as cfg
        monkeypatch.setattr(cfg.settings, "windy_api_key", "fake-key", raising=False)

        forecast = _make_hourly_forecast(temp_850=None, elevation_m=750.0)
        weather = _make_weather_response(temp_c=10.0)
        with patch(
            "app.routers.tools.windy_get_temp_850",
            new_callable=AsyncMock,
            return_value=4.5,
        ), patch(
            "app.routers.tools.aggregate_current",
            new_callable=AsyncMock,
            return_value=weather,
        ), patch(
            "app.routers.tools.get_hourly_forecast",
            new_callable=AsyncMock,
            return_value=forecast,
        ):
            response = await async_client.get(
                "/api/tools/cota-de-nieve?lat=-38.0&lon=-70.0"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "windy_gfs"
        assert data["m850_hpa_m"] is not None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_falls_back_to_openmeteo_when_windy_errors(
        self, async_client: AsyncClient, monkeypatch
    ):
        import app.core.config as cfg
        monkeypatch.setattr(cfg.settings, "windy_api_key", "fake-key", raising=False)

        forecast = _make_hourly_forecast(temp_850=5.0, elevation_m=750.0)
        weather = _make_weather_response(temp_c=10.0)
        with patch(
            "app.routers.tools.windy_get_temp_850",
            new_callable=AsyncMock,
            side_effect=RuntimeError("windy timeout"),
        ), patch(
            "app.routers.tools.aggregate_current",
            new_callable=AsyncMock,
            return_value=weather,
        ), patch(
            "app.routers.tools.get_hourly_forecast",
            new_callable=AsyncMock,
            return_value=forecast,
        ):
            response = await async_client.get(
                "/api/tools/cota-de-nieve?lat=-38.0&lon=-70.0"
            )

        assert response.status_code == 200
        assert response.json()["source"] == "openmeteo_fallback"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_source_unavailable_when_temp_850_missing(
        self, async_client: AsyncClient
    ):
        """Sin Windy y sin temp_850 en OM → source = unavailable."""
        forecast = _make_hourly_forecast(temp_850=None, elevation_m=750.0)
        # temp_850 None se replica vía dataclasses.replace para evitar list[None]
        import dataclasses
        forecast = dataclasses.replace(forecast, temps_850hpa=[None] * len(forecast.temps_850hpa))
        weather = _make_weather_response(temp_c=10.0)
        with patch(
            "app.routers.tools.aggregate_current",
            new_callable=AsyncMock,
            return_value=weather,
        ), patch(
            "app.routers.tools.get_hourly_forecast",
            new_callable=AsyncMock,
            return_value=forecast,
        ):
            response = await async_client.get(
                "/api/tools/cota-de-nieve?lat=-38.0&lon=-70.0"
            )

        assert response.status_code == 200
        data = response.json()
        # Sin temp_850 disponible → source unavailable
        assert data["source"] == "unavailable"
        assert data["m850_hpa_m"] is None
