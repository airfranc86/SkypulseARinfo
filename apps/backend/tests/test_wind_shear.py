"""Tests unitarios del cálculo de cizalladura (LLWS) en aproximación (sin I/O)."""
from __future__ import annotations

import json
import math
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from app.services.wind_shear import (
    _DRIVER_MESSAGES,
    _RISK_INFO,
    _THERMAL_MESSAGES,
    classify_risk,
    compute_wind_shear,
)

# El frontend reutiliza estos textos en su estimación local (fail-open, mientras el backend
# despierta). Si divergen, el usuario ve dos mensajes distintos para el mismo nivel.
FRONTEND_MESSAGES = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "windShearMessages.json"

# Casos de borde compartidos con el frontend (tests/windShear.test.ts los lee del mismo archivo):
# si los dos cálculos divergen en un borde, uno de los dos tests falla.
BOUNDARY_FIXTURE = Path(__file__).resolve().parents[2] / "frontend" / "tests" / "fixtures" / "windShearBoundaries.json"


def _load_boundary_fixture() -> dict:
    if not BOUNDARY_FIXTURE.exists():
        return {"tolerance": 1e-9, "cases": []}  # checkout sin apps/frontend: el parametrize queda vacío
    return json.loads(BOUNDARY_FIXTURE.read_text(encoding="utf-8"))


_BOUNDARY = _load_boundary_fixture()

LEVELS = ["verde", "amarillo", "naranja", "rojo"]


def _calc(**overrides):
    """Perfil base: viento constante de 10 kt desde el norte (dir 0, trigonometría exacta),
    sin ráfaga y sin temperaturas. Cizalladura = 0."""
    params = dict(
        surface_wind_dir_deg=0.0,
        surface_wind_speed_kt=10.0,
        surface_gust_kt=None,
        wind_500ft_dir_deg=0.0,
        wind_500ft_speed_kt=10.0,
        wind_1000ft_dir_deg=None,
        wind_1000ft_speed_kt=None,
        surface_temp_c=None,
        temp_1000ft_c=None,
    )
    params.update(overrides)
    return compute_wind_shear(**params)


def _calc_500(speed_500_kt: float, **overrides):
    """Superficie en calma vs. viento a 500 ft de `speed_500_kt` (misma dirección):
    cizalladura = speed_500_kt / 5 kt por cada 100 ft, con aritmética exacta."""
    return _calc(surface_wind_speed_kt=0.0, wind_500ft_speed_kt=speed_500_kt, **overrides)


# ---------------------------------------------------------------------------
# Matemática vectorial
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_speed_change_only_known_case():
    # 270/10 en superficie vs 270/30 a 500 ft: 20 kt sobre 5 centenas de pie = 4,0 kt/100 ft.
    r = _calc(
        surface_wind_dir_deg=270.0, surface_wind_speed_kt=10.0,
        wind_500ft_dir_deg=270.0, wind_500ft_speed_kt=30.0,
    )
    assert len(r.layers) == 1
    assert (r.layers[0].from_ft, r.layers[0].to_ft) == (0, 500)
    assert r.layers[0].shear_kt_per_100ft == pytest.approx(4.0, abs=1e-9)
    assert r.max_shear_kt_per_100ft == pytest.approx(4.0, abs=1e-9)
    assert r.risk_level == "amarillo"


@pytest.mark.unit
def test_pure_direction_change_is_a_vector_difference():
    # 360/20 vs 270/20: misma rapidez, el vector cambia 90°. |ΔV| = 20·√2 ≈ 28,28 kt → 5,66 kt/100 ft.
    r = _calc(
        surface_wind_dir_deg=360.0, surface_wind_speed_kt=20.0,
        wind_500ft_dir_deg=270.0, wind_500ft_speed_kt=20.0,
    )
    # La cizalladura se redondea a 6 decimales donde se calcula: la tolerancia es la del redondeo.
    assert r.max_shear_kt_per_100ft == pytest.approx(20.0 * math.sqrt(2.0) / 5.0, abs=1e-6)
    assert r.max_shear_kt_per_100ft == pytest.approx(5.657, abs=1e-3)
    assert r.risk_level == "amarillo"


@pytest.mark.unit
def test_opposite_directions_add_up():
    # 90/10 vs 270/10: vientos opuestos → |ΔV| = 20 kt → 4,0 kt/100 ft.
    r = _calc(
        surface_wind_dir_deg=90.0, surface_wind_speed_kt=10.0,
        wind_500ft_dir_deg=270.0, wind_500ft_speed_kt=10.0,
    )
    assert r.max_shear_kt_per_100ft == pytest.approx(4.0, abs=1e-9)


@pytest.mark.unit
def test_same_wind_at_both_levels_has_zero_shear():
    r = _calc(surface_wind_dir_deg=123.0, surface_wind_speed_kt=14.0,
              wind_500ft_dir_deg=123.0, wind_500ft_speed_kt=14.0)
    assert r.max_shear_kt_per_100ft == pytest.approx(0.0, abs=1e-9)
    assert r.risk_level == "verde"


@pytest.mark.unit
def test_gust_is_not_used_as_the_bottom_vector_of_the_layer():
    # La ráfaga mide variabilidad en superficie; la cizalladura usa el viento sostenido.
    calm = _calc(surface_gust_kt=None)
    gusty = _calc(surface_gust_kt=40.0)
    assert gusty.max_shear_kt_per_100ft == pytest.approx(calm.max_shear_kt_per_100ft, abs=1e-12)


# ---------------------------------------------------------------------------
# Capas
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_without_1000ft_wind_there_is_a_single_layer():
    r = _calc()
    assert [(layer.from_ft, layer.to_ft) for layer in r.layers] == [(0, 500)]
    assert (r.max_layer.from_ft, r.max_layer.to_ft) == (0, 500)


@pytest.mark.unit
def test_with_1000ft_wind_there_are_two_layers():
    r = _calc(wind_1000ft_dir_deg=0.0, wind_1000ft_speed_kt=20.0)
    assert [(layer.from_ft, layer.to_ft) for layer in r.layers] == [(0, 500), (500, 1000)]
    # 10 → 10 kt: 0; 10 → 20 kt: 10 kt / 5 = 2,0.
    assert r.layers[0].shear_kt_per_100ft == pytest.approx(0.0, abs=1e-9)
    assert r.layers[1].shear_kt_per_100ft == pytest.approx(2.0, abs=1e-9)


@pytest.mark.unit
def test_upper_layer_can_be_the_max_layer_and_drives_the_level():
    # 0–500 ft: 10 → 12 kt (0,4); 500–1000 ft: 12 → 60 kt (9,6) → naranja por la capa alta.
    r = _calc(wind_500ft_speed_kt=12.0, wind_1000ft_dir_deg=0.0, wind_1000ft_speed_kt=60.0)
    assert (r.max_layer.from_ft, r.max_layer.to_ft) == (500, 1000)
    assert r.max_shear_kt_per_100ft == pytest.approx(9.6, abs=1e-9)
    assert r.risk_level == "naranja"


@pytest.mark.unit
def test_lower_layer_stays_max_layer_when_upper_is_weaker():
    r = _calc(wind_500ft_speed_kt=60.0, wind_1000ft_dir_deg=0.0, wind_1000ft_speed_kt=62.0)
    assert (r.max_layer.from_ft, r.max_layer.to_ft) == (0, 500)


@pytest.mark.unit
def test_equal_layers_report_the_lowest_one_as_max():
    # Perfil lineal: 10 → 20 → 30 kt, 2,0 kt/100 ft en ambas capas. Empate → capa más baja
    # (la más cercana al piso, la que más pesa en la toma de contacto).
    r = _calc(wind_500ft_speed_kt=20.0, wind_1000ft_dir_deg=0.0, wind_1000ft_speed_kt=30.0)
    assert r.layers[0].shear_kt_per_100ft == r.layers[1].shear_kt_per_100ft
    assert (r.max_layer.from_ft, r.max_layer.to_ft) == (0, 500)


@pytest.mark.unit
def test_max_layer_is_one_of_the_reported_layers():
    r = _calc(wind_500ft_speed_kt=33.0, wind_1000ft_dir_deg=90.0, wind_1000ft_speed_kt=44.0)
    assert r.max_layer in r.layers
    assert r.max_shear_kt_per_100ft == max(layer.shear_kt_per_100ft for layer in r.layers)


# ---------------------------------------------------------------------------
# Ráfaga – sostenido
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_gust_spread_is_zero_without_gust():
    assert _calc(surface_gust_kt=None).gust_spread_kt == 0.0


@pytest.mark.unit
def test_gust_spread_is_gust_minus_sustained_speed():
    assert _calc(surface_wind_speed_kt=10.0, surface_gust_kt=25.0).gust_spread_kt == pytest.approx(15.0)


# ---------------------------------------------------------------------------
# Matriz de riesgo — umbrales (hipótesis de partida de FRA-119)
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize(
    "max_shear, gust_spread, expected",
    [
        (0.0, 0.0, "verde"),
        (3.99, 0.0, "verde"),
        (4.0, 0.0, "amarillo"),           # borde: 4 → amarillo
        (8.99, 0.0, "amarillo"),
        (9.0, 0.0, "naranja"),            # borde: 9 → naranja (el ticket dejaba un hueco 8–9)
        (11.99, 0.0, "naranja"),
        (12.0, 0.0, "naranja"),           # borde: exactamente 12 sigue siendo naranja
        (12.01, 0.0, "rojo"),             # rojo empieza estrictamente por encima de 12
        (0.0, 15.0, "verde"),             # borde: ráfaga–sostenido = 15 NO es rojo por sí solo
        (0.0, 15.1, "rojo"),
        (5.0, 15.0, "amarillo"),          # con cizalladura amarilla, el 15 exacto no escala
        (10.0, 20.0, "rojo"),             # gana la condición más severa
        (0.0, 14.0, "verde"),             # una ráfaga alta pero ≤ 15 no cambia el nivel
    ],
)
def test_classify_risk_thresholds(max_shear, gust_spread, expected):
    assert classify_risk(max_shear_kt_per_100ft=max_shear, gust_spread_kt=gust_spread) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "speed_500_kt, expected",
    [
        (19.95, "verde"),    # 3,99 kt/100 ft
        (20.0, "amarillo"),  # exactamente 4,0
        (44.95, "amarillo"), # 8,99
        (45.0, "naranja"),   # exactamente 9,0
        (60.0, "naranja"),   # exactamente 12,0
        (60.05, "rojo"),     # 12,01
    ],
)
def test_end_to_end_boundaries(speed_500_kt, expected):
    assert _calc_500(speed_500_kt).risk_level == expected


@pytest.mark.unit
def test_gust_spread_boundary_end_to_end():
    assert _calc(surface_wind_speed_kt=10.0, surface_gust_kt=25.0).risk_level == "verde"      # 15,0
    assert _calc(surface_wind_speed_kt=10.0, surface_gust_kt=25.1).risk_level == "rojo"       # 15,1


# ---------------------------------------------------------------------------
# Ruido de coma flotante en los bordes (FRA-119): rumbos que no caen sobre un eje
# ---------------------------------------------------------------------------

def _boundary_id(case: dict) -> str:
    return case["name"]


@pytest.mark.unit
@pytest.mark.parametrize("case", _BOUNDARY["cases"], ids=_boundary_id)
def test_shared_boundary_fixture(case):
    expected = case["expected"]
    tolerance = _BOUNDARY["tolerance"]

    r = compute_wind_shear(**case["request"])

    assert r.risk_level == expected["level"]
    assert r.max_shear_kt_per_100ft == pytest.approx(expected["max_shear_kt_per_100ft"], abs=tolerance)
    assert r.gust_spread_kt == pytest.approx(expected["gust_spread_kt"], abs=tolerance)
    assert list(r.drivers) == expected["drivers"]
    assert [r.max_layer.from_ft, r.max_layer.to_ft] == expected["max_layer"]
    # El valor que se informa es el mismo número con el que se decidió el nivel.
    assert classify_risk(r.max_shear_kt_per_100ft, r.gust_spread_kt) == r.risk_level


@pytest.mark.unit
def test_shared_boundary_fixture_is_not_empty():
    if not BOUNDARY_FIXTURE.exists():
        pytest.skip("checkout sin apps/frontend (deploy solo backend)")
    assert len(_BOUNDARY["cases"]) >= 50


@pytest.mark.unit
def test_exact_boundaries_hold_for_every_integer_direction():
    # 4, 9 y 12 kt/100 ft exactos (mismo rumbo, superficie en calma, rumbos opuestos) en los 361 rumbos.
    families = {
        "4 mismo rumbo": (dict(surface_wind_speed_kt=10.0, wind_500ft_speed_kt=30.0), 0, "amarillo"),
        "9 calma": (dict(surface_wind_speed_kt=0.0, wind_500ft_speed_kt=45.0), 0, "naranja"),
        "12 calma": (dict(surface_wind_speed_kt=0.0, wind_500ft_speed_kt=60.0), 0, "naranja"),
        "4 opuestos": (dict(surface_wind_speed_kt=8.0, wind_500ft_speed_kt=12.0), 180, "amarillo"),
        "9 opuestos": (dict(surface_wind_speed_kt=20.0, wind_500ft_speed_kt=25.0), 180, "naranja"),
        "12 opuestos": (dict(surface_wind_speed_kt=25.0, wind_500ft_speed_kt=35.0), 180, "naranja"),
    }
    failures = []
    for label, (speeds, turn_deg, expected) in families.items():
        for direction in range(361):
            r = _calc(
                surface_wind_dir_deg=float(direction),
                wind_500ft_dir_deg=float((direction + turn_deg) % 360),
                **speeds,
            )
            if r.risk_level != expected:
                failures.append((label, direction, r.risk_level, r.max_shear_kt_per_100ft))
    assert failures == []


@pytest.mark.unit
def test_gust_spread_subtraction_noise_does_not_count_as_over_fifteen():
    # 25,1 - 10,1 = 15,000000000000002 en coma flotante: el diferencial real es 15 y no es rojo.
    r = _calc(surface_wind_speed_kt=10.1, wind_500ft_speed_kt=10.1, surface_gust_kt=25.1)
    assert r.gust_spread_kt == 15.0
    assert r.risk_level == "verde"
    assert r.drivers == ()


@pytest.mark.unit
def test_layer_shear_and_gust_spread_are_rounded_to_six_decimals():
    # 360/20 vs 270/20: 20·√2 / 5 = 5,65685424949...; se redondea a 6 decimales donde se calcula.
    r = _calc(
        surface_wind_dir_deg=360.0, surface_wind_speed_kt=20.0, surface_gust_kt=20.3333333,
        wind_500ft_dir_deg=270.0, wind_500ft_speed_kt=20.0,
    )
    assert r.layers[0].shear_kt_per_100ft == 5.656854
    assert r.max_shear_kt_per_100ft == 5.656854
    assert r.gust_spread_kt == 0.333333


# ---------------------------------------------------------------------------
# Drivers
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_green_has_no_drivers():
    assert _calc().drivers == ()


@pytest.mark.unit
def test_shear_alone_is_the_driver_of_yellow_and_orange():
    assert _calc_500(25.0).drivers == ("shear",)   # amarillo
    assert _calc_500(50.0).drivers == ("shear",)   # naranja


@pytest.mark.unit
def test_gust_spread_alone_is_the_driver_of_a_red_without_shear():
    r = _calc(surface_wind_speed_kt=10.0, surface_gust_kt=30.0)
    assert r.risk_level == "rojo"
    assert r.drivers == ("gust_spread",)


@pytest.mark.unit
def test_both_drivers_when_both_reach_red():
    r = _calc_500(70.0, surface_gust_kt=20.0)  # shear 14 y ráfaga–sostenido 20
    assert r.risk_level == "rojo"
    assert r.drivers == ("shear", "gust_spread")


@pytest.mark.unit
def test_driver_below_the_chosen_level_is_not_listed():
    # Cizalladura amarilla (5,0) + ráfaga–sostenido roja: el nivel es rojo y solo la ráfaga lo explica.
    r = _calc_500(25.0, surface_gust_kt=20.0)
    assert r.risk_level == "rojo"
    assert r.drivers == ("gust_spread",)


@pytest.mark.unit
def test_gust_spread_below_red_threshold_is_not_listed_as_a_driver():
    # Sostenido 10 → 70 kt a 500 ft: 12,0 kt/100 ft (naranja). Ráfaga–sostenido 10: no cruza ningún umbral.
    r = _calc(surface_wind_speed_kt=10.0, surface_gust_kt=20.0, wind_500ft_speed_kt=70.0)
    assert r.risk_level == "naranja"
    assert r.drivers == ("shear",)


# ---------------------------------------------------------------------------
# Nota térmica (informativa)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_thermal_is_none_without_temperatures():
    assert _calc().thermal is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "surface_c, temp_1000_c, code, lapse",
    [
        (10.0, 12.0, "inversion", -2.0),   # más cálido arriba
        (20.0, 18.0, "neutral", 2.0),
        (15.0, 15.0, "neutral", 0.0),      # isotermia: ni inversión ni inestable
        (20.0, 15.0, "unstable", 5.0),     # > 2,99 °C/1000 ft (adiabático seco ≈ 9,8 °C/km)
    ],
)
def test_thermal_classification(surface_c, temp_1000_c, code, lapse):
    thermal = _calc(surface_temp_c=surface_c, temp_1000ft_c=temp_1000_c).thermal
    assert thermal is not None
    assert thermal.code == code
    assert thermal.lapse_c_per_1000ft == pytest.approx(lapse, abs=1e-9)


@pytest.mark.unit
def test_lapse_just_above_dry_adiabatic_is_unstable_and_just_below_is_neutral():
    assert _calc(surface_temp_c=13.0, temp_1000ft_c=10.0).thermal.code == "unstable"   # 3,00
    assert _calc(surface_temp_c=12.9, temp_1000ft_c=10.0).thermal.code == "neutral"    # 2,90


@pytest.mark.unit
@pytest.mark.parametrize("temps", [(10.0, 12.0), (20.0, 18.0), (20.0, 5.0)])
@pytest.mark.parametrize("speed_500_kt", [0.0, 25.0, 50.0, 70.0])
def test_thermal_never_changes_the_risk_level(speed_500_kt, temps):
    without = _calc_500(speed_500_kt)
    with_temps = _calc_500(speed_500_kt, surface_temp_c=temps[0], temp_1000ft_c=temps[1])
    assert with_temps.risk_level == without.risk_level
    assert with_temps.drivers == without.drivers
    assert with_temps.max_shear_kt_per_100ft == without.max_shear_kt_per_100ft


# ---------------------------------------------------------------------------
# Mensajes — genéricos, sin números inventados
# ---------------------------------------------------------------------------

EXPECTED_MESSAGES = {
    "verde": (
        "Cizalladura leve según los parámetros ingresados. "
        "No garantiza condiciones seguras: seguí monitoreando el viento."
    ),
    "amarillo": (
        "Riesgo de pérdida repentina de sustentación en final. "
        "Mantené margen de altura."
    ),
    "naranja": (
        "Riesgo alto de colapso del velamen y pérdida de control direccional. "
        "Evitá la aproximación si podés."
    ),
    "rojo": "Cizalladura extrema. No aterrizar en estas condiciones (No-Go).",
}

EXPECTED_CODES = {
    "verde": "SHEAR_LIGHT",
    "amarillo": "SHEAR_MODERATE",
    "naranja": "SHEAR_SEVERE",
    "rojo": "SHEAR_EXTREME",
}

_LEVEL_CASES = {
    "verde": dict(speed_500_kt=0.0),
    "amarillo": dict(speed_500_kt=25.0),
    "naranja": dict(speed_500_kt=50.0),
    "rojo": dict(speed_500_kt=70.0),
}


@pytest.mark.unit
@pytest.mark.parametrize("level", LEVELS)
def test_each_level_has_its_documented_message_and_code(level):
    r = _calc_500(_LEVEL_CASES[level]["speed_500_kt"])
    assert r.risk_level == level
    assert r.risk_message == EXPECTED_MESSAGES[level]
    assert r.risk_code == EXPECTED_CODES[level]


@pytest.mark.unit
def test_green_message_does_not_reassure_beyond_the_entered_data():
    # Verde solo dice que, con lo ingresado, la cizalladura es leve: nunca "operación normal".
    message = _RISK_INFO["verde"][1]
    assert "normal" not in message.lower()
    assert "no garantiza" in message.lower()
    assert "monitoreando" in message.lower()


@pytest.mark.unit
def test_risk_info_covers_every_level_exactly():
    assert set(_RISK_INFO) == set(LEVELS)


@pytest.mark.unit
def test_messages_cover_every_driver_and_thermal_code():
    assert set(_DRIVER_MESSAGES) == {"shear", "gust_spread"}
    assert set(_THERMAL_MESSAGES) == {"inversion", "unstable", "neutral"}


@pytest.mark.unit
def test_messages_match_frontend_copy():
    if not FRONTEND_MESSAGES.exists():
        pytest.skip("checkout sin apps/frontend (deploy solo backend)")
    frontend = json.loads(FRONTEND_MESSAGES.read_text(encoding="utf-8"))
    assert frontend == {
        "levels": {level: message for level, (_, message) in _RISK_INFO.items()},
        "drivers": dict(_DRIVER_MESSAGES),
        "thermal": dict(_THERMAL_MESSAGES),
    }


@pytest.mark.unit
def test_every_message_is_free_of_digits():
    messages = [message for _, message in _RISK_INFO.values()]
    messages += list(_DRIVER_MESSAGES.values()) + list(_THERMAL_MESSAGES.values())
    assert messages
    for message in messages:
        assert message.strip()
        assert not any(ch.isdigit() for ch in message), message


@pytest.mark.unit
def test_result_is_immutable():
    r = _calc()
    with pytest.raises(FrozenInstanceError):
        r.risk_level = "rojo"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        r.layers[0].shear_kt_per_100ft = 99.0  # type: ignore[misc]
