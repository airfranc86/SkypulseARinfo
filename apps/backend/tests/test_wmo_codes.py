"""Tests para el mapeo WMO → (description, icon)."""
from __future__ import annotations

import pytest

from app.utils.wmo_codes import (
    WMO_CODE_MAP,
    describe_wmo,
    icon_from_description_es,
    resolve_daily_icon,
)


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
    # Ícono neutro: el rayo no necesita sol (la variante -day embebe disco solar,
    # incoherente con una tormenta — mismo criterio que 'overcast').
    assert icon == "thunderstorms"


def test_storm_day_night_agnostic():
    _, icon_day = describe_wmo(95, is_day=True)
    _, icon_night = describe_wmo(95, is_day=False)
    assert icon_day == icon_night == "thunderstorms"


def test_snow_heavy():
    desc, icon = describe_wmo(75)
    assert "nieve" in desc.lower() or "Nieve" in desc
    assert "snow" in icon


def test_fog():
    desc, icon = describe_wmo(45, is_day=True)
    assert desc == "Niebla"
    # Ícono neutro: la niebla no lleva sol/luna (las variantes -day/-night
    # embeben un astro, incoherente — mismo criterio que 'overcast'/'thunderstorms').
    assert icon == "fog"


def test_fog_day_night_agnostic():
    _, icon_day = describe_wmo(45, is_day=True)
    _, icon_night = describe_wmo(45, is_day=False)
    assert icon_day == icon_night == "fog"

    # Código 48 (niebla con escarcha) comparte el mismo ícono neutro.
    _, icon_48 = describe_wmo(48, is_day=True)
    assert icon_48 == "fog"


def test_drizzle_light():
    desc, _ = describe_wmo(51)
    assert "Llovizna" in desc


def test_overcast():
    desc, icon = describe_wmo(3, is_day=True)
    assert desc == "Cubierto"
    assert icon == "overcast"


def test_overcast_day_night_agnostic():
    # 'overcast' es neutro (nube gris, sin sol) ⇒ mismo ícono día y noche.
    _, icon_day = describe_wmo(3, is_day=True)
    _, icon_night = describe_wmo(3, is_day=False)
    assert icon_day == icon_night == "overcast"


# ---------------------------------------------------------------------------
# Cobertura: todos los códigos esperados están en el mapa
# ---------------------------------------------------------------------------

def test_mandatory_codes_present():
    mandatory = [0, 1, 2, 3, 45, 48, 51, 53, 55, 61, 63, 65, 71, 73, 75, 80, 81, 82, 95, 96, 99]
    for code in mandatory:
        assert code in WMO_CODE_MAP, f"Código {code} no encontrado en WMO_CODE_MAP"


# ---------------------------------------------------------------------------
# Íconos nocturnos son distintos a diurnos en ciertos casos
# (código 3 'Cubierto' queda fuera: usa 'overcast' neutro, día == noche)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("code", [0, 1, 2])
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


# ---------------------------------------------------------------------------
# Granizo — códigos 96/99 (tormenta con granizo) usan ícono 'hail' propio,
# distinto del 95 (tormenta simple → thunderstorms).
# ---------------------------------------------------------------------------

def test_hail_storm_uses_hail_icon():
    _, icon96 = describe_wmo(96, is_day=True)
    assert icon96 == "hail"

    _, icon99 = describe_wmo(99, is_day=True)
    assert icon99 == "hail"


def test_hail_descriptions_unchanged():
    desc96, _ = describe_wmo(96)
    assert desc96 == "Tormenta con granizo"

    desc99, _ = describe_wmo(99)
    assert desc99 == "Tormenta intensa con granizo"


def test_hail_day_night_agnostic():
    # 'hail' es neutro (nube + granizo, sin sol) ⇒ mismo ícono día y noche.
    _, icon_day = describe_wmo(96, is_day=True)
    _, icon_night = describe_wmo(96, is_day=False)
    assert icon_day == icon_night == "hail"


def test_simple_storm_stays_thunderstorms():
    # Regresión: código 95 (tormenta SIN granizo) NO debe usar 'hail'.
    _, icon_day = describe_wmo(95, is_day=True)
    assert icon_day == "thunderstorms"
    assert icon_day != "hail"


# ---------------------------------------------------------------------------
# Snow grains (WMO 77): NO es granizo. Descripción correcta = "Granos de nieve".
# ---------------------------------------------------------------------------

def test_snow_grains_description():
    desc, icon = describe_wmo(77, is_day=True)
    assert desc == "Granos de nieve"
    assert "granizo" not in desc.lower()
    assert icon == "snow"


def test_resolve_daily_icon_hail_storm():
    # Pronóstico diario: 96/99 caen en 'hail' (code != 3 ⇒ sin override de lluvia).
    assert resolve_daily_icon(96, 80.0, is_day=True) == "hail"
    assert resolve_daily_icon(99, 50.0, is_day=False) == "hail"


# ---------------------------------------------------------------------------
# icon_from_description_es — texto español del SMN → ícono Meteocons
# (el SMN entrega descripción en texto pero NO entrega weather_code)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text, is_day, expected",
    [
        ("Cubierto", True, "overcast"),
        ("Cubierto", False, "overcast"),
        ("Nublado", True, "overcast"),
        ("Mayormente nublado", True, "overcast"),
        ("Algo nublado", True, "partly-cloudy-day"),
        ("Algo nublado", False, "partly-cloudy-night"),
        ("Parcialmente nublado", True, "partly-cloudy-day"),
        ("Ligeramente nublado", True, "partly-cloudy-day"),
        ("Despejado", True, "clear-day"),
        ("Despejado", False, "clear-night"),
        ("Cielo despejado", True, "clear-day"),
        ("Lluvia", True, "rain"),
        ("Lluvias", True, "rain"),
        ("Lluvias débiles", True, "rain"),
        ("Chaparrones", True, "rain"),
        ("Llovizna", True, "drizzle"),
        ("Lloviznas", True, "drizzle"),
        ("Tormenta", True, "thunderstorms"),
        ("Tormentas", False, "thunderstorms"),
        ("Niebla", True, "fog"),
        ("Neblina", True, "fog"),
        ("Bruma", False, "fog"),
        ("Nieve", True, "snow"),
        ("Nevadas", True, "snow"),
        ("Aguanieve", True, "sleet"),
    ],
)
def test_icon_from_description_es_known(text: str, is_day: bool, expected: str):
    assert icon_from_description_es(text, is_day) == expected


def test_icon_from_description_es_accent_insensitive():
    # Sin tilde debe matchear igual que con tilde.
    assert icon_from_description_es("nino lluvia", True) == "rain"
    assert icon_from_description_es("LLUVIA", True) == "rain"


@pytest.mark.parametrize("text", [None, "", "   ", "valor inexistente xyz"])
def test_icon_from_description_es_unknown_returns_none(text):
    assert icon_from_description_es(text, True) is None


def test_icon_from_description_es_tormenta_takes_priority_over_lluvia():
    # "Tormenta con lluvia" debe resolver a tormenta, no a lluvia simple.
    assert icon_from_description_es("Tormenta con lluvia", True) == "thunderstorms"


def test_icon_from_description_es_llovizna_not_confused_with_lluvia():
    assert icon_from_description_es("Llovizna", True) == "drizzle"


# ---------------------------------------------------------------------------
# resolve_daily_icon — pronóstico 7 días:
# Cubierto (código 3) + prob de lluvia alta ⇒ ícono 'rain' (nube llena + lluvia).
# Por decisión de producto, SOLO el código 3 dispara el override
# (un día "parcialmente nublado" con prob alta NO cambia de ícono).
# ---------------------------------------------------------------------------

def test_resolve_daily_icon_overcast_high_prob_uses_rain():
    assert resolve_daily_icon(3, 100.0, is_day=True) == "rain"


def test_resolve_daily_icon_overcast_threshold_inclusive():
    assert resolve_daily_icon(3, 60.0, is_day=True) == "rain"


def test_resolve_daily_icon_overcast_below_threshold_stays_overcast():
    assert resolve_daily_icon(3, 59.0, is_day=True) == "overcast"


def test_resolve_daily_icon_overcast_none_prob_stays_overcast():
    assert resolve_daily_icon(3, None, is_day=True) == "overcast"


def test_resolve_daily_icon_partly_cloudy_high_prob_unchanged():
    # Caso "Hoy": código parcial (2) con 92% NO cambia — decisión del usuario.
    assert resolve_daily_icon(2, 92.0, is_day=True) == "partly-cloudy-day"


def test_resolve_daily_icon_rain_has_no_day_night_variant():
    assert resolve_daily_icon(3, 70.0, is_day=False) == "rain"


def test_resolve_daily_icon_clear_unchanged():
    assert resolve_daily_icon(0, 0.0, is_day=True) == "clear-day"


def test_resolve_daily_icon_none_code_no_override():
    # code != 3 ⇒ sin override, cae al fallback de describe_wmo.
    assert resolve_daily_icon(None, 80.0, is_day=True) == "clear-day"
