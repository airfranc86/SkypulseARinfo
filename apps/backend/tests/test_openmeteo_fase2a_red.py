# Fase 2a RED — interface de los 5 fetch de openmeteo.py (plan 2026-10-08)
import pytest

def test_current_interface_red():
    from app.services.openmeteo import get_current, _CURRENT_FIELDS
    assert len(_CURRENT_FIELDS) == 10

def test_daily_ext_interface_red():
    from app.services.openmeteo import get_daily_forecast_ext, _DAILY_FIELDS
    assert len(_DAILY_FIELDS) == 14

def test_hourly_ext_interface_red():
    from app.services.openmeteo import get_hourly_forecast_ext, _HOURLY_FIELDS
    assert len(_HOURLY_FIELDS) == 11

def test_ecmwf_hourly_interface_red():
    from app.services.openmeteo import get_hourly_forecast_ecmwf, _ECMWF_HOURLY_FIELDS
    assert len(_ECMWF_HOURLY_FIELDS) == 5

def test_niebla_combined_interface_red():
    from app.services.openmeteo import get_visibility_forecast, _fetch_niebla_combined
    assert callable(_fetch_niebla_combined)
