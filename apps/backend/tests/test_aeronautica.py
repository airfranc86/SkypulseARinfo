"""Tests unitarios del cálculo de Altitud de Densidad (sin I/O)."""
from __future__ import annotations

import pytest

from app.services.aeronautica import classify_risk, compute_density_altitude


def _calc(**overrides):
    params = dict(
        elev_ft=0.0,
        qnh_hpa=1013.25,
        oat_c=15.0,
        td_c=-40.0,
        wl_nom=1.5,
        ias_kt=100.0,
        aircraft_model="piston",
    )
    params.update(overrides)
    return compute_density_altitude(**params)


# ---------------------------------------------------------------------------
# Física base
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_isa_sea_level_dry_air_is_near_zero_density_altitude():
    r = _calc()
    assert r.pressure_altitude_ft == pytest.approx(0.0, abs=1e-6)
    assert r.density_altitude_ft == pytest.approx(0.0, abs=15.0)
    assert r.sigma == pytest.approx(1.0, abs=0.005)
    assert r.tas_kt == pytest.approx(100.0, rel=0.005)
    assert r.wl_eff == pytest.approx(1.5, rel=0.005)
    assert r.risk_level == "verde"


@pytest.mark.unit
def test_low_qnh_raises_pressure_altitude_30ft_per_hpa():
    r = _calc(qnh_hpa=993.25)  # 20 hPa por debajo de ISA
    assert r.pressure_altitude_ft == pytest.approx(600.0, abs=1e-6)


@pytest.mark.unit
def test_hot_day_raises_density_altitude_118_8_ft_per_degree():
    isa = _calc(elev_ft=2000.0, oat_c=15.0 - 1.98 * 2.0)
    hot = _calc(elev_ft=2000.0, oat_c=15.0 - 1.98 * 2.0 + 20.0)
    assert hot.density_altitude_ft - isa.density_altitude_ft == pytest.approx(118.8 * 20.0, rel=0.03)


@pytest.mark.unit
def test_humidity_raises_density_altitude_at_equal_temperature_and_pressure():
    dry = _calc(elev_ft=1000.0, oat_c=30.0, td_c=-10.0)
    humid = _calc(elev_ft=1000.0, oat_c=30.0, td_c=25.0)
    assert humid.density_altitude_ft > dry.density_altitude_ft


@pytest.mark.unit
def test_higher_density_altitude_lowers_sigma_and_raises_tas_and_wing_loading():
    low = _calc(elev_ft=0.0, oat_c=15.0)
    high = _calc(elev_ft=5000.0, oat_c=35.0, td_c=10.0)
    assert high.sigma < low.sigma
    assert high.tas_kt > low.tas_kt
    assert high.wl_eff > low.wl_eff
    assert high.wl_eff == pytest.approx(1.5 / high.sigma, rel=1e-9)


# ---------------------------------------------------------------------------
# Reglas operacionales del ticket
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_operational_rules_scale_with_density_altitude():
    # elev 5000 ft, temperatura ISA, aire seco → DA ≈ 5000 ft
    r = _calc(elev_ft=5000.0, oat_c=15.0 - 1.98 * 5.0)
    da_k = r.density_altitude_ft / 1000.0
    assert r.flare_loss_pct == pytest.approx(4.0 * da_k, rel=1e-9)
    assert r.takeoff_run_increase_pct == pytest.approx(10.0 * da_k, rel=1e-9)
    assert r.engine_power_loss_pct == pytest.approx(3.5 * da_k, rel=1e-9)


@pytest.mark.unit
def test_turboprop_has_no_piston_power_loss():
    r = _calc(elev_ft=5000.0, aircraft_model="turboprop")
    assert r.engine_power_loss_pct is None


@pytest.mark.unit
def test_negative_density_altitude_never_reports_performance_credit():
    r = _calc(elev_ft=0.0, oat_c=-30.0, td_c=-40.0)
    assert r.density_altitude_ft < 0
    assert r.flare_loss_pct == 0.0
    assert r.takeoff_run_increase_pct == 0.0
    assert r.engine_power_loss_pct == 0.0


# ---------------------------------------------------------------------------
# Matriz de riesgo — umbrales del ticket
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize(
    "wl_eff, da_ft, expected",
    [
        (1.00, 0.0, "verde"),
        (1.10, 2999.9, "verde"),          # WL_eff ≤ 1.10×nom y DA < 3000
        (1.00, 3000.0, "amarillo"),       # DA ∈ [3000, 6000]
        (1.11, 0.0, "amarillo"),          # WL_eff > 1.10×nom
        (1.00, 5999.9, "amarillo"),
        (1.00, 6000.0, "naranja"),        # borde compartido → la categoría más severa
        (1.26, 0.0, "naranja"),           # WL_eff > 1.25×nom
        (1.00, 9000.0, "naranja"),        # DA ∈ [6000, 9000]
        (1.00, 9000.1, "rojo"),           # DA > 9000
        (1.36, 0.0, "rojo"),              # WL_eff > 1.35×nom
        (1.30, 9500.0, "rojo"),           # gana la condición más severa
    ],
)
def test_classify_risk_thresholds(wl_eff, da_ft, expected):
    assert classify_risk(wl_eff=wl_eff, wl_nom=1.0, da_ft=da_ft) == expected


@pytest.mark.unit
def test_end_to_end_hot_high_day_is_orange():
    r = _calc(elev_ft=5000.0, oat_c=35.0, td_c=10.0)
    assert 6000.0 <= r.density_altitude_ft <= 9000.0
    assert r.risk_level == "naranja"


# ---------------------------------------------------------------------------
# Textos de decisión
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_green_has_a_single_all_clear_text():
    r = _calc()
    assert len(r.decision_texts) == 1


@pytest.mark.unit
def test_piston_gets_mixture_advice_from_yellow_upwards_but_turboprop_does_not():
    piston = _calc(elev_ft=4000.0, oat_c=30.0, aircraft_model="piston")
    turbo = _calc(elev_ft=4000.0, oat_c=30.0, aircraft_model="turboprop")
    assert piston.risk_level != "verde"
    assert any("mezcla" in t.lower() for t in piston.decision_texts)
    assert not any("mezcla" in t.lower() for t in turbo.decision_texts)


@pytest.mark.unit
def test_orange_asks_to_raise_turn_initiation_height_by_45_m():
    r = _calc(elev_ft=5000.0, oat_c=35.0, td_c=10.0)
    assert r.risk_level == "naranja"
    assert any("45 metros" in t for t in r.decision_texts)


@pytest.mark.unit
def test_red_recommends_not_swooping():
    r = _calc(elev_ft=8000.0, oat_c=38.0, td_c=15.0)
    assert r.risk_level == "rojo"
    assert any("swooping" in t.lower() for t in r.decision_texts)
