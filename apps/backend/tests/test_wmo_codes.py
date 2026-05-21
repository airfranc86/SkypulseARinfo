"""Tests para el mapeo WMO → (description, icon)."""
from __future__ import annotations

import pytest

from app.utils.wmo_codes import WMO_CODE_MAP, describe_wmo


# ---------------------------------------------------------------------------
# Todos los códigos del mapa devuelven descripción e ícono no vacíos
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("code", list(WMO_CODE_MAP.keys()))
def test_all_codes_return_description(code: int):
    desc, icon = describe_wmo(code, is_day=True)
    assert desc, f"WMO {code}: descripción vacía"
    assert icon, f"WMO {code}: ícono vacío"


@pytest.mark.parametrize("code", list(WMO_CODE_MAP.keys()))
def test_all_codes_night_return_valid(code: int):
    desc, icon = describe_wmo(code, is_day=False)
    assert desc
    assert icon


# ---------------------------------------------------------------------------
# Fallback para códigos no mapeados
# ---------------------------------------------------------------------------

def test_unknown_code_fallback():
    desc, icon = describe_wmo(999, is_day=True)
    assert desc == "Sin datos"
    assert icon == "clear-day"


def test_none_code_fallback():
    desc, icon = describe_wmo(None, is_day=True)
    assert desc == "Sin datos"
    assert icon == "clear-day"


def test_negative_code_fallback():
    desc, icon = describe_wmo(-1, is_day=True)
    assert desc == "Sin datos"


# ---------------------------------------------------------------------------
# Casos concretos — day vs night
# ---------------------------------------------------------------------------

def test_clear_day_icon():
    _, icon = describe_wmo(0, is_day=True)
    assert icon == "clear-day"


def test_clear_night_icon():
    _, icon = describe_wmo(0, is_day=False)
    assert icon == "clear-night"


def test_rain_moderate_description():
    desc, _ = describe_wmo(63)
    assert desc == "Lluvia moderada"


def test_storm_description():
    desc, icon = describe_wmo(95, is_day=True)
    assert desc == "Tormenta"
    assert "thunderstorms" in icon


def test_snow_heavy():
    desc, icon = describe_wmo(75)
    assert "nieve" in desc.lower() or "Nieve" in desc
    assert "snow" in icon


def test_fog():
    desc, icon = describe_wmo(45, is_day=True)
    assert desc == "Niebla"
    assert "fog" in icon


def test_drizzle_light():
    desc, _ = describe_wmo(51)
    assert "Llovizna" in desc


def test_overcast():
    desc, icon = describe_wmo(3, is_day=True)
    assert desc == "Cubierto"
    assert "overcast" in icon


# ---------------------------------------------------------------------------
# Cobertura: todos los códigos esperados están en el mapa
# ---------------------------------------------------------------------------

def test_mandatory_codes_present():
    mandatory = [0, 1, 2, 3, 45, 48, 51, 53, 55, 61, 63, 65, 71, 73, 75, 80, 81, 82, 95, 96, 99]
    for code in mandatory:
        assert code in WMO_CODE_MAP, f"Código {code} no encontrado en WMO_CODE_MAP"


# ---------------------------------------------------------------------------
# Íconos nocturnos son distintos a diurnos en ciertos casos
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("code", [0, 1, 2, 3])
def test_day_night_icons_differ_for_clear_codes(code: int):
    _, icon_day = describe_wmo(code, is_day=True)
    _, icon_night = describe_wmo(code, is_day=False)
    assert icon_day != icon_night, f"WMO {code}: esperaba íconos distintos día/noche"


# ---------------------------------------------------------------------------
# Sleet para llovizna helada
# ---------------------------------------------------------------------------

def test_freezing_drizzle_uses_sleet():
    _, icon = describe_wmo(56)
    assert icon == "sleet"

    _, icon2 = describe_wmo(57)
    assert icon2 == "sleet"
