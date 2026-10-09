"""Umbral del voto de lluvia de get_multi_model_daily.

Criterio del product owner (FRA-116): un modelo vota "llueve" un día solo si su acumulado diario
es ESTRICTAMENTE superior a 0,9 mm. Cada caso simula qué acumulado informa cada modelo, así el
borde queda fijo: 0,9 exacto no vota, apenas por encima sí, y lo que votaba con el umbral viejo
de 0,5 mm (0,51 o 0,6 mm) ya no vota.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.openmeteo import MultiModelDailyData, get_multi_model_daily

_GFS = "gfs_seamless"
_ECMWF = "ecmwf_ifs025"


def _daily_payload(precip_mm: float) -> dict:
    """Un solo día de Open-Meteo con el acumulado indicado."""
    return {
        "daily": {
            "time": ["2026-05-20"],
            "temperature_2m_max": [25.0],
            "temperature_2m_min": [15.0],
            "precipitation_sum": [precip_mm],
            "precipitation_probability_max": [10],
            "wind_speed_10m_max": [20.0],
            "wind_gusts_10m_max": [30.0],
            "relative_humidity_2m_mean": [55.0],
            "uv_index_max": [6.0],
            "weather_code": [0],
            "sunrise": ["2026-05-20T07:30"],
            "sunset": ["2026-05-20T18:00"],
            "daylight_duration": [37800.0],
        }
    }


def _client_answering(precip_mm_by_model: dict[str, float]) -> MagicMock:
    """Cliente HTTP que responde a cada modelo con su propio acumulado diario."""

    async def respond(method, url, **kwargs):
        model = kwargs.get("params", {}).get("models")
        response = MagicMock()
        response.status_code = 200
        response.raise_for_status = MagicMock()
        response.json.return_value = _daily_payload(precip_mm_by_model[model])
        return response

    client = MagicMock()
    client.request = respond
    return client


async def _consensus_for(precip_mm_by_model: dict[str, float]) -> MultiModelDailyData:
    with patch(
        "app.services.openmeteo_source.get_client",
        return_value=_client_answering(precip_mm_by_model),
    ):
        result = await get_multi_model_daily(-34.6, -58.4, days=1)
    assert result is not None
    return result


class TestRainVoteThreshold:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("model", [_GFS, _ECMWF])
    @pytest.mark.parametrize("mm", [0.51, 0.6, 0.9])
    async def test_up_to_threshold_does_not_vote_rain(self, model: str, mm: float) -> None:
        """0,9 mm exacto no vota; 0,51 y 0,6 mm votaban con el umbral viejo de 0,5 mm y ya no."""
        other = _ECMWF if model == _GFS else _GFS
        result = await _consensus_for({model: mm, other: 0.0})
        assert result.rain_consensus_per_day == ["all_agree_dry"]
        assert result.consensus_pct_per_day == [100.0]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("model", [_GFS, _ECMWF])
    @pytest.mark.parametrize("mm", [0.91, 2.0])
    async def test_above_threshold_votes_rain(self, model: str, mm: float) -> None:
        """Apenas por encima de 0,9 mm ya vota: con el otro modelo seco el voto queda 1 a 1."""
        other = _ECMWF if model == _GFS else _GFS
        result = await _consensus_for({model: mm, other: 0.0})
        assert result.rain_consensus_per_day != ["all_agree_dry"]
        assert result.consensus_pct_per_day == [50.0]

    @pytest.mark.asyncio
    async def test_both_models_at_threshold_agree_dry(self) -> None:
        result = await _consensus_for({_GFS: 0.9, _ECMWF: 0.9})
        assert result.rain_consensus_per_day == ["all_agree_dry"]
        assert result.consensus_pct_per_day == [100.0]

    @pytest.mark.asyncio
    async def test_both_models_just_above_threshold_agree_rain(self) -> None:
        result = await _consensus_for({_GFS: 0.91, _ECMWF: 0.91})
        assert result.rain_consensus_per_day == ["all_agree_rain"]
        assert result.consensus_pct_per_day == [100.0]
