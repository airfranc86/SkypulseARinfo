"""Tests unitarios para app.services.windy."""
from __future__ import annotations

import asyncio
import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.windy import (
    LaundryDayRaw,
    WindyNotConfiguredError,
    _aggregate_to_daily,
    get_laundry_forecast,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_windy_response(n_slots: int = 8) -> dict:
    """
    Construye una respuesta sintética de Windy con n_slots timestamps,
    todos en el mismo día (2026-05-20 en UTC-3).
    Base: 2026-05-20 12:00 UTC → 2026-05-20 09:00 ART.
    """
    base_ms = 1747742400000  # 2026-05-20 12:00:00 UTC en ms
    ts = [base_ms + i * 3600 * 1000 for i in range(n_slots)]

    temp_k = [295.15] * n_slots      # 22 °C
    rh = [55.0] * n_slots
    wind_u = [5.0] * n_slots         # ~5 m/s E→W
    wind_v = [0.0] * n_slots
    precip = [0.0] * n_slots         # sin lluvia

    return {
        "ts": ts,
        "units": {
            "temp-surface": "K",
            "rh-surface": "%",
            "wind_u-surface": "m/s",
            "wind_v-surface": "m/s",
            "past3hprecip-surface": "mm",
        },
        "temp-surface": temp_k,
        "rh-surface": rh,
        "wind_u-surface": wind_u,
        "wind_v-surface": wind_v,
        "past3hprecip-surface": precip,
    }


def _make_multi_day_response() -> dict:
    """
    Construye respuesta con datos distribuidos en 3 días distintos.
    Día 1: 2026-05-20 09:00–20:00 ART  (base_ms → + 11h)
    Día 2: 2026-05-21 00:00–23:00 ART  (+ 15h → + 38h)
    Día 3: 2026-05-22 00:00–11:00 ART  (+ 39h → + 50h)
    """
    base_ms = 1747742400000  # 2026-05-20 12:00 UTC (= 09:00 ART)
    # 51 slots
    ts = [base_ms + i * 3600 * 1000 for i in range(51)]

    temp_k = [294.15 + (i % 4) for i in range(51)]  # 21–24 °C variando
    rh = [60.0] * 51
    wind_u = [3.0] * 51
    wind_v = [4.0] * 51   # sqrt(9+16) = 5 m/s → 18 km/h
    precip = [0.0 if i % 7 != 0 else 0.5 for i in range(51)]  # lluvia en cada 7mo slot

    return {
        "ts": ts,
        "temp-surface": temp_k,
        "rh-surface": rh,
        "wind_u-surface": wind_u,
        "wind_v-surface": wind_v,
        "past3hprecip-surface": precip,
    }


# ---------------------------------------------------------------------------
# Tests unitarios puros — _aggregate_to_daily
# ---------------------------------------------------------------------------

class TestAggregateToDaily:

    def test_single_day_returns_one_entry(self):
        data = _make_windy_response(n_slots=8)
        result = _aggregate_to_daily(data)
        assert len(result) == 1

    def test_result_is_laundry_day_raw(self):
        data = _make_windy_response(n_slots=4)
        result = _aggregate_to_daily(data)
        assert isinstance(result[0], LaundryDayRaw)

    def test_temp_conversion_kelvin_to_celsius(self):
        data = _make_windy_response(n_slots=4)
        # All temps are 295.15 K → 22.0 °C
        result = _aggregate_to_daily(data)
        day = result[0]
        assert day.temp_max_c == pytest.approx(22.0, abs=0.1)
        assert day.temp_min_c == pytest.approx(22.0, abs=0.1)

    def test_wind_speed_converted_to_kmh(self):
        # u=5, v=0 → speed_ms=5 → 18 km/h
        data = _make_windy_response(n_slots=4)
        result = _aggregate_to_daily(data)
        assert result[0].wind_speed_kmh == pytest.approx(5.0 * 3.6, abs=0.1)

    def test_no_rain_precip_sum_zero(self):
        data = _make_windy_response(n_slots=4)
        result = _aggregate_to_daily(data)
        assert result[0].precip_sum_mm == pytest.approx(0.0)

    def test_no_rain_precip_prob_zero(self):
        data = _make_windy_response(n_slots=4)
        result = _aggregate_to_daily(data)
        assert result[0].precip_prob == pytest.approx(0.0)

    def test_precip_prob_calculated_correctly(self):
        data = _make_windy_response(n_slots=4)
        # Force 2 out of 4 slots to have rain > 0.1
        data["past3hprecip-surface"] = [0.5, 0.0, 0.2, 0.0]
        result = _aggregate_to_daily(data)
        assert result[0].precip_prob == pytest.approx(50.0)

    def test_precip_sum_accumulates(self):
        data = _make_windy_response(n_slots=4)
        data["past3hprecip-surface"] = [1.0, 2.0, 0.5, 0.0]
        result = _aggregate_to_daily(data)
        assert result[0].precip_sum_mm == pytest.approx(3.5)

    def test_multi_day_splits_correctly(self):
        data = _make_multi_day_response()
        result = _aggregate_to_daily(data)
        assert len(result) >= 2

    def test_max_seven_days_returned(self):
        # Create 10 days of hourly data (240 slots)
        base_ms = 1747742400000
        ts = [base_ms + i * 3600 * 1000 for i in range(240)]
        data = {
            "ts": ts,
            "temp-surface": [295.15] * 240,
            "rh-surface": [55.0] * 240,
            "wind_u-surface": [3.0] * 240,
            "wind_v-surface": [0.0] * 240,
            "past3hprecip-surface": [0.0] * 240,
        }
        result = _aggregate_to_daily(data)
        assert len(result) <= 7

    def test_date_format_is_iso(self):
        data = _make_windy_response(n_slots=4)
        result = _aggregate_to_daily(data)
        # Must match YYYY-MM-DD
        import re
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", result[0].date)

    def test_empty_arrays_returns_empty(self):
        result = _aggregate_to_daily({"ts": [], "temp-surface": [], "rh-surface": [],
                                      "wind_u-surface": [], "wind_v-surface": [],
                                      "past3hprecip-surface": []})
        assert result == []

    def test_humidity_mean_computed(self):
        data = _make_windy_response(n_slots=4)
        data["rh-surface"] = [40.0, 60.0, 80.0, 60.0]
        result = _aggregate_to_daily(data)
        assert result[0].humidity_mean == pytest.approx(60.0)

    def test_wind_vector_magnitude(self):
        # u=3, v=4 → magnitude = 5 m/s → 18 km/h
        data = _make_windy_response(n_slots=2)
        data["wind_u-surface"] = [3.0, 3.0]
        data["wind_v-surface"] = [4.0, 4.0]
        result = _aggregate_to_daily(data)
        assert result[0].wind_speed_kmh == pytest.approx(5.0 * 3.6, abs=0.05)

    def test_wind_dir_cardinal_present(self):
        """wind_dir_cardinal must be a non-empty string when u/v are provided."""
        data = _make_windy_response(n_slots=4)
        result = _aggregate_to_daily(data)
        assert result[0].wind_dir_cardinal is not None
        assert isinstance(result[0].wind_dir_cardinal, str)
        assert len(result[0].wind_dir_cardinal) >= 1

    def test_wind_dir_cardinal_due_east(self):
        """u=5 (eastward), v=0 → origin = West → 'O'."""
        data = _make_windy_response(n_slots=4)
        data["wind_u-surface"] = [5.0] * 4
        data["wind_v-surface"] = [0.0] * 4
        result = _aggregate_to_daily(data)
        # atan2(-5, 0) = -90° → 270° → index 12 → 'O'
        assert result[0].wind_dir_cardinal == "O"

    def test_wind_dir_cardinal_due_north(self):
        """u=0, v=5 (northward) → origin = South → 'S'."""
        data = _make_windy_response(n_slots=4)
        data["wind_u-surface"] = [0.0] * 4
        data["wind_v-surface"] = [5.0] * 4
        result = _aggregate_to_daily(data)
        # atan2(0, -5) = 180° → 'S'
        assert result[0].wind_dir_cardinal == "S"

    def test_wind_dir_cardinal_none_when_no_uv(self):
        """Without u/v data, wind_dir_cardinal must be None."""
        data = _make_windy_response(n_slots=4)
        data["wind_u-surface"] = []
        data["wind_v-surface"] = []
        result = _aggregate_to_daily(data)
        assert result[0].wind_dir_cardinal is None


# ---------------------------------------------------------------------------
# Tests async — get_laundry_forecast
# ---------------------------------------------------------------------------

class TestGetLaundryForecast:

    @pytest.mark.asyncio
    async def test_raises_when_api_key_empty(self):
        with patch("app.services.windy.settings") as mock_settings:
            mock_settings.windy_api_key = ""
            with pytest.raises(WindyNotConfiguredError):
                await get_laundry_forecast(-34.6, -58.4)

    @pytest.mark.asyncio
    async def test_returns_list_of_laundry_day_raw(self):
        windy_data = _make_windy_response(n_slots=8)

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = windy_data

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("app.services.windy.settings") as mock_settings, \
             patch("app.services.windy.get_client", return_value=mock_client), \
             patch.object(
                 __import__("app.services.windy", fromlist=["_forecast_cache"]),
                 "_forecast_cache",
                 {}
             ):
            mock_settings.windy_api_key = "test-key-123"
            mock_settings.windy_base_url = "https://api.windy.com/api/point-forecast/v2"

            result = await get_laundry_forecast(-34.6, -58.4)

        assert isinstance(result, list)
        assert len(result) >= 1
        assert isinstance(result[0], LaundryDayRaw)

    @pytest.mark.asyncio
    async def test_uses_correct_model_and_parameters(self):
        windy_data = _make_windy_response(n_slots=4)

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = windy_data

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("app.services.windy.settings") as mock_settings, \
             patch("app.services.windy.get_client", return_value=mock_client), \
             patch.object(
                 __import__("app.services.windy", fromlist=["_forecast_cache"]),
                 "_forecast_cache",
                 {}
             ):
            mock_settings.windy_api_key = "test-key-456"
            mock_settings.windy_base_url = "https://api.windy.com/api/point-forecast/v2"

            await get_laundry_forecast(-34.6, -58.4)

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs[1]["json"] if call_kwargs[1] else call_kwargs.kwargs["json"]
        assert payload["model"] == "gfs"  # ecmwf requiere plan pago — gfs disponible en free plan
        assert "temp" in payload["parameters"]
        assert "rh" in payload["parameters"]
        assert "wind" in payload["parameters"]   # "wind" retorna wind_u + wind_v
        assert "precip" in payload["parameters"] # "precip" → past3hprecip-surface en respuesta
        assert payload["key"] == "test-key-456"
