"""Tests de las fuentes de cada campo en build_7d_forecast: todo sale de Open-Meteo.

Windy dejó de alimentar el pronóstico de 7 días: la clave del plan Testing devuelve datos mezclados
al azar, y con la cantidad de lluvia de Windy y la probabilidad de Open-Meteo la tarjeta de un día
podía decir "Lluvia 100 %" con 0,01 mm. Ahora la cantidad, la probabilidad, el ícono y las
temperaturas salen del mismo lugar.

T1  — precip_prob: el máximo entre los modelos
T2  — precip_prob con un solo modelo
T3  — precip_prob sin dato → None
T4  — temp_max: promedio del consenso
T6  — temp_max sin dato → None, sin romper
T7  — precip_sum: promedio del consenso, o el del modelo elegido
T8  — wind_speed_max: promedio del consenso
T9  — cantidad y probabilidad de un día salen de la misma fuente
T10 — consenso promedia varios modelos
T11 — el modelo elegido filtra la lista
T12 — riesgo convectivo diario desde el CAPE horario de Open-Meteo
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.services.dashboard_builder import build_7d_forecast
from app.services.openmeteo import DailyForecastDataExt, MultiModelDailyData
from tests.hourly_fixtures import AR, make_hourly


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_DATES = ["2026-05-20", "2026-05-21", "2026-05-22",
          "2026-05-23", "2026-05-24", "2026-05-25", "2026-05-26"]
_N = len(_DATES)


def _make_om(
    *,
    temp_max: list[float | None] | None = None,
    temp_min: list[float | None] | None = None,
    precip_prob_max: list[float | None] | None = None,
    precip_sum: list[float | None] | None = None,
    wind_speed_max: list[float | None] | None = None,
) -> DailyForecastDataExt:
    return DailyForecastDataExt(
        dates=_DATES,
        day_labels=["miércoles"] * _N,
        temp_max=temp_max if temp_max is not None else [22.0] * _N,
        temp_min=temp_min if temp_min is not None else [10.0] * _N,
        precip_sum=precip_sum if precip_sum is not None else [0.0] * _N,
        precip_prob_max=precip_prob_max if precip_prob_max is not None else [5.0] * _N,
        wind_speed_max=wind_speed_max if wind_speed_max is not None else [15.0] * _N,
        wind_gusts_max=[25.0] * _N,
        humidity_mean=[60.0] * _N,
        uv_max=[4.0] * _N,
        weather_codes=[0] * _N,
        sunrise=["2026-05-20T07:00"] * _N,
        sunset=["2026-05-20T18:30"] * _N,
        daylight_seconds=[41400.0] * _N,
    )


def _make_multi(*models: DailyForecastDataExt) -> MultiModelDailyData:
    """Un MultiModelDailyData con los modelos dados (ECMWF, GFS…, en ese orden)."""
    names = ["ecmwf_ifs025", "gfs_seamless", "icon_seamless"]
    chosen = models or (_make_om(),)
    return MultiModelDailyData(
        models=dict(zip(names, chosen)),
        consensus_pct_per_day=[100.0] * _N,
        rain_consensus_per_day=["all_agree_dry"] * _N,
    )


def _first(daily_multi: MultiModelDailyData, **kwargs):
    """Corre build_7d_forecast y devuelve el primer día."""
    return build_7d_forecast(daily_multi, snow_level_m=None, **kwargs)[0]


# ---------------------------------------------------------------------------
# T1 / T2 / T3 — precip_prob
# ---------------------------------------------------------------------------

def test_precip_prob_is_the_maximum_across_models():
    multi = _make_multi(_make_om(precip_prob_max=[30.0] * _N), _make_om(precip_prob_max=[60.0] * _N))

    assert _first(multi).precip_prob == pytest.approx(60.0)


def test_precip_prob_not_zero_when_om_has_rain_forecast():
    multi = _make_multi(_make_om(precip_prob_max=[45.0] * _N))

    assert _first(multi).precip_prob == pytest.approx(45.0)


def test_precip_prob_without_data_is_none():
    multi = _make_multi(_make_om(precip_prob_max=[None] * _N))

    assert _first(multi).precip_prob is None


# ---------------------------------------------------------------------------
# T4 / T6 — temp_max
# ---------------------------------------------------------------------------

def test_temp_max_comes_from_the_open_meteo_daily_aggregate():
    multi = _make_multi(_make_om(temp_max=[22.0] * _N))

    assert _first(multi).temp_max == pytest.approx(22.0)


def test_temp_max_both_none():
    multi = _make_multi(_make_om(temp_max=[None] * _N))

    assert _first(multi).temp_max is None, "sin dato en ningún modelo → None, sin romper"


# ---------------------------------------------------------------------------
# T7 / T8 — precip_sum y wind_speed_max: también de Open-Meteo
# ---------------------------------------------------------------------------

def test_precip_sum_is_the_consensus_mean_of_open_meteo():
    """Mañana en el pronóstico real: GFS 16,8 mm y ECMWF 14 mm → 15,4 mm."""
    multi = _make_multi(_make_om(precip_sum=[14.0] * _N), _make_om(precip_sum=[16.8] * _N))

    assert _first(multi).precip_sum == pytest.approx(15.4)


def test_precip_sum_of_the_selected_model():
    multi = _make_multi(_make_om(precip_sum=[14.0] * _N), _make_om(precip_sum=[16.8] * _N))

    assert _first(multi, selected_model="gfs").precip_sum == pytest.approx(16.8)
    assert _first(multi, selected_model="ecmwf").precip_sum == pytest.approx(14.0)


def test_wind_speed_max_is_the_consensus_mean_of_open_meteo():
    multi = _make_multi(_make_om(wind_speed_max=[30.0] * _N), _make_om(wind_speed_max=[40.0] * _N))

    assert _first(multi).wind_speed_max == pytest.approx(35.0)


# ---------------------------------------------------------------------------
# T9 — la cantidad y la probabilidad de un día cuentan la misma historia
# ---------------------------------------------------------------------------

def test_amount_and_probability_of_a_rainy_day_come_from_the_same_source():
    """El día que mostraba "Lluvia 100 %" con 0,01 mm: la probabilidad era de Open-Meteo y la
    cantidad de Windy. Ahora ambas son de Open-Meteo y coinciden."""
    multi = _make_multi(
        _make_om(precip_sum=[14.0] * _N, precip_prob_max=[97.0] * _N),
        _make_om(precip_sum=[16.8] * _N, precip_prob_max=[100.0] * _N),
    )

    entry = _first(multi)
    assert entry.precip_prob == pytest.approx(100.0)
    assert entry.precip_sum == pytest.approx(15.4)
    assert entry.precip_sum > 10  # una tormenta, no una traza


# ---------------------------------------------------------------------------
# T10 / T11 — consenso y modelo elegido
# ---------------------------------------------------------------------------

def test_consensus_mode_averages_multiple_om_models():
    multi = _make_multi(
        _make_om(temp_max=[20.0] * _N),
        _make_om(temp_max=[22.0] * _N),
        _make_om(temp_max=[24.0] * _N),
    )

    assert _first(multi, selected_model="consensus").temp_max == pytest.approx(22.0)


def test_selected_model_filters_om_list():
    multi = _make_multi(_make_om(temp_max=[22.0] * _N), _make_om(temp_max=[18.0] * _N))

    entry = _first(multi, selected_model="ecmwf")
    assert entry.temp_max == pytest.approx(22.0), "solo ecmwf_ifs025 aporta; gfs_seamless (18.0) se ignora"


# ---------------------------------------------------------------------------
# T12 — riesgo convectivo diario: el CAPE máximo del día, de Open-Meteo
# ---------------------------------------------------------------------------

def _week_of_hours(**overrides):
    return make_hourly(hours=_N * 24, start=datetime(2026, 5, 20, 0, 0, tzinfo=AR), **overrides)


def test_daily_convective_risk_is_the_highest_cape_of_that_day():
    hourly = _week_of_hours(cape_j_kg={2 * 24 + 16: 3200.0, 3 * 24 + 10: 400.0})

    entries = build_7d_forecast(_make_multi(), snow_level_m=None, om_hourly=hourly)

    assert entries[2].convective_risk == "high"     # 22/05: 3200 J/kg
    assert entries[3].convective_risk == "low"      # 23/05: 400 J/kg
    assert entries[0].convective_risk == "low"      # hay dato y es 0 J/kg


def test_daily_convective_risk_is_unknown_without_hourly_data():
    entries = build_7d_forecast(_make_multi(), snow_level_m=None, om_hourly=None)

    assert all(e.convective_risk is None for e in entries), "sin dato no se finge un cielo tranquilo"


def test_daily_convective_risk_is_unknown_for_days_beyond_the_hourly_horizon():
    hourly = make_hourly(hours=2 * 24, start=datetime(2026, 5, 20, 0, 0, tzinfo=AR))  # solo 2 días

    entries = build_7d_forecast(_make_multi(), snow_level_m=None, om_hourly=hourly)

    assert entries[0].convective_risk == "low"
    assert entries[5].convective_risk is None
