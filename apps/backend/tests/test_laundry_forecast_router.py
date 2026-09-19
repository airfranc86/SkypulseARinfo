"""Tests de integración para GET /api/tools/tender-ropa/forecast.

El pronóstico de 7 días sale de la serie horaria de Open-Meteo agregada por día.
"""
from __future__ import annotations

import dataclasses
import re
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from tests.hourly_fixtures import make_uniform_hourly

HOURLY = "app.routers.tools.get_hourly_forecast_ext"
URL = "/api/tools/tender-ropa/forecast?lat=-34.6&lon=-58.4"


def _patch_hourly(forecast):
    return patch(HOURLY, new_callable=AsyncMock, return_value=forecast)


def _good_days(**overrides):
    """7 días de condiciones favorables: 25 °C, 50 % de humedad, 15 km/h del sur y sin lluvia."""
    values = {"temp_c": 25.0, "humidity": 50.0, "wind": 15.0, "wind_dir": 180.0, "precip": 0.0}
    values.update(overrides)
    return make_uniform_hourly(**values)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestLaundryForecast:

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_happy_path_returns_200(self, async_client: AsyncClient):
        with _patch_hourly(_good_days()):
            response = await async_client.get(URL)

        assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_response_has_days_and_open_meteo_source(self, async_client: AsyncClient):
        with _patch_hourly(_good_days()):
            response = await async_client.get(URL)

        data = response.json()
        assert "days" in data
        assert data["source"] == "openmeteo"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_seven_days(self, async_client: AsyncClient):
        with _patch_hourly(_good_days()):
            response = await async_client.get(URL)

        assert len(response.json()["days"]) == 7

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_day_has_required_fields(self, async_client: AsyncClient):
        with _patch_hourly(_good_days()):
            response = await async_client.get(URL)

        day = response.json()["days"][0]
        required = [
            "date", "day_label", "score", "label", "headline",
            "temp_max_c", "humidity", "wind_speed_kmh", "precip_prob",
            "is_best", "confidence_pct", "confidence_label",
        ]
        for field in required:
            assert field in day, f"Missing field: {field}"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_a_day_carries_the_values_of_its_hours(self, async_client: AsyncClient):
        forecast = _good_days(temp_c=25.0, humidity=50.0, wind=15.0, precip_prob=35.0)
        with _patch_hourly(forecast):
            response = await async_client.get(URL)

        day = response.json()["days"][0]
        assert day["temp_max_c"] == pytest.approx(25.0)
        assert day["humidity"] == pytest.approx(50.0)
        assert day["wind_speed_kmh"] == pytest.approx(15.0)     # el promedio del día, no la máxima
        assert day["precip_prob"] == pytest.approx(35.0)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_label_is_valid_literal(self, async_client: AsyncClient):
        with _patch_hourly(_good_days()):
            response = await async_client.get(URL)

        valid_labels = {"Excelente", "Bueno", "Regular", "No apto"}
        for day in response.json()["days"]:
            assert day["label"] in valid_labels

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_confidence_label_is_valid(self, async_client: AsyncClient):
        with _patch_hourly(_good_days()):
            response = await async_client.get(URL)

        for day in response.json()["days"]:
            assert day["confidence_label"] in {"Alta", "Media", "Baja"}

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_exactly_one_is_best(self, async_client: AsyncClient):
        with _patch_hourly(_good_days()):
            response = await async_client.get(URL)

        best_days = [d for d in response.json()["days"] if d["is_best"]]
        assert len(best_days) == 1

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_day_label_format(self, async_client: AsyncClient):
        """day_label debe ser 'Abv DD/MM' — e.g. 'Mié 20/05'."""
        with _patch_hourly(_good_days()):
            response = await async_client.get(URL)

        day_label = response.json()["days"][0]["day_label"]
        assert re.match(r"^\w+ \d{2}/\d{2}$", day_label), f"Unexpected format: {day_label}"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_confidence_pct_decreases_over_days(self, async_client: AsyncClient):
        """El confidence_pct debe ser mayor en día 0 que en día 6."""
        with _patch_hourly(_good_days()):
            response = await async_client.get(URL)

        days = response.json()["days"]
        assert days[0]["confidence_pct"] >= days[-1]["confidence_pct"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_score_range_0_to_100(self, async_client: AsyncClient):
        with _patch_hourly(_good_days()):
            response = await async_client.get(URL)

        for day in response.json()["days"]:
            assert 0 <= day["score"] <= 100


# ---------------------------------------------------------------------------
# Sin pronóstico
# ---------------------------------------------------------------------------

class TestLaundryForecastUnavailable:

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_forecast_none_returns_503(self, async_client: AsyncClient):
        with _patch_hourly(None):
            response = await async_client.get(URL)

        assert response.status_code == 503
        assert response.json()["detail"] == "forecast_unavailable"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_empty_forecast_returns_503(self, async_client: AsyncClient):
        with _patch_hourly(make_uniform_hourly(hours=0)):
            response = await async_client.get(URL)

        assert response.status_code == 503
        assert response.json()["detail"] == "forecast_unavailable"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestLaundryForecastValidation:

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_outside_argentina_returns_422(self, async_client: AsyncClient):
        response = await async_client.get("/api/tools/tender-ropa/forecast?lat=-60&lon=-58.4")
        assert response.status_code == 422
        assert response.json()["error"] == "outside_argentina"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_missing_params_returns_422(self, async_client: AsyncClient):
        response = await async_client.get("/api/tools/tender-ropa/forecast")
        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_invalid_lat_type_returns_422(self, async_client: AsyncClient):
        response = await async_client.get("/api/tools/tender-ropa/forecast?lat=invalid&lon=-58.4")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Scoring — dirección del viento + punto de rocío + fórmula continua
# ---------------------------------------------------------------------------

class TestLaundryForecastScoring:

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_southerly_wind_scores_higher_than_westerly(self, async_client: AsyncClient):
        """Viento del sur (S, multiplicador 1.0) debe dar mayor score que del oeste (O, 0.70)."""
        with _patch_hourly(_good_days(wind_dir=180.0)):
            resp_s = await async_client.get(URL)
        with _patch_hourly(_good_days(wind_dir=270.0)):
            resp_o = await async_client.get(URL)

        score_s = resp_s.json()["days"][0]["score"]
        score_o = resp_o.json()["days"][0]["score"]
        assert score_s > score_o

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rain_with_high_prob_scores_very_low(self, async_client: AsyncClient):
        """Lluvia > 1 mm + prob >= 70% → score máximo 5 (no apto)."""
        forecast = _good_days(temp_c=20.0, humidity=85.0, wind=10.0, wind_dir=0.0, precip=0.5, precip_prob=80.0)
        with _patch_hourly(forecast):
            response = await async_client.get(URL)

        day = response.json()["days"][0]
        assert day["score"] <= 5
        assert day["label"] == "No apto"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_ideal_conditions_produce_excelente(self, async_client: AsyncClient):
        """Condiciones óptimas → label Excelente (score >= 75)."""
        with _patch_hourly(_good_days(temp_c=25.0, humidity=40.0, wind=15.0, wind_dir=180.0)):
            response = await async_client.get(URL)

        day = response.json()["days"][0]
        assert day["score"] >= 75
        assert day["label"] == "Excelente"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_a_storm_in_the_day_vetoes_it(self, async_client: AsyncClient):
        with _patch_hourly(_good_days(weather_code=95)):
            response = await async_client.get(URL)

        assert all(d["label"] == "No apto" for d in response.json()["days"])

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_wind_direction_reaches_the_scorer(self, async_client: AsyncClient):
        """Sin dirección el multiplicador es 0,9; con viento del sur, 1,0."""
        without_direction = dataclasses.replace(_good_days(), wind_dirs_deg=[])
        with _patch_hourly(without_direction):
            resp_none = await async_client.get(URL)
        with _patch_hourly(_good_days(wind_dir=180.0)):
            resp_s = await async_client.get(URL)

        assert resp_s.json()["days"][0]["score"] >= resp_none.json()["days"][0]["score"]
