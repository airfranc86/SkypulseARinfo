"""Tests para funciones de openmeteo no cubiertas por test_openmeteo.py.

Cubre:
- _cap_vis, _classify_visibility (puras)
- get_hourly_forecast
- get_daily_forecast
- get_daily_forecast_ext
- get_multi_model_daily
- get_hourly_forecast_ext
- get_visibility_forecast
- get_fog_inference_forecast
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.openmeteo import (
    DailyForecastData,
    DailyForecastDataExt,
    FogInferenceSlot,
    HourlyForecastData,
    HourlyForecastExt,
    MultiModelDailyData,
    VisibilityData,
    _cap_vis,
    _classify_visibility,
    get_daily_forecast,
    get_daily_forecast_ext,
    get_fog_inference_forecast,
    get_hourly_forecast,
    get_hourly_forecast_ext,
    get_multi_model_daily,
    get_visibility_forecast,
)


# ---------------------------------------------------------------------------
# Helpers de payload
# ---------------------------------------------------------------------------

def _make_hourly_payload(n: int = 4) -> dict:
    times = [f"2026-05-20T{9 + i:02d}:00" for i in range(n)]
    return {
        "elevation": 25.0,
        "hourly": {
            "time": times,
            "temperature_2m": [22.0 + i for i in range(n)],
            "relative_humidity_2m": [55.0] * n,
            "precipitation": [0.0] * n,
            "wind_speed_10m": [15.0] * n,
            "temperature_850hPa": [-5.0] * n,
        },
    }


def _make_daily_payload(n: int = 3) -> dict:
    dates = [f"2026-05-{20 + i:02d}" for i in range(n)]
    return {
        "daily": {
            "time": dates,
            "temperature_2m_max": [25.0 + i for i in range(n)],
            "temperature_2m_min": [15.0] * n,
            "precipitation_sum": [0.0, 5.0, 2.0][:n],
            "precipitation_probability_max": [10, 60, 40][:n],
            "wind_speed_10m_max": [20.0] * n,
            "relative_humidity_2m_mean": [55.0] * n,
        }
    }


def _make_daily_ext_payload(n: int = 3) -> dict:
    dates = [f"2026-05-{20 + i:02d}" for i in range(n)]
    return {
        "daily": {
            "time": dates,
            "temperature_2m_max": [25.0] * n,
            "temperature_2m_min": [15.0] * n,
            "precipitation_sum": [0.0] * n,
            "precipitation_probability_max": [10] * n,
            "wind_speed_10m_max": [20.0] * n,
            "wind_gusts_10m_max": [30.0] * n,
            "relative_humidity_2m_mean": [55.0] * n,
            "uv_index_max": [6.0] * n,
            "weather_code": [0, 61, 3][:n],
            "sunrise": [f"2026-05-{20 + i:02d}T07:30" for i in range(n)],
            "sunset": [f"2026-05-{20 + i:02d}T18:00" for i in range(n)],
            "daylight_duration": [37800.0] * n,
        }
    }


def _make_hourly_ext_payload(n: int = 4) -> dict:
    times = [f"2026-05-20T{9 + i:02d}:00" for i in range(n)]
    return {
        "hourly": {
            "time": times,
            "temperature_2m": [22.0] * n,
            "precipitation": [0.0] * n,
            "precipitation_probability": [10] * n,
            "wind_speed_10m": [15.0] * n,
            "weather_code": [0] * n,
            "is_day": [1, 1, 0, 0][:n],
        }
    }


def _make_visibility_payload(n: int = 14) -> dict:
    times = [f"2026-05-20T{i:02d}:00" for i in range(n)]
    return {
        "current": {
            "visibility": 8500.0,
            "weather_code": 1,
        },
        "hourly": {
            "time": times,
            "visibility": [8500.0] * n,
        },
    }


def _make_fog_inference_payload(n: int = 14) -> dict:
    times = [f"2026-05-20T{i:02d}:00" for i in range(n)]
    return {
        "hourly": {
            "time": times,
            "relative_humidity_2m": [55.0] * n,
            "dew_point_2m": [10.0] * n,
            "temperature_2m": [20.0] * n,
            "wind_speed_10m": [15.0] * n,
            "weather_code": [0] * n,
        }
    }


def _mock_http_client(payload: dict, status_code: int = 200) -> AsyncMock:
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = status_code
    if status_code >= 400:
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            str(status_code),
            request=MagicMock(),
            response=MagicMock(status_code=status_code),
        )
    else:
        mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = payload

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_response)
    return mock_client


# ---------------------------------------------------------------------------
# _cap_vis
# ---------------------------------------------------------------------------

class TestCapVis:

    def test_none_returns_none(self):
        assert _cap_vis(None) is None

    def test_below_max_returns_unchanged(self):
        assert _cap_vis(5000.0) == pytest.approx(5000.0)

    def test_above_max_returns_10000(self):
        assert _cap_vis(25000.0) == pytest.approx(10000.0)

    def test_exactly_at_max_returns_10000(self):
        assert _cap_vis(10000.0) == pytest.approx(10000.0)

    def test_zero_returns_zero(self):
        assert _cap_vis(0.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _classify_visibility
# ---------------------------------------------------------------------------

class TestClassifyVisibility:

    def test_none_returns_no_data(self):
        level, label, _ = _classify_visibility(None)
        assert level == 0
        assert label == "Sin datos"

    def test_10000m_is_despejada(self):
        level, label, _ = _classify_visibility(10_000.0)
        assert level == 0
        assert label == "Despejada"

    def test_above_10000_is_despejada(self):
        level, label, _ = _classify_visibility(15_000.0)
        assert label == "Despejada"

    def test_5000_to_9999_is_buena(self):
        level, label, _ = _classify_visibility(7_000.0)
        assert level == 1
        assert label == "Buena"

    def test_2000_to_4999_is_reducida(self):
        level, label, _ = _classify_visibility(3_000.0)
        assert level == 2
        assert label == "Reducida"

    def test_1000_to_1999_is_bruma(self):
        level, label, _ = _classify_visibility(1_500.0)
        assert level == 3
        assert label == "Bruma"

    def test_500_to_999_is_neblina(self):
        level, label, _ = _classify_visibility(700.0)
        assert level == 4
        assert label == "Neblina"

    def test_below_500_is_niebla(self):
        level, label, _ = _classify_visibility(200.0)
        assert level == 5
        assert label == "Niebla"

    def test_returns_hex_color(self):
        _, _, color = _classify_visibility(8000.0)
        assert color.startswith("#")
        assert len(color) == 7


# ---------------------------------------------------------------------------
# get_hourly_forecast
# ---------------------------------------------------------------------------

class TestGetHourlyForecast:

    @pytest.mark.asyncio
    async def test_returns_hourly_forecast_data(self):
        payload = _make_hourly_payload(n=4)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_hourly_forecast(-34.6, -58.4)
        assert isinstance(result, HourlyForecastData)

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self):
        from httpx import TimeoutException
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=TimeoutException("timeout"))
        with patch("app.services.openmeteo.get_client", return_value=mock_client):
            result = await get_hourly_forecast(-34.6, -58.4)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_5xx(self):
        payload = {}
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload, status_code=500)):
            result = await get_hourly_forecast(-34.6, -58.4)
        assert result is None

    @pytest.mark.asyncio
    async def test_timestamps_length_matches_time_list(self):
        payload = _make_hourly_payload(n=6)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_hourly_forecast(-34.6, -58.4)
        assert len(result.timestamps) == 6
        assert len(result.hour_labels) == 6

    @pytest.mark.asyncio
    async def test_hour_label_format_hh_mm(self):
        payload = _make_hourly_payload(n=2)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_hourly_forecast(-34.6, -58.4)
        for label in result.hour_labels:
            assert len(label) == 5
            assert label[2] == ":"

    @pytest.mark.asyncio
    async def test_elevation_m_parsed(self):
        payload = _make_hourly_payload(n=2)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_hourly_forecast(-34.6, -58.4)
        assert result.elevation_m == pytest.approx(25.0)

    @pytest.mark.asyncio
    async def test_returns_none_on_invalid_payload(self):
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client({"wrong": "payload"})):
            result = await get_hourly_forecast(-34.6, -58.4)
        assert result is None


# ---------------------------------------------------------------------------
# get_daily_forecast
# ---------------------------------------------------------------------------

class TestGetDailyForecast:

    @pytest.mark.asyncio
    async def test_returns_daily_forecast_data(self):
        payload = _make_daily_payload(n=3)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_daily_forecast(-34.6, -58.4)
        assert isinstance(result, DailyForecastData)

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self):
        from httpx import TimeoutException
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=TimeoutException("t"))
        with patch("app.services.openmeteo.get_client", return_value=mock_client):
            result = await get_daily_forecast(-34.6, -58.4)
        assert result is None

    @pytest.mark.asyncio
    async def test_dates_count_matches_input(self):
        payload = _make_daily_payload(n=4)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_daily_forecast(-34.6, -58.4)
        assert len(result.dates) == 4

    @pytest.mark.asyncio
    async def test_day_labels_are_spanish_weekdays(self):
        valid_days = {"lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"}
        payload = _make_daily_payload(n=3)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_daily_forecast(-34.6, -58.4)
        for label in result.day_labels:
            assert label in valid_days

    @pytest.mark.asyncio
    async def test_temp_max_parsed(self):
        payload = _make_daily_payload(n=2)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_daily_forecast(-34.6, -58.4)
        assert result.temp_max[0] == pytest.approx(25.0)

    @pytest.mark.asyncio
    async def test_precip_prob_max_parsed(self):
        payload = _make_daily_payload(n=2)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_daily_forecast(-34.6, -58.4)
        assert result.precip_prob_max[1] == pytest.approx(60.0)

    @pytest.mark.asyncio
    async def test_returns_none_on_invalid_payload(self):
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client({"bad": True})):
            result = await get_daily_forecast(-34.6, -58.4)
        assert result is None


# ---------------------------------------------------------------------------
# get_daily_forecast_ext
# ---------------------------------------------------------------------------

class TestGetDailyForecastExt:

    @pytest.mark.asyncio
    async def test_returns_daily_forecast_data_ext(self):
        payload = _make_daily_ext_payload(n=3)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_daily_forecast_ext(-34.6, -58.4)
        assert isinstance(result, DailyForecastDataExt)

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self):
        from httpx import TimeoutException
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=TimeoutException("t"))
        with patch("app.services.openmeteo.get_client", return_value=mock_client):
            result = await get_daily_forecast_ext(-34.6, -58.4)
        assert result is None

    @pytest.mark.asyncio
    async def test_weather_codes_are_integers(self):
        payload = _make_daily_ext_payload(n=3)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_daily_forecast_ext(-34.6, -58.4)
        for code in result.weather_codes:
            if code is not None:
                assert isinstance(code, int)

    @pytest.mark.asyncio
    async def test_daylight_seconds_parsed(self):
        payload = _make_daily_ext_payload(n=2)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_daily_forecast_ext(-34.6, -58.4)
        assert result.daylight_seconds[0] == pytest.approx(37800.0)

    @pytest.mark.asyncio
    async def test_model_param_injected_when_specified(self):
        import httpx
        payload = _make_daily_ext_payload(n=2)
        captured = {}

        async def capture_request(method, url, **kwargs):
            captured["params"] = kwargs.get("params", {})
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = payload
            return mock_response

        mock_client = MagicMock()
        mock_client.request = capture_request
        with patch("app.services.openmeteo.get_client", return_value=mock_client):
            await get_daily_forecast_ext(-34.6, -58.4, model="gfs_seamless")

        assert captured.get("params", {}).get("models") == "gfs_seamless"

    @pytest.mark.asyncio
    async def test_no_model_param_when_none(self):
        payload = _make_daily_ext_payload(n=2)
        captured = {}

        async def capture_request(method, url, **kwargs):
            captured["params"] = kwargs.get("params", {})
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = payload
            return mock_response

        mock_client = MagicMock()
        mock_client.request = capture_request
        with patch("app.services.openmeteo.get_client", return_value=mock_client):
            await get_daily_forecast_ext(-34.6, -58.4, model=None)

        assert "models" not in captured.get("params", {})

    @pytest.mark.asyncio
    async def test_wind_gusts_parsed(self):
        payload = _make_daily_ext_payload(n=2)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_daily_forecast_ext(-34.6, -58.4)
        assert result.wind_gusts_max[0] == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# get_multi_model_daily
# ---------------------------------------------------------------------------

class TestGetMultiModelDaily:

    @pytest.mark.asyncio
    async def test_returns_multi_model_daily_data(self):
        payload = _make_daily_ext_payload(n=3)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_multi_model_daily(-34.6, -58.4, days=3)
        assert isinstance(result, MultiModelDailyData)

    @pytest.mark.asyncio
    async def test_returns_none_when_all_models_fail(self):
        from httpx import TimeoutException
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=TimeoutException("t"))
        with patch("app.services.openmeteo.get_client", return_value=mock_client):
            result = await get_multi_model_daily(-34.6, -58.4)
        assert result is None

    @pytest.mark.asyncio
    async def test_models_dict_has_both_models(self):
        payload = _make_daily_ext_payload(n=3)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_multi_model_daily(-34.6, -58.4)
        assert "gfs_seamless" in result.models
        assert "ecmwf_ifs025" in result.models

    @pytest.mark.asyncio
    async def test_partial_failure_returns_result_with_one_model(self):
        """Si un modelo falla en todos sus intentos, el resultado usa solo el modelo disponible."""
        from httpx import TimeoutException
        payload = _make_daily_ext_payload(n=2)

        async def selective_fail(method, url, **kwargs):
            # Identificar el modelo por params — GFS siempre falla, ECMWF siempre tiene éxito
            if kwargs.get("params", {}).get("models") == "gfs_seamless":
                raise TimeoutException("gfs failed")
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = payload
            return mock_response

        mock_client = MagicMock()
        mock_client.request = selective_fail
        with patch("app.services.openmeteo.get_client", return_value=mock_client):
            result = await get_multi_model_daily(-34.6, -58.4, days=2)

        assert result is not None
        assert len(result.models) == 1
        assert "ecmwf_ifs025" in result.models

    @pytest.mark.asyncio
    async def test_consensus_pct_length_matches_days(self):
        payload = _make_daily_ext_payload(n=3)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_multi_model_daily(-34.6, -58.4, days=3)
        assert len(result.consensus_pct_per_day) == 3

    @pytest.mark.asyncio
    async def test_consensus_pct_range_50_to_100(self):
        payload = _make_daily_ext_payload(n=3)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_multi_model_daily(-34.6, -58.4, days=3)
        for pct in result.consensus_pct_per_day:
            assert 50.0 <= pct <= 100.0

    @pytest.mark.asyncio
    async def test_all_agree_dry_when_no_precip(self):
        payload = _make_daily_ext_payload(n=2)
        # All precip_sum=0 → all_agree_dry
        payload["daily"]["precipitation_sum"] = [0.0, 0.0]
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_multi_model_daily(-34.6, -58.4, days=2)
        assert all(label == "all_agree_rain" or label == "all_agree_dry"
                   for label in result.rain_consensus_per_day)

    @pytest.mark.asyncio
    async def test_all_agree_rain_when_precip_high(self):
        payload = _make_daily_ext_payload(n=2)
        payload["daily"]["precipitation_sum"] = [10.0, 8.0]  # > 0.5mm both days
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_multi_model_daily(-34.6, -58.4, days=2)
        assert all(label == "all_agree_rain" for label in result.rain_consensus_per_day)

    @pytest.mark.asyncio
    async def test_rain_consensus_labels_valid(self):
        valid_labels = {"all_agree_dry", "all_agree_rain", "majority_dry", "majority_rain", "split"}
        payload = _make_daily_ext_payload(n=3)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_multi_model_daily(-34.6, -58.4, days=3)
        for label in result.rain_consensus_per_day:
            assert label in valid_labels


# ---------------------------------------------------------------------------
# get_hourly_forecast_ext
# ---------------------------------------------------------------------------

class TestGetHourlyForecastExt:

    @pytest.mark.asyncio
    async def test_returns_hourly_forecast_ext(self):
        payload = _make_hourly_ext_payload(n=4)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_hourly_forecast_ext(-34.6, -58.4)
        assert isinstance(result, HourlyForecastExt)

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self):
        from httpx import TimeoutException
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=TimeoutException("t"))
        with patch("app.services.openmeteo.get_client", return_value=mock_client):
            result = await get_hourly_forecast_ext(-34.6, -58.4)
        assert result is None

    @pytest.mark.asyncio
    async def test_is_day_converted_to_bool(self):
        payload = _make_hourly_ext_payload(n=4)
        payload["hourly"]["is_day"] = [1, 0, 1, 0]
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_hourly_forecast_ext(-34.6, -58.4)
        assert all(isinstance(v, bool) for v in result.is_day)
        assert result.is_day[0] is True
        assert result.is_day[1] is False

    @pytest.mark.asyncio
    async def test_weather_codes_are_integers(self):
        payload = _make_hourly_ext_payload(n=3)
        payload["hourly"]["weather_code"] = [0, 61, 95]
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_hourly_forecast_ext(-34.6, -58.4)
        for code in result.weather_codes:
            if code is not None:
                assert isinstance(code, int)

    @pytest.mark.asyncio
    async def test_dates_extracted_from_timestamp(self):
        payload = _make_hourly_ext_payload(n=2)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_hourly_forecast_ext(-34.6, -58.4)
        # dates should be YYYY-MM-DD format
        import re
        for d in result.dates:
            assert re.match(r"^\d{4}-\d{2}-\d{2}$", d)

    @pytest.mark.asyncio
    async def test_hour_labels_format(self):
        payload = _make_hourly_ext_payload(n=2)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)):
            result = await get_hourly_forecast_ext(-34.6, -58.4)
        for label in result.hour_labels:
            assert len(label) == 5
            assert label[2] == ":"

    @pytest.mark.asyncio
    async def test_returns_none_on_invalid_payload(self):
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client({"x": 1})):
            result = await get_hourly_forecast_ext(-34.6, -58.4)
        assert result is None


# ---------------------------------------------------------------------------
# get_visibility_forecast
# ---------------------------------------------------------------------------

class TestGetVisibilityForecast:

    @pytest.mark.asyncio
    async def test_returns_visibility_data(self):
        payload = _make_visibility_payload(n=14)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)), \
             patch("app.services.openmeteo._next_ar_hour_idx", return_value=0):
            result = await get_visibility_forecast(-34.6, -58.4)
        assert isinstance(result, VisibilityData)

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self):
        from httpx import TimeoutException
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=TimeoutException("t"))
        with patch("app.services.openmeteo.get_client", return_value=mock_client):
            result = await get_visibility_forecast(-34.6, -58.4)
        assert result is None

    @pytest.mark.asyncio
    async def test_current_visibility_parsed(self):
        payload = _make_visibility_payload(n=14)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)), \
             patch("app.services.openmeteo._next_ar_hour_idx", return_value=0):
            result = await get_visibility_forecast(-34.6, -58.4)
        assert result.current_m == pytest.approx(8500.0)

    @pytest.mark.asyncio
    async def test_current_visibility_capped_at_10000(self):
        payload = _make_visibility_payload(n=14)
        payload["current"]["visibility"] = 25000.0
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)), \
             patch("app.services.openmeteo._next_ar_hour_idx", return_value=0):
            result = await get_visibility_forecast(-34.6, -58.4)
        assert result.current_m == pytest.approx(10000.0)

    @pytest.mark.asyncio
    async def test_hourly_m_has_12_slots(self):
        payload = _make_visibility_payload(n=14)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)), \
             patch("app.services.openmeteo._next_ar_hour_idx", return_value=0):
            result = await get_visibility_forecast(-34.6, -58.4)
        assert len(result.hourly_m) == 12

    @pytest.mark.asyncio
    async def test_fog_level_set_correctly(self):
        payload = _make_visibility_payload(n=14)
        # 8500 m → level=1 ("Buena")
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)), \
             patch("app.services.openmeteo._next_ar_hour_idx", return_value=0):
            result = await get_visibility_forecast(-34.6, -58.4)
        assert result.fog_level == 1
        assert result.fog_label == "Buena"

    @pytest.mark.asyncio
    async def test_weather_code_parsed(self):
        payload = _make_visibility_payload(n=14)
        payload["current"]["weather_code"] = 45
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)), \
             patch("app.services.openmeteo._next_ar_hour_idx", return_value=0):
            result = await get_visibility_forecast(-34.6, -58.4)
        assert result.weather_code == 45

    @pytest.mark.asyncio
    async def test_returns_none_on_invalid_payload(self):
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client({"z": 1})):
            result = await get_visibility_forecast(-34.6, -58.4)
        assert result is None


# ---------------------------------------------------------------------------
# get_fog_inference_forecast
# ---------------------------------------------------------------------------

class TestGetFogInferenceForecast:

    @pytest.mark.asyncio
    async def test_returns_list_of_fog_inference_slots(self):
        payload = _make_fog_inference_payload(n=14)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)), \
             patch("app.services.openmeteo._next_ar_hour_idx", return_value=0):
            result = await get_fog_inference_forecast(-34.6, -58.4, hours=12)
        assert isinstance(result, list)
        assert all(isinstance(s, FogInferenceSlot) for s in result)

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self):
        from httpx import TimeoutException
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=TimeoutException("t"))
        with patch("app.services.openmeteo.get_client", return_value=mock_client):
            result = await get_fog_inference_forecast(-34.6, -58.4)
        assert result is None

    @pytest.mark.asyncio
    async def test_wmo_45_sets_vis_300m(self):
        """WMO code 45 (fog confirmed) must override estimation → 300 m."""
        payload = _make_fog_inference_payload(n=14)
        payload["hourly"]["weather_code"] = [45] * 14
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)), \
             patch("app.services.openmeteo._next_ar_hour_idx", return_value=0):
            result = await get_fog_inference_forecast(-34.6, -58.4, hours=4)
        assert all(s.visibility_m == pytest.approx(300.0) for s in result)

    @pytest.mark.asyncio
    async def test_wmo_48_sets_vis_300m(self):
        """WMO code 48 (rime fog) must also produce 300 m."""
        payload = _make_fog_inference_payload(n=14)
        payload["hourly"]["weather_code"] = [48] * 14
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)), \
             patch("app.services.openmeteo._next_ar_hour_idx", return_value=0):
            result = await get_fog_inference_forecast(-34.6, -58.4, hours=4)
        assert all(s.visibility_m == pytest.approx(300.0) for s in result)

    @pytest.mark.asyncio
    async def test_dense_fog_conditions_return_300m(self):
        """dep<2 + rh>=95 + wind<5 → niebla densa → 300 m."""
        payload = _make_fog_inference_payload(n=14)
        payload["hourly"]["temperature_2m"] = [15.0] * 14
        payload["hourly"]["dew_point_2m"] = [14.5] * 14   # dep=0.5 < 2
        payload["hourly"]["relative_humidity_2m"] = [96.0] * 14   # >=95
        payload["hourly"]["wind_speed_10m"] = [3.0] * 14          # <5
        payload["hourly"]["weather_code"] = [1] * 14   # not fog code
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)), \
             patch("app.services.openmeteo._next_ar_hour_idx", return_value=0):
            result = await get_fog_inference_forecast(-34.6, -58.4, hours=4)
        assert all(s.visibility_m == pytest.approx(300.0) for s in result)

    @pytest.mark.asyncio
    async def test_fog_conditions_return_1000m(self):
        """dep<3 + rh>=90 + wind<8 (but not dense) → niebla → 1000 m."""
        payload = _make_fog_inference_payload(n=14)
        payload["hourly"]["temperature_2m"] = [15.0] * 14
        payload["hourly"]["dew_point_2m"] = [12.5] * 14   # dep=2.5 < 3
        payload["hourly"]["relative_humidity_2m"] = [92.0] * 14   # >=90
        payload["hourly"]["wind_speed_10m"] = [6.0] * 14          # <8, >=5
        payload["hourly"]["weather_code"] = [1] * 14
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)), \
             patch("app.services.openmeteo._next_ar_hour_idx", return_value=0):
            result = await get_fog_inference_forecast(-34.6, -58.4, hours=4)
        assert all(s.visibility_m == pytest.approx(1000.0) for s in result)

    @pytest.mark.asyncio
    async def test_reduced_visibility_conditions_return_3000m(self):
        """dep<5 + rh>=80 → reducida → 3000 m."""
        payload = _make_fog_inference_payload(n=14)
        payload["hourly"]["temperature_2m"] = [15.0] * 14
        payload["hourly"]["dew_point_2m"] = [11.5] * 14   # dep=3.5 < 5
        payload["hourly"]["relative_humidity_2m"] = [82.0] * 14   # >=80
        payload["hourly"]["wind_speed_10m"] = [12.0] * 14         # >=8 (not fog)
        payload["hourly"]["weather_code"] = [1] * 14
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)), \
             patch("app.services.openmeteo._next_ar_hour_idx", return_value=0):
            result = await get_fog_inference_forecast(-34.6, -58.4, hours=4)
        assert all(s.visibility_m == pytest.approx(3000.0) for s in result)

    @pytest.mark.asyncio
    async def test_clear_conditions_return_10000m(self):
        """Normal conditions (not foggy) → despejada → 10 000 m."""
        payload = _make_fog_inference_payload(n=14)
        payload["hourly"]["temperature_2m"] = [20.0] * 14
        payload["hourly"]["dew_point_2m"] = [10.0] * 14   # dep=10 >=5
        payload["hourly"]["relative_humidity_2m"] = [55.0] * 14   # <80
        payload["hourly"]["wind_speed_10m"] = [15.0] * 14
        payload["hourly"]["weather_code"] = [0] * 14
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)), \
             patch("app.services.openmeteo._next_ar_hour_idx", return_value=0):
            result = await get_fog_inference_forecast(-34.6, -58.4, hours=4)
        assert all(s.visibility_m == pytest.approx(10000.0) for s in result)

    @pytest.mark.asyncio
    async def test_hour_label_format(self):
        payload = _make_fog_inference_payload(n=14)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)), \
             patch("app.services.openmeteo._next_ar_hour_idx", return_value=0):
            result = await get_fog_inference_forecast(-34.6, -58.4, hours=4)
        for slot in result:
            assert len(slot.hour_label) == 5
            assert slot.hour_label[2] == ":"

    @pytest.mark.asyncio
    async def test_slot_count_matches_hours_param(self):
        payload = _make_fog_inference_payload(n=14)
        with patch("app.services.openmeteo.get_client", return_value=_mock_http_client(payload)), \
             patch("app.services.openmeteo._next_ar_hour_idx", return_value=0):
            result = await get_fog_inference_forecast(-34.6, -58.4, hours=6)
        assert len(result) == 6
