"""Tests para compute_moon_phase — verificación contra fechas conocidas."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.utils.moon_phase import MoonPhaseInfo, compute_moon_phase


# ---------------------------------------------------------------------------
# Casos conocidos (extraídos de almanaque astronómico)
# ---------------------------------------------------------------------------

# Luna Nueva: 2024-01-11 11:57 UTC
KNOWN_NEW_MOON = datetime(2024, 1, 11, 11, 57, 0, tzinfo=timezone.utc)

# Luna Llena: 2024-01-25 17:54 UTC
KNOWN_FULL_MOON = datetime(2024, 1, 25, 17, 54, 0, tzinfo=timezone.utc)

# Cuarto Creciente: ~2024-01-17 22:52 UTC (a ~7 días de luna nueva)
KNOWN_FIRST_QUARTER = datetime(2024, 1, 17, 22, 52, 0, tzinfo=timezone.utc)

# Cuarto Menguante: ~2024-02-02 23:18 UTC (a ~7 días de luna llena)
KNOWN_LAST_QUARTER = datetime(2024, 2, 2, 23, 18, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Tipo de retorno
# ---------------------------------------------------------------------------

def test_returns_moon_phase_info():
    result = compute_moon_phase(datetime(2024, 1, 15, tzinfo=timezone.utc))
    assert isinstance(result, MoonPhaseInfo)


def test_fields_present():
    result = compute_moon_phase(datetime(2024, 1, 15, tzinfo=timezone.utc))
    assert result.name
    assert result.icon
    assert 0.0 <= result.illumination <= 1.0


# ---------------------------------------------------------------------------
# Fases conocidas
# ---------------------------------------------------------------------------

def test_new_moon_illumination_near_zero():
    result = compute_moon_phase(KNOWN_NEW_MOON)
    assert result.illumination < 0.10, f"Illumination={result.illumination} debería ser cercana a 0 en luna nueva"


def test_new_moon_name():
    result = compute_moon_phase(KNOWN_NEW_MOON)
    assert result.name == "Nueva"


def test_new_moon_icon():
    result = compute_moon_phase(KNOWN_NEW_MOON)
    assert result.icon == "moon-new"


def test_full_moon_illumination_near_one():
    result = compute_moon_phase(KNOWN_FULL_MOON)
    assert result.illumination > 0.90, f"Illumination={result.illumination} debería ser cercana a 1 en luna llena"


def test_full_moon_name():
    result = compute_moon_phase(KNOWN_FULL_MOON)
    assert result.name == "Llena"


def test_full_moon_icon():
    result = compute_moon_phase(KNOWN_FULL_MOON)
    assert result.icon == "moon-full"


def test_first_quarter_phase():
    result = compute_moon_phase(KNOWN_FIRST_QUARTER)
    # ~7 días después de luna nueva → cuarto creciente o gibosa creciente
    assert result.name in ("Cuarto creciente", "Gibosa creciente", "Creciente iluminante")


def test_last_quarter_phase():
    result = compute_moon_phase(KNOWN_LAST_QUARTER)
    # ~7 días después de luna llena → cuarto menguante o gibosa menguante
    assert result.name in ("Cuarto menguante", "Gibosa menguante")


# ---------------------------------------------------------------------------
# Propiedad: illumination monotónica desde nueva → llena
# ---------------------------------------------------------------------------

def test_illumination_increases_new_to_full():
    """La iluminación debe crecer entre luna nueva y luna llena."""
    t_new = KNOWN_NEW_MOON
    t_mid = datetime(2024, 1, 18, tzinfo=timezone.utc)   # ~7 días
    t_full = KNOWN_FULL_MOON
    ill_new = compute_moon_phase(t_new).illumination
    ill_mid = compute_moon_phase(t_mid).illumination
    ill_full = compute_moon_phase(t_full).illumination
    assert ill_new < ill_mid < ill_full


# ---------------------------------------------------------------------------
# Naive datetime (sin tzinfo) — debe manejarse sin crash
# ---------------------------------------------------------------------------

def test_naive_datetime_does_not_crash():
    naive = datetime(2024, 6, 22, 12, 0, 0)  # sin tzinfo
    result = compute_moon_phase(naive)
    assert isinstance(result, MoonPhaseInfo)


# ---------------------------------------------------------------------------
# Fechas históricas y futuras
# ---------------------------------------------------------------------------

def test_historical_date():
    """Fecha histórica lejana (año 1900) no debe crashear."""
    result = compute_moon_phase(datetime(1900, 1, 1, tzinfo=timezone.utc))
    assert isinstance(result, MoonPhaseInfo)
    assert 0.0 <= result.illumination <= 1.0


def test_future_date():
    """Fecha futura (año 2100) no debe crashear."""
    result = compute_moon_phase(datetime(2100, 1, 1, tzinfo=timezone.utc))
    assert isinstance(result, MoonPhaseInfo)
    assert 0.0 <= result.illumination <= 1.0


# ---------------------------------------------------------------------------
# Todas las fases tienen icon válido (no vacío)
# ---------------------------------------------------------------------------

def test_all_returned_icons_are_non_empty():
    """Recorrer 30 días desde luna nueva y verificar que todos los iconos son válidos."""
    import datetime as dt
    valid_icons = {
        "moon-new", "moon-waxing-crescent", "moon-first-quarter",
        "moon-waxing-gibbous", "moon-full", "moon-waning-gibbous",
        "moon-last-quarter", "moon-waning-crescent",
    }
    for day in range(30):
        d = KNOWN_NEW_MOON + dt.timedelta(days=day)
        result = compute_moon_phase(d)
        assert result.icon in valid_icons, f"Día {day}: icon '{result.icon}' no reconocido"
