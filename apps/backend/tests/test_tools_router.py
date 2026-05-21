"""Tests de integración para el router GET /api/tools/*."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient

from app.schemas.weather import WeatherCurrentResponse, SourceMeta
from app.services.openmeteo import HourlyForecastData


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
    base_ts = 1705320000  # 2024-01-15T14:00 UTC
    timestamps = [base_ts + i * 3600 for i in range(n)]
    hour_labels = [f"{(14 + i) % 24:02d}:00" for i in range(n)]
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
