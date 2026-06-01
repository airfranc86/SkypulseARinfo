"""Unit tests for drizzle risk detection in _build_rain_forecast.

D1 — current humidity>=80 AND cloud_cover>=70 with no precip → "Llovizna posible" / "media"
D2 — low humidity + low cloud → "Sin lluvia esperada" / "alta"
D3 — actual precip detected → "Lluvia esperada hoy" / "alta" (drizzle check bypassed)
D4 — humidity>=80 but cloud_cover<70 → NOT drizzle (both conditions required)
D5 — cloud_cover>=70 but humidity<80 → NOT drizzle (both conditions required)
D6 — Windy slot averages: hum_mean>=75 AND cloud_mean>=80 → drizzle via slots
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.routers.weather import _build_rain_forecast
from app.schemas.weather import SourceMeta, StationMeta, WeatherCurrentResponse
from app.services.windy import WindyHourlyEntry


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _meta() -> SourceMeta:
    station = StationMeta(
        name="CÓRDOBA AEROPUERTO",
        lat=-31.323,
        lon=-64.208,
        distance_km=15.2,
        observed_at=datetime.now(timezone.utc),
    )
    return SourceMeta(
        source="smn",
        reason="smn_nearby_fresh",
        station=station,
        fetched_at=datetime.now(timezone.utc),
        cache_hit=False,
    )


def _current(
    *,
    humidity: float | None = 60.0,
    cloud_cover: float | None = 30.0,
    wind_speed_kmh: float = 10.0,
    temp_c: float = 18.0,
) -> WeatherCurrentResponse:
    return WeatherCurrentResponse(
        lat=-31.4,
        lon=-64.2,
        temp_c=temp_c,
        feels_like_c=temp_c - 1.0,
        humidity=humidity,
        wind_speed_kmh=wind_speed_kmh,
        wind_dir_deg=270.0,
        wind_dir_cardinal="W",
        pressure_hpa=1013.0,
        precip_1h_mm=0.0,
        cloud_cover=cloud_cover,
        description="Nublado",
        meta=_meta(),
    )


def _windy_slot(
    *,
    precip_3h_mm: float = 0.0,
    humidity: float = 60.0,
    cloud_cover_pct: float = 30.0,
    i: int = 0,
) -> WindyHourlyEntry:
    base_ts_ms = 1716220800 * 1000
    ts_ms = base_ts_ms + i * 3 * 3600 * 1000
    return WindyHourlyEntry(
        timestamp_ms=ts_ms,
        timestamp_s=ts_ms // 1000,
        date="2026-05-20",
        hour_label=f"{(i * 3) % 24:02d}:00",
        temp_c=18.0,
        humidity=humidity,
        wind_speed_kmh=10.0,
        wind_gust_kmh=15.0,
        wind_dir_deg=270.0,
        wind_dir_cardinal="W",
        precip_3h_mm=precip_3h_mm,
        cloud_cover_pct=cloud_cover_pct,
        dewpoint_c=10.0,
        temp_850_c=5.0,
    )


def _dry_slots(n: int = 8, humidity: float = 60.0, cloud_cover_pct: float = 30.0) -> list[WindyHourlyEntry]:
    return [_windy_slot(i=i, humidity=humidity, cloud_cover_pct=cloud_cover_pct) for i in range(n)]


# ---------------------------------------------------------------------------
# D1: current humidity>=80 AND cloud_cover>=70 → drizzle risk
# ---------------------------------------------------------------------------

def test_drizzle_detected_when_current_saturated():
    result = _build_rain_forecast(
        windy_hourly=_dry_slots(),
        om_hourly=None,
        current=_current(humidity=85.0, cloud_cover=75.0),
    )
    assert result.status_text == "Llovizna posible"
    assert result.confidence_label == "media"
    assert result.has_rain_today is False


# ---------------------------------------------------------------------------
# D2: low humidity + low cloud cover → clear, no drizzle
# ---------------------------------------------------------------------------

def test_no_drizzle_when_conditions_clear():
    result = _build_rain_forecast(
        windy_hourly=_dry_slots(),
        om_hourly=None,
        current=_current(humidity=55.0, cloud_cover=30.0),
    )
    assert result.status_text == "Sin lluvia esperada"
    assert result.confidence_label == "alta"
    assert result.has_rain_today is False


# ---------------------------------------------------------------------------
# D3: actual precipitation detected → confidence "alta", drizzle check skipped
# ---------------------------------------------------------------------------

def test_rain_detected_confidence_alta():
    rainy_slots = [
        _windy_slot(precip_3h_mm=1.5, humidity=85.0, cloud_cover_pct=90.0, i=i)
        for i in range(8)
    ]
    result = _build_rain_forecast(
        windy_hourly=rainy_slots,
        om_hourly=None,
        current=_current(humidity=85.0, cloud_cover=90.0),
    )
    assert result.status_text == "Lluvia esperada hoy"
    assert result.confidence_label == "alta"
    assert result.has_rain_today is True


# ---------------------------------------------------------------------------
# D4: humidity>=80 but cloud_cover<70 → NOT drizzle (both conditions required)
# ---------------------------------------------------------------------------

def test_drizzle_not_detected_when_only_humidity_high():
    result = _build_rain_forecast(
        windy_hourly=_dry_slots(),
        om_hourly=None,
        current=_current(humidity=85.0, cloud_cover=50.0),
    )
    assert result.confidence_label == "alta"
    assert result.status_text == "Sin lluvia esperada"


# ---------------------------------------------------------------------------
# D5: cloud_cover>=70 but humidity<80 → NOT drizzle (both conditions required)
# ---------------------------------------------------------------------------

def test_drizzle_not_detected_when_only_cloud_cover_high():
    result = _build_rain_forecast(
        windy_hourly=_dry_slots(),
        om_hourly=None,
        current=_current(humidity=60.0, cloud_cover=80.0),
    )
    assert result.confidence_label == "alta"
    assert result.status_text == "Sin lluvia esperada"


# ---------------------------------------------------------------------------
# D6: current clear but Windy slot averages saturated → drizzle via upcoming slots
# ---------------------------------------------------------------------------

def test_drizzle_detected_from_windy_slot_averages():
    # Current conditions clear, but upcoming 4 slots have high humidity+cloud
    saturated_slots = _dry_slots(n=8, humidity=80.0, cloud_cover_pct=85.0)
    result = _build_rain_forecast(
        windy_hourly=saturated_slots,
        om_hourly=None,
        current=_current(humidity=60.0, cloud_cover=50.0),
    )
    assert result.status_text == "Llovizna posible"
    assert result.confidence_label == "media"
    assert result.has_rain_today is False
