"""Tests unitarios del cálculo de Altitud de Densidad (sin I/O)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.aeronautica import _RISK_INFO, classify_risk, compute_density_altitude

# El frontend reutiliza estos mismos textos en su estimación local (fail-open, mientras el
# backend despierta). Si divergen, el usuario ve dos mensajes distintos para el mismo nivel.
FRONTEND_RISK_MESSAGES = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "riskMessages.json"


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
    assert r.density_adjusted_wing_loading == pytest.approx(1.5, rel=0.005)
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
    assert high.density_adjusted_wing_loading > low.density_adjusted_wing_loading
    assert high.density_adjusted_wing_loading == pytest.approx(1.5 / high.sigma, rel=1e-9)


@pytest.mark.unit
def test_intermediate_values_are_exposed_for_audit():
    r = _calc(elev_ft=2000.0, qnh_hpa=1005.0, oat_c=30.0, td_c=20.0)
    assert r.isa_temperature_c == pytest.approx(15.0 - 1.98 * (r.pressure_altitude_ft / 1000.0), abs=1e-9)
    assert 0 < r.vapor_pressure_hpa < 60
    assert r.station_pressure_hpa < 1005.0  # menor que QNH por estar a 2000 ft
    assert r.virtual_temperature_c > 30.0  # el vapor de agua vuelve el aire menos denso


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
    "adjusted_wl, da_ft, expected",
    [
        (1.00, 0.0, "verde"),
        (1.10, 2999.9, "verde"),          # índice ≤ 1.10×nom y DA < 3000
        (1.00, 3000.0, "amarillo"),       # DA ∈ [3000, 6000)
        (1.11, 0.0, "amarillo"),          # índice > 1.10×nom
        (1.00, 5999.9, "amarillo"),
        (1.26, 0.0, "naranja"),           # índice > 1.25×nom
        (1.00, 6000.1, "naranja"),
        (1.36, 0.0, "rojo"),              # índice > 1.35×nom
        (1.30, 9500.0, "rojo"),           # gana la condición más severa
    ],
)
def test_classify_risk_thresholds(adjusted_wl, da_ft, expected):
    assert classify_risk(adjusted_wl=adjusted_wl, wl_nom=1.0, da_ft=da_ft) == expected


@pytest.mark.unit
def test_boundary_6000_ft_is_orange_by_documented_precedence():
    """El ticket define DA ∈ [3000, 6000] (amarillo) y [6000, 9000] (naranja): 6000 pertenece a
    ambos intervalos. Precedencia documentada: en un borde compartido gana la categoría más severa."""
    assert classify_risk(adjusted_wl=1.0, wl_nom=1.0, da_ft=6000.0) == "naranja"
    assert classify_risk(adjusted_wl=1.0, wl_nom=1.0, da_ft=5999.99) == "amarillo"


@pytest.mark.unit
def test_boundary_9000_ft_is_still_orange_and_red_starts_above():
    assert classify_risk(adjusted_wl=1.0, wl_nom=1.0, da_ft=9000.0) == "naranja"
    assert classify_risk(adjusted_wl=1.0, wl_nom=1.0, da_ft=9000.01) == "rojo"


@pytest.mark.unit
def test_boundary_3000_ft_is_yellow_not_green():
    assert classify_risk(adjusted_wl=1.0, wl_nom=1.0, da_ft=3000.0) == "amarillo"


@pytest.mark.unit
def test_end_to_end_hot_high_day_is_orange():
    r = _calc(elev_ft=5000.0, oat_c=35.0, td_c=10.0)
    assert 6000.0 <= r.density_altitude_ft <= 9000.0
    assert r.risk_level == "naranja"


# ---------------------------------------------------------------------------
# Mensajes de decisión — genéricos, sin números operativos inventados
# ---------------------------------------------------------------------------

EXPECTED_MESSAGES = {
    "verde": "Condiciones normales según los parámetros ingresados.",
    "amarillo": (
        "La densidad del aire reduce el margen de performance. "
        "Verificá distancias, velocidad y limitaciones del manual de vuelo."
    ),
    "naranja": (
        "Condiciones desfavorables para la performance. "
        "Recalculá con datos actualizados y considerá demorar o reevaluar la operación."
    ),
    "rojo": (
        "No iniciar la operación sin una evaluación específica de performance "
        "y autorización conforme a los procedimientos aplicables."
    ),
}

EXPECTED_CODES = {
    "verde": "NORMAL",
    "amarillo": "REDUCED_PERFORMANCE_MARGIN",
    "naranja": "UNFAVORABLE_PERFORMANCE",
    "rojo": "SPECIFIC_EVALUATION_REQUIRED",
}

_CASES = {
    "verde": dict(elev_ft=0.0, oat_c=15.0, td_c=5.0),
    "amarillo": dict(elev_ft=2000.0, oat_c=25.0, td_c=10.0),
    "naranja": dict(elev_ft=5000.0, oat_c=35.0, td_c=10.0),
    "rojo": dict(elev_ft=8000.0, oat_c=38.0, td_c=15.0),
}


@pytest.mark.unit
@pytest.mark.parametrize("level", ["verde", "amarillo", "naranja", "rojo"])
def test_each_level_has_its_documented_message_and_code(level):
    r = _calc(**_CASES[level])
    assert r.risk_level == level
    assert r.risk_message == EXPECTED_MESSAGES[level]
    assert r.risk_code == EXPECTED_CODES[level]


@pytest.mark.unit
def test_risk_messages_match_frontend_copy():
    if not FRONTEND_RISK_MESSAGES.exists():
        pytest.skip("checkout sin apps/frontend (deploy solo backend)")
    frontend = json.loads(FRONTEND_RISK_MESSAGES.read_text(encoding="utf-8"))
    backend = {level: message for level, (_, message) in _RISK_INFO.items()}
    assert frontend == backend


@pytest.mark.unit
@pytest.mark.parametrize("level", ["verde", "amarillo", "naranja", "rojo"])
def test_message_does_not_depend_on_aircraft_model(level):
    piston = _calc(**_CASES[level], aircraft_model="piston")
    turbo = _calc(**_CASES[level], aircraft_model="turboprop")
    assert piston.risk_message == turbo.risk_message


@pytest.mark.unit
@pytest.mark.parametrize("level", ["verde", "amarillo", "naranja", "rojo"])
def test_messages_never_prescribe_unsourced_operational_numbers(level):
    message = _calc(**_CASES[level]).risk_message
    assert not any(ch.isdigit() for ch in message)
    assert "mezcla" not in message.lower()
