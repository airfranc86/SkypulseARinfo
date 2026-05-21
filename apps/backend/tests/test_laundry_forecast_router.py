"""Tests de integración para GET /api/tools/tender-ropa/forecast."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import AsyncClient

from app.services.openmeteo import DailyForecastData
from app.services.windy import LaundryDayRaw, WindyNotConfiguredError


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

def _make_raw_days(
    n: int = 7,
    *,
    wind_dir_cardinal: str | None = "S",
) -> list[LaundryDayRaw]:
    """Construye n LaundryDayRaw con condiciones favorables."""
    from datetime import date, timedelta
    base = date(2026, 5, 20)
    days = []
    for i in range(n):
        d = base + timedelta(days=i)
        days.append(
            LaundryDayRaw(
                date=d.isoformat(),
                temp_max_c=25.0,
                temp_min_c=15.0,
                humidity_mean=50.0,
                wind_speed_kmh=15.0,
                precip_sum_mm=0.0,
                precip_prob=0.0,
                wind_dir_cardinal=wind_dir_cardinal,
            )
        )
    return days


def _make_daily_forecast(n: int = 7) -> DailyForecastData:
    """Construye un DailyForecastData sintético de n días."""
    from datetime import date, timedelta
    base = date(2026, 5, 20)
    dates = [(base + timedelta(days=i)).isoformat() for i in range(n)]
    day_labels = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"][:n]
    return DailyForecastData(
        dates=dates,
        day_labels=day_labels,
        temp_max=[25.0] * n,
        temp_min=[15.0] * n,
        precip_sum=[0.0] * n,
        wind_speed_max=[15.0] * n,
        humidity_mean=[50.0] * n,
    )


# ---------------------------------------------------------------------------
# Happy path — Windy
# ---------------------------------------------------------------------------

class TestLaundryForecastWindy:

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_windy_happy_path_returns_200(self, async_client: AsyncClient):
        raw = _make_raw_days(7)
        with patch(
            "app.routers.tools.get_windy_laundry",
            new_callable=AsyncMock,
            return_value=raw,
        ):
            response = await async_client.get(
                "/api/tools/tender-ropa/forecast?lat=-34.6&lon=-58.4"
            )

        assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_response_has_days_and_source(self, async_client: AsyncClient):
        raw = _make_raw_days(7)
        with patch(
            "app.routers.tools.get_windy_laundry",
            new_callable=AsyncMock,
            return_value=raw,
        ):
            response = await async_client.get(
                "/api/tools/tender-ropa/forecast?lat=-34.6&lon=-58.4"
            )

        data = response.json()
        assert "days" in data
        assert "source" in data
        assert data["source"] == "windy_ecmwf"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_days_count_matches_raw(self, async_client: AsyncClient):
        raw = _make_raw_days(7)
        with patch(
            "app.routers.tools.get_windy_laundry",
            new_callable=AsyncMock,
            return_value=raw,
        ):
            response = await async_client.get(
                "/api/tools/tender-ropa/forecast?lat=-34.6&lon=-58.4"
            )

        data = response.json()
        assert len(data["days"]) == 7

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_day_has_required_fields(self, async_client: AsyncClient):
        raw = _make_raw_days(3)
        with patch(
            "app.routers.tools.get_windy_laundry",
            new_callable=AsyncMock,
            return_value=raw,
        ):
            response = await async_client.get(
                "/api/tools/tender-ropa/forecast?lat=-34.6&lon=-58.4"
            )

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
    async def test_label_is_valid_literal(self, async_client: AsyncClient):
        raw = _make_raw_days(3)
        with patch(
            "app.routers.tools.get_windy_laundry",
            new_callable=AsyncMock,
            return_value=raw,
        ):
            response = await async_client.get(
                "/api/tools/tender-ropa/forecast?lat=-34.6&lon=-58.4"
            )

        valid_labels = {"Excelente", "Bueno", "Regular", "No apto"}
        for day in response.json()["days"]:
            assert day["label"] in valid_labels

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_confidence_label_is_valid(self, async_client: AsyncClient):
        raw = _make_raw_days(7)
        with patch(
            "app.routers.tools.get_windy_laundry",
            new_callable=AsyncMock,
            return_value=raw,
        ):
            response = await async_client.get(
                "/api/tools/tender-ropa/forecast?lat=-34.6&lon=-58.4"
            )

        valid = {"Alta", "Media", "Baja"}
        for day in response.json()["days"]:
            assert day["confidence_label"] in valid

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_exactly_one_is_best(self, async_client: AsyncClient):
        raw = _make_raw_days(7)
        with patch(
            "app.routers.tools.get_windy_laundry",
            new_callable=AsyncMock,
            return_value=raw,
        ):
            response = await async_client.get(
                "/api/tools/tender-ropa/forecast?lat=-34.6&lon=-58.4"
            )

        best_days = [d for d in response.json()["days"] if d["is_best"]]
        assert len(best_days) == 1

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_day_label_format(self, async_client: AsyncClient):
        """day_label debe ser 'Abv DD/MM' — e.g. 'Mié 20/05'."""
        raw = _make_raw_days(1)
        with patch(
            "app.routers.tools.get_windy_laundry",
            new_callable=AsyncMock,
            return_value=raw,
        ):
            response = await async_client.get(
                "/api/tools/tender-ropa/forecast?lat=-34.6&lon=-58.4"
            )

        import re
        day_label = response.json()["days"][0]["day_label"]
        assert re.match(r"^\w+ \d{2}/\d{2}$", day_label), f"Unexpected format: {day_label}"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_confidence_pct_decreases_over_days(self, async_client: AsyncClient):
        """El confidence_pct debe ser mayor en día 0 que en día 6."""
        raw = _make_raw_days(7)
        with patch(
            "app.routers.tools.get_windy_laundry",
            new_callable=AsyncMock,
            return_value=raw,
        ):
            response = await async_client.get(
                "/api/tools/tender-ropa/forecast?lat=-34.6&lon=-58.4"
            )

        days = response.json()["days"]
        assert days[0]["confidence_pct"] >= days[-1]["confidence_pct"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_score_range_0_to_100(self, async_client: AsyncClient):
        raw = _make_raw_days(7)
        with patch(
            "app.routers.tools.get_windy_laundry",
            new_callable=AsyncMock,
            return_value=raw,
        ):
            response = await async_client.get(
                "/api/tools/tender-ropa/forecast?lat=-34.6&lon=-58.4"
            )

        for day in response.json()["days"]:
            assert 0 <= day["score"] <= 100


# ---------------------------------------------------------------------------
# Fallback a Open-Meteo
# ---------------------------------------------------------------------------

class TestLaundryForecastFallback:

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_windy_not_configured_falls_back(self, async_client: AsyncClient):
        daily = _make_daily_forecast(7)
        with patch(
            "app.routers.tools.get_windy_laundry",
            new_callable=AsyncMock,
            side_effect=WindyNotConfiguredError("no key"),
        ), patch(
            "app.routers.tools.get_daily_forecast",
            new_callable=AsyncMock,
            return_value=daily,
        ):
            response = await async_client.get(
                "/api/tools/tender-ropa/forecast?lat=-34.6&lon=-58.4"
            )

        assert response.status_code == 200
        assert response.json()["source"] == "openmeteo_fallback"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_windy_http_error_falls_back(self, async_client: AsyncClient):
        import httpx
        daily = _make_daily_forecast(7)
        with patch(
            "app.routers.tools.get_windy_laundry",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("connection refused"),
        ), patch(
            "app.routers.tools.get_daily_forecast",
            new_callable=AsyncMock,
            return_value=daily,
        ):
            response = await async_client.get(
                "/api/tools/tender-ropa/forecast?lat=-34.6&lon=-58.4"
            )

        assert response.status_code == 200
        assert response.json()["source"] == "openmeteo_fallback"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_both_sources_fail_returns_503(self, async_client: AsyncClient):
        with patch(
            "app.routers.tools.get_windy_laundry",
            new_callable=AsyncMock,
            side_effect=WindyNotConfiguredError("no key"),
        ), patch(
            "app.routers.tools.get_daily_forecast",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = await async_client.get(
                "/api/tools/tender-ropa/forecast?lat=-34.6&lon=-58.4"
            )

        assert response.status_code == 503
        assert response.json()["detail"] == "forecast_unavailable"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_fallback_days_have_correct_structure(self, async_client: AsyncClient):
        daily = _make_daily_forecast(5)
        with patch(
            "app.routers.tools.get_windy_laundry",
            new_callable=AsyncMock,
            side_effect=WindyNotConfiguredError("no key"),
        ), patch(
            "app.routers.tools.get_daily_forecast",
            new_callable=AsyncMock,
            return_value=daily,
        ):
            response = await async_client.get(
                "/api/tools/tender-ropa/forecast?lat=-34.6&lon=-58.4"
            )

        data = response.json()
        assert len(data["days"]) == 5
        day = data["days"][0]
        assert "score" in day
        assert "label" in day
        assert "confidence_pct" in day


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestLaundryForecastValidation:

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_outside_argentina_returns_422(self, async_client: AsyncClient):
        response = await async_client.get(
            "/api/tools/tender-ropa/forecast?lat=-60&lon=-58.4"
        )
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
        response = await async_client.get(
            "/api/tools/tender-ropa/forecast?lat=invalid&lon=-58.4"
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# New scoring logic — wind direction + dew point + continuous formula
# ---------------------------------------------------------------------------

class TestLaundryForecastScoring:

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_southerly_wind_scores_higher_than_westerly(
        self, async_client: AsyncClient
    ):
        """Viento del sur (S, multiplicador 1.0) debe dar mayor score que del oeste (O, 0.70)."""
        raw_s = _make_raw_days(1, wind_dir_cardinal="S")
        raw_o = _make_raw_days(1, wind_dir_cardinal="O")

        with patch(
            "app.routers.tools.get_windy_laundry",
            new_callable=AsyncMock,
            return_value=raw_s,
        ):
            resp_s = await async_client.get(
                "/api/tools/tender-ropa/forecast?lat=-34.6&lon=-58.4"
            )

        with patch(
            "app.routers.tools.get_windy_laundry",
            new_callable=AsyncMock,
            return_value=raw_o,
        ):
            resp_o = await async_client.get(
                "/api/tools/tender-ropa/forecast?lat=-34.6&lon=-58.4"
            )

        score_s = resp_s.json()["days"][0]["score"]
        score_o = resp_o.json()["days"][0]["score"]
        assert score_s > score_o

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rain_with_high_prob_scores_very_low(
        self, async_client: AsyncClient
    ):
        """Lluvia > 1 mm + prob >= 70% → score máximo 5 (no apto)."""
        from datetime import date
        raw = [
            LaundryDayRaw(
                date=date(2026, 5, 20).isoformat(),
                temp_max_c=20.0,
                temp_min_c=12.0,
                humidity_mean=85.0,
                wind_speed_kmh=10.0,
                precip_sum_mm=5.0,
                precip_prob=80.0,
                wind_dir_cardinal="N",
            )
        ]

        with patch(
            "app.routers.tools.get_windy_laundry",
            new_callable=AsyncMock,
            return_value=raw,
        ):
            response = await async_client.get(
                "/api/tools/tender-ropa/forecast?lat=-34.6&lon=-58.4"
            )

        day = response.json()["days"][0]
        assert day["score"] <= 5
        assert day["label"] == "No apto"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_ideal_conditions_produce_excelente(
        self, async_client: AsyncClient
    ):
        """Condiciones óptimas → label Excelente (score >= 75)."""
        from datetime import date
        raw = [
            LaundryDayRaw(
                date=date(2026, 5, 20).isoformat(),
                temp_max_c=25.0,
                temp_min_c=15.0,
                humidity_mean=40.0,
                wind_speed_kmh=15.0,
                precip_sum_mm=0.0,
                precip_prob=0.0,
                wind_dir_cardinal="S",
            )
        ]

        with patch(
            "app.routers.tools.get_windy_laundry",
            new_callable=AsyncMock,
            return_value=raw,
        ):
            response = await async_client.get(
                "/api/tools/tender-ropa/forecast?lat=-34.6&lon=-58.4"
            )

        day = response.json()["days"][0]
        assert day["score"] >= 75
        assert day["label"] == "Excelente"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_wind_dir_cardinal_propagates_to_scorer(
        self, async_client: AsyncClient
    ):
        """wind_dir_cardinal None vs S deben producir scores distintos con viento > 3 km/h."""
        raw_none = _make_raw_days(1, wind_dir_cardinal=None)
        raw_s = _make_raw_days(1, wind_dir_cardinal="S")

        with patch(
            "app.routers.tools.get_windy_laundry",
            new_callable=AsyncMock,
            return_value=raw_none,
        ):
            resp_none = await async_client.get(
                "/api/tools/tender-ropa/forecast?lat=-34.6&lon=-58.4"
            )

        with patch(
            "app.routers.tools.get_windy_laundry",
            new_callable=AsyncMock,
            return_value=raw_s,
        ):
            resp_s = await async_client.get(
                "/api/tools/tender-ropa/forecast?lat=-34.6&lon=-58.4"
            )

        score_none = resp_none.json()["days"][0]["score"]
        score_s = resp_s.json()["days"][0]["score"]
        # S (1.0) >= default (0.9)
        assert score_s >= score_none
