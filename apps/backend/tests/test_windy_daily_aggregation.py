"""Tests for WindyDailyEntry aggregation logic — specifically precip_prob denominator.

W1: denominator uses len(precips) not len(slots) → correct % when some slots have None
W2: all slots None → precip_prob is None (not 0)
W3: all slots below threshold → precip_prob == 0.0
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from app.services.windy import (
    WindyHourlyEntry,
    WindyDailyEntry,
    get_daily_forecast,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_slot(
    date: str = "2026-05-20",
    hour: int = 0,
    precip: float | None = None,
) -> WindyHourlyEntry:
    return WindyHourlyEntry(
        timestamp_ms=(1716163200 + hour * 3600) * 1000,
        timestamp_s=1716163200 + hour * 3600,
        date=date,
        hour_label=f"{hour:02d}:00",
        temp_c=20.0,
        humidity=60.0,
        wind_speed_kmh=10.0,
        wind_gust_kmh=15.0,
        wind_dir_deg=180.0,
        wind_dir_cardinal="S",
        precip_3h_mm=precip,
        cloud_cover_pct=30.0,
        dewpoint_c=10.0,
        temp_850_c=None,
    )


# ---------------------------------------------------------------------------
# W1 — denominator uses slots-with-data, not total slots
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_precip_prob_denominator_uses_precips_not_slots():
    """4 slots with precip data (2 rainy, 2 dry), 4 with None → 50.0%, not 25.0%."""
    slots = [
        _make_slot(hour=0, precip=0.5),   # rainy
        _make_slot(hour=3, precip=1.2),   # rainy
        _make_slot(hour=6, precip=0.0),   # dry (has data, not rainy)
        _make_slot(hour=9, precip=0.05),  # dry (below 0.1 threshold)
        _make_slot(hour=12, precip=None), # no data
        _make_slot(hour=15, precip=None), # no data
        _make_slot(hour=18, precip=None), # no data
        _make_slot(hour=21, precip=None), # no data
    ]

    with patch("app.services.windy.get_hourly_forecast", new=AsyncMock(return_value=slots)):
        result = await get_daily_forecast(-31.4, -64.2, days=1)

    assert len(result) == 1
    entry = result[0]
    assert entry.precip_prob == pytest.approx(50.0), (
        f"Expected 50.0% (2 rainy / 4 slots-with-data), got {entry.precip_prob}. "
        "Denominator must use len(precips), not len(slots)."
    )


# ---------------------------------------------------------------------------
# W2 — all slots None → precip_prob is None
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_precip_prob_none_when_all_slots_none():
    """When every slot has precip_3h_mm=None, precip_prob must be None (not 0)."""
    slots = [_make_slot(hour=h, precip=None) for h in range(0, 24, 3)]

    with patch("app.services.windy.get_hourly_forecast", new=AsyncMock(return_value=slots)):
        result = await get_daily_forecast(-31.4, -64.2, days=1)

    assert len(result) == 1
    assert result[0].precip_prob is None, (
        "All slots None → no data to compute ratio → must return None, not 0"
    )


# ---------------------------------------------------------------------------
# W3 — all slots below threshold → precip_prob == 0.0
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_precip_prob_zero_when_precips_all_below_threshold():
    """8 slots with values 0.05–0.09 (all below 0.1 mm threshold) → precip_prob == 0.0."""
    precip_values = [0.05, 0.06, 0.07, 0.08, 0.09, 0.05, 0.06, 0.07]
    slots = [
        _make_slot(hour=h * 3, precip=v)
        for h, v in enumerate(precip_values)
    ]

    with patch("app.services.windy.get_hourly_forecast", new=AsyncMock(return_value=slots)):
        result = await get_daily_forecast(-31.4, -64.2, days=1)

    assert len(result) == 1
    assert result[0].precip_prob == pytest.approx(0.0), (
        "0 rainy slots out of 8 with data → 0/8 * 100 == 0.0"
    )
