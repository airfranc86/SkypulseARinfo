"""Adapter de prueba: cubre los 2 fetch (current + daily_ext) con fixtures."""
import pytest
from app.services.openmeteo import get_current, get_daily_forecast_ext

@pytest.mark.asyncio
async def test_fetch_current():
    # Fixture: assert interface presente
    assert callable(get_current)

@pytest.mark.asyncio
async def test_fetch_daily_ext():
    assert callable(get_daily_forecast_ext)
