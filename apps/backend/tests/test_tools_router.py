"""Tests de integración para el router GET /api/tools/*.

Las herramientas salen de la serie horaria de Open-Meteo (la misma del dashboard).
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.schemas.weather import SourceMeta, WeatherCurrentResponse
from tests.hourly_fixtures import make_uniform_hourly

HOURLY = "app.routers.tools.get_hourly_forecast_ext"


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


def _patch_hourly(forecast):
    return patch(HOURLY, new_callable=AsyncMock, return_value=forecast)


# ---------------------------------------------------------------------------
# /api/tools/tender-ropa
# ---------------------------------------------------------------------------

class TestTenderRopa:

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_happy_path_returns_200(self, async_client: AsyncClient):
        """Datos de forecast completos → 200 con ToolResult válido."""
        forecast = make_uniform_hourly(temp_c=25.0, humidity=50.0, precip=0.0, wind=15.0)
        with _patch_hourly(forecast):
            response = await async_client.get("/api/tools/tender-ropa?lat=-34.6&lon=-58.4")

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
    async def test_source_is_open_meteo(self, async_client: AsyncClient):
        with _patch_hourly(make_uniform_hourly()):
            response = await async_client.get("/api/tools/tender-ropa?lat=-34.6&lon=-58.4")

        assert response.json()["source"] == "openmeteo"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_hourly_has_is_best_flag(self, async_client: AsyncClient):
        """Al menos una hora debe tener is_best=True si hay puntajes altos."""
        forecast = make_uniform_hourly(temp_c=25.0, humidity=50.0, precip=0.0, wind=15.0)
        with _patch_hourly(forecast):
            response = await async_client.get("/api/tools/tender-ropa?lat=-34.6&lon=-58.4")

        data = response.json()
        best_hours = [h for h in data["hourly"] if h["is_best"]]
        assert len(best_hours) >= 1

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_the_strip_starts_at_the_current_slot_and_is_in_order(self, async_client: AsyncClient):
        with _patch_hourly(make_uniform_hourly()):
            response = await async_client.get("/api/tools/tender-ropa?lat=-34.6&lon=-58.4")

        stamps = [h["timestamp"] for h in response.json()["hourly"]]
        now = datetime.now(timezone.utc).timestamp()
        assert stamps == sorted(stamps)
        assert stamps[0] > now - 1800 - 5      # ninguna franja terminó hace más de media hora
        assert stamps[1] - stamps[0] == 3 * 3600

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_current_conditions_come_from_the_forecast(self, async_client: AsyncClient):
        forecast = make_uniform_hourly(temp_c=27.0, humidity=41.0, wind=12.0, precip=0.5)
        with _patch_hourly(forecast):
            response = await async_client.get("/api/tools/tender-ropa?lat=-34.6&lon=-58.4")

        data = response.json()
        assert data["temp"] == pytest.approx(27.0)
        assert data["humidity"] == pytest.approx(41.0)
        assert data["wind_speed"] == pytest.approx(12.0)
        assert data["precip"] == pytest.approx(3.0)      # 0,5 mm por hora, las próximas 6 h

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_forecast_none_returns_503(self, async_client: AsyncClient):
        """Cuando forecast retorna None → 503 con detail='forecast_unavailable'."""
        with _patch_hourly(None):
            response = await async_client.get("/api/tools/tender-ropa?lat=-34.6&lon=-58.4")

        assert response.status_code == 503
        assert response.json()["detail"] == "forecast_unavailable"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_empty_forecast_returns_503(self, async_client: AsyncClient):
        with _patch_hourly(make_uniform_hourly(hours=0)):
            response = await async_client.get("/api/tools/tender-ropa?lat=-34.6&lon=-58.4")

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
        forecast = make_uniform_hourly(temp_c=25.0, humidity=50.0, precip=0.0, wind=15.0)
        with _patch_hourly(forecast):
            response = await async_client.get("/api/tools/tender-ropa?lat=-34.6&lon=-58.4")

        # Con score >= 70 en todas las franjas, debe haber best_window
        assert response.json()["best_window"] is not None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_best_window_none_when_all_low_score(self, async_client: AsyncClient):
        """Con condiciones malas en todas las franjas, best_window = None."""
        forecast = make_uniform_hourly(temp_c=5.0, humidity=90.0, precip=5.0, wind=30.0)
        with _patch_hourly(forecast):
            response = await async_client.get("/api/tools/tender-ropa?lat=-34.6&lon=-58.4")

        assert response.json()["best_window"] is None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_storm_code_in_the_next_hours_overrides_perfect_conditions(self, async_client: AsyncClient):
        forecast = make_uniform_hourly(temp_c=25.0, humidity=45.0, wind=12.0, weather_code=95)
        with _patch_hourly(forecast):
            response = await async_client.get("/api/tools/tender-ropa?lat=-34.6&lon=-58.4")

        data = response.json()
        assert data["label"] == "No apto"
        assert "tormenta" in data["headline"].lower()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_high_cape_overrides_perfect_conditions(self, async_client: AsyncClient):
        """El CAPE de Open-Meteo (1000 J/kg o más) también vetea, como antes con el de Windy."""
        forecast = make_uniform_hourly(temp_c=25.0, humidity=45.0, wind=12.0, cape=1500.0)
        with _patch_hourly(forecast):
            response = await async_client.get("/api/tools/tender-ropa?lat=-34.6&lon=-58.4")

        assert response.json()["label"] == "No apto"


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
        forecast = make_uniform_hourly(temp_c=10.0, temp_850=5.0, elevation_m=750.0)
        weather = _make_weather_response(temp_c=10.0)
        with _patch_hourly(forecast), patch(
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
        assert data["source"] == "openmeteo"
        assert data["station_altitude_m"] == pytest.approx(750.0)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_uses_the_850_hpa_temperature_of_the_current_hour(self, async_client: AsyncClient):
        forecast = make_uniform_hourly(temp_850=5.0, elevation_m=750.0)
        with _patch_hourly(forecast), patch(
            "app.routers.tools.aggregate_current",
            new_callable=AsyncMock,
            return_value=_make_weather_response(temp_c=10.0),
        ):
            response = await async_client.get("/api/tools/cota-de-nieve?lat=-38.0&lon=-70.0")

        # 1500 m + (5 °C / 6,5 °C/km) = 2269,2 m
        assert response.json()["m850_hpa_m"] == pytest.approx(2269.2, abs=0.1)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_weather_unavailable_returns_503(self, async_client: AsyncClient):
        """Cuando weather falla → 503."""
        from fastapi import HTTPException
        with _patch_hourly(make_uniform_hourly()), patch(
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
        forecast = make_uniform_hourly(elevation_m=None)
        with _patch_hourly(forecast), patch(
            "app.routers.tools.aggregate_current",
            new_callable=AsyncMock,
            return_value=_make_weather_response(temp_c=15.0),
        ):
            response = await async_client.get(
                "/api/tools/cota-de-nieve?lat=-34.6&lon=-58.4"
            )

        assert response.status_code == 200
        assert response.json()["station_altitude_m"] == pytest.approx(0.0)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_source_unavailable_when_temp_850_missing(self, async_client: AsyncClient):
        """Sin temp_850 en Open-Meteo → source = unavailable y solo dos métodos."""
        forecast = make_uniform_hourly(temp_850=None, elevation_m=750.0)
        with _patch_hourly(forecast), patch(
            "app.routers.tools.aggregate_current",
            new_callable=AsyncMock,
            return_value=_make_weather_response(temp_c=10.0),
        ):
            response = await async_client.get(
                "/api/tools/cota-de-nieve?lat=-38.0&lon=-70.0"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "unavailable"
        assert data["m850_hpa_m"] is None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_forecast_down_still_answers_with_the_two_surface_methods(self, async_client: AsyncClient):
        """Si Open-Meteo horario falla, la cota se estima con la temperatura actual y altitud 0."""
        with _patch_hourly(None), patch(
            "app.routers.tools.aggregate_current",
            new_callable=AsyncMock,
            return_value=_make_weather_response(temp_c=10.0),
        ):
            response = await async_client.get("/api/tools/cota-de-nieve?lat=-38.0&lon=-70.0")

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "unavailable"
        assert data["m850_hpa_m"] is None
        assert data["station_altitude_m"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# /api/tools/hacer-deporte
# ---------------------------------------------------------------------------

class TestHacerDeporte:

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_happy_path_returns_200(self, async_client: AsyncClient):
        """Condiciones favorables → 200 con ToolResult válido."""
        forecast = make_uniform_hourly(temp_c=20.0, humidity=50.0, precip=0.0, wind=10.0)
        with _patch_hourly(forecast):
            response = await async_client.get("/api/tools/hacer-deporte?lat=-34.6&lon=-58.4")

        assert response.status_code == 200
        data = response.json()
        assert data["tool"] == "hacer-deporte"
        assert data["score"] >= 0
        assert data["label"] in ("Excelente", "Bueno", "Regular", "No apto")
        assert isinstance(data["hourly"], list)
        assert len(data["hourly"]) == 12
        assert data["source"] == "openmeteo"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_current_conditions_come_from_the_forecast(self, async_client: AsyncClient):
        forecast = make_uniform_hourly(temp_c=19.0, humidity=48.0, wind=9.0, precip=0.0)
        with _patch_hourly(forecast):
            response = await async_client.get("/api/tools/hacer-deporte?lat=-34.6&lon=-58.4")

        data = response.json()
        assert data["temp"] == pytest.approx(19.0)
        assert data["humidity"] == pytest.approx(48.0)
        assert data["wind_speed"] == pytest.approx(9.0)
        assert data["precip"] == pytest.approx(0.0)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_forecast_none_returns_503(self, async_client: AsyncClient):
        """Forecast None → 503."""
        with _patch_hourly(None):
            response = await async_client.get("/api/tools/hacer-deporte?lat=-34.6&lon=-58.4")

        assert response.status_code == 503
        assert response.json()["detail"] == "forecast_unavailable"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_outside_argentina_returns_422(self, async_client: AsyncClient):
        """Coordenadas fuera de Argentina → 422."""
        response = await async_client.get("/api/tools/hacer-deporte?lat=-60&lon=-58.4")
        assert response.status_code == 422
        assert response.json()["error"] == "outside_argentina"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_best_window_when_high_score(self, async_client: AsyncClient):
        """Con score alto, best_window debe ser la mejor hora."""
        forecast = make_uniform_hourly(temp_c=20.0, humidity=50.0, precip=0.0, wind=10.0)
        with _patch_hourly(forecast):
            response = await async_client.get("/api/tools/hacer-deporte?lat=-34.6&lon=-58.4")

        data = response.json()
        # Con score >= 40, best_window debe existir (formato "A las HH:MM")
        assert data["best_window"] is not None
        assert "A las" in data["best_window"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_best_window_none_when_all_low(self, async_client: AsyncClient):
        """Con score < 40 en todas las franjas, best_window = None."""
        forecast = make_uniform_hourly(temp_c=5.0, humidity=90.0, precip=5.0, wind=30.0)
        with _patch_hourly(forecast):
            response = await async_client.get("/api/tools/hacer-deporte?lat=-34.6&lon=-58.4")

        assert response.json()["best_window"] is None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_hourly_has_is_best_flag(self, async_client: AsyncClient):
        """Exactamente una franja tiene is_best=True (la de mayor score)."""
        forecast = make_uniform_hourly(temp_c=20.0, humidity=50.0, precip=0.0, wind=10.0)
        with _patch_hourly(forecast):
            response = await async_client.get("/api/tools/hacer-deporte?lat=-34.6&lon=-58.4")

        best_hours = [h for h in response.json()["hourly"] if h["is_best"]]
        assert len(best_hours) == 1

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_storm_forecast_overrides_perfect_conditions(self, async_client: AsyncClient):
        """
        Cableado end-to-end del veto de tormenta: weather_code=95 en el forecast que llega al router
        debe forzar "No apto" pese a que temperatura/humedad/viento sean ideales — el bug reportado
        en vivo.
        """
        forecast = make_uniform_hourly(temp_c=18.0, humidity=50.0, precip=0.0, wind=10.0, weather_code=95)
        with _patch_hourly(forecast):
            response = await async_client.get("/api/tools/hacer-deporte?lat=-34.6&lon=-58.4")

        data = response.json()
        assert data["label"] == "No apto"
        assert "tormenta" in data["headline"].lower()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_high_cape_overrides_perfect_conditions(self, async_client: AsyncClient):
        forecast = make_uniform_hourly(temp_c=18.0, humidity=50.0, precip=0.0, wind=10.0, cape=1500.0)
        with _patch_hourly(forecast):
            response = await async_client.get("/api/tools/hacer-deporte?lat=-34.6&lon=-58.4")

        assert response.json()["label"] == "No apto"


# ---------------------------------------------------------------------------
# /api/tools/lavar-coche
# ---------------------------------------------------------------------------

class TestLavarCoche:

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_five_days_from_open_meteo_with_one_best(self, async_client: AsyncClient):
        forecast = make_uniform_hourly(temp_c=22.0, humidity=50.0, precip=0.0, wind=10.0)
        with _patch_hourly(forecast):
            response = await async_client.get("/api/tools/lavar-coche?lat=-34.6&lon=-58.4")

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "openmeteo"
        assert len(data["days"]) == 5
        assert len([d for d in data["days"] if d["is_best"]]) == 1

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_a_day_carries_the_totals_and_the_wind_max_of_its_hours(self, async_client: AsyncClient):
        forecast = make_uniform_hourly(temp_c=22.0, humidity=50.0, precip=0.0, wind=18.0)
        with _patch_hourly(forecast):
            response = await async_client.get("/api/tools/lavar-coche?lat=-34.6&lon=-58.4")

        day = response.json()["days"][0]
        assert day["temp_max_c"] == pytest.approx(22.0)
        assert day["temp_min_c"] == pytest.approx(22.0)
        assert day["humidity"] == pytest.approx(50.0)
        assert day["wind_speed_kmh"] == pytest.approx(18.0)
        assert day["precip_mm"] == pytest.approx(0.0)
        assert day["day_label"] == day["day_label"].lower()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_a_rainy_series_is_not_a_good_day_to_wash(self, async_client: AsyncClient):
        forecast = make_uniform_hourly(temp_c=22.0, humidity=60.0, precip=1.0, wind=10.0)
        with _patch_hourly(forecast):
            response = await async_client.get("/api/tools/lavar-coche?lat=-34.6&lon=-58.4")

        day = response.json()["days"][0]
        assert day["precip_mm"] == pytest.approx(24.0)
        assert day["label"] in ("Regular", "No apto")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_a_storm_in_the_day_vetoes_it(self, async_client: AsyncClient):
        forecast = make_uniform_hourly(temp_c=22.0, humidity=50.0, precip=0.0, wind=10.0, weather_code=96)
        with _patch_hourly(forecast):
            response = await async_client.get("/api/tools/lavar-coche?lat=-34.6&lon=-58.4")

        assert all(d["label"] == "No apto" for d in response.json()["days"])

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_forecast_none_returns_503(self, async_client: AsyncClient):
        with _patch_hourly(None):
            response = await async_client.get("/api/tools/lavar-coche?lat=-34.6&lon=-58.4")

        assert response.status_code == 503
        assert response.json()["detail"] == "forecast_unavailable"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_outside_argentina_returns_422(self, async_client: AsyncClient):
        response = await async_client.get("/api/tools/lavar-coche?lat=-60&lon=-58.4")

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Rate limiting (compartido entre endpoints)
# ---------------------------------------------------------------------------

class TestRateLimiting:
    """Va al final a propósito: este test agota el cupo de /tender-ropa para el resto de la sesión
    (el limiter no se resetea entre tests)."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rate_limit_returns_429(self, async_client: AsyncClient):
        """Más de 30 requests por minuto → 429."""
        forecast = make_uniform_hourly()
        with _patch_hourly(forecast):
            responses = []
            for _ in range(35):
                r = await async_client.get(
                    "/api/tools/tender-ropa?lat=-34.6&lon=-58.4"
                )
                responses.append(r.status_code)

        assert 429 in responses
