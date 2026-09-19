"""Tests de `build_rain_forecast`: lluvia en las próximas 24 h y riesgo de llovizna, desde Open-Meteo.

D1 — humedad>=80 y nubosidad>=70 ahora, sin lluvia → "Llovizna posible" / "media"
D2 — poca humedad y poca nubosidad → "Sin lluvia esperada" / "alta"
D3 — lluvia prevista → "Lluvia esperada hoy" / "alta" (no se evalúa llovizna)
D4 — humedad>=80 pero nubosidad<70 → NO es llovizna (hacen falta las dos)
D5 — nubosidad>=70 pero humedad<80 → NO es llovizna (hacen falta las dos)
D6 — promedios de las próximas franjas: humedad>=75 y nubosidad>=80 → llovizna por el pronóstico
D7 — solo cuentan las próximas 24 h: la lluvia de esta mañana o la de pasado mañana no
D8 — sin Open-Meteo: "Sin datos de lluvia", sin inventar un cielo seco
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.weather import SourceMeta, StationMeta, WeatherCurrentResponse
from app.services.dashboard_builder import build_rain_forecast
from tests.hourly_fixtures import AR
from tests.hourly_fixtures import make_hourly as _hourly

# 11:14 del 19/09/2026 en Argentina. Las próximas 24 h son las franjas de las 12:00 de hoy a las
# 09:00 de mañana.
NOW = datetime(2026, 9, 19, 11, 14, tzinfo=AR)


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


def _saturated(hours: int = 72, **overrides):
    """Toda la serie con humedad 80 % y nubosidad 85 %."""
    return _hourly(hours, humidities={i: 80.0 for i in range(hours)}, cloud_covers={i: 85.0 for i in range(hours)}, **overrides)


def _forecast(om, current=None):
    return build_rain_forecast(om, current or _current(), now=NOW)


# ---------------------------------------------------------------------------
# D1: humedad>=80 y nubosidad>=70 ahora → riesgo de llovizna
# ---------------------------------------------------------------------------

def test_drizzle_detected_when_current_saturated():
    result = _forecast(_hourly(72), _current(humidity=85.0, cloud_cover=75.0))

    assert result.status_text == "Llovizna posible"
    assert result.confidence_label == "media"
    assert result.has_rain_today is False


# ---------------------------------------------------------------------------
# D2: poca humedad y poca nubosidad → cielo seco, sin llovizna
# ---------------------------------------------------------------------------

def test_no_drizzle_when_conditions_clear():
    result = _forecast(_hourly(72), _current(humidity=55.0, cloud_cover=30.0))

    assert result.status_text == "Sin lluvia esperada"
    assert result.confidence_label == "alta"
    assert result.has_rain_today is False


# ---------------------------------------------------------------------------
# D3: lluvia prevista → confianza "alta", no se evalúa llovizna
# ---------------------------------------------------------------------------

def test_rain_detected_confidence_alta():
    om = _saturated(72, precipitations={15: 1.5, 16: 1.5, 17: 1.5})

    result = _forecast(om, _current(humidity=85.0, cloud_cover=90.0))

    assert result.status_text == "Lluvia esperada hoy"
    assert result.confidence_label == "alta"
    assert result.has_rain_today is True


# ---------------------------------------------------------------------------
# D4: humedad>=80 pero nubosidad<70 → NO es llovizna (hacen falta las dos)
# ---------------------------------------------------------------------------

def test_drizzle_not_detected_when_only_humidity_high():
    result = _forecast(_hourly(72), _current(humidity=85.0, cloud_cover=50.0))

    assert result.confidence_label == "alta"
    assert result.status_text == "Sin lluvia esperada"


# ---------------------------------------------------------------------------
# D5: nubosidad>=70 pero humedad<80 → NO es llovizna (hacen falta las dos)
# ---------------------------------------------------------------------------

def test_drizzle_not_detected_when_only_cloud_cover_high():
    result = _forecast(_hourly(72), _current(humidity=60.0, cloud_cover=80.0))

    assert result.confidence_label == "alta"
    assert result.status_text == "Sin lluvia esperada"


# ---------------------------------------------------------------------------
# D6: ahora despejado pero las próximas franjas saturadas → llovizna por el pronóstico
# ---------------------------------------------------------------------------

def test_drizzle_detected_from_upcoming_slot_averages():
    result = _forecast(_saturated(72), _current(humidity=60.0, cloud_cover=50.0))

    assert result.status_text == "Llovizna posible"
    assert result.confidence_label == "media"
    assert result.has_rain_today is False


def test_saturated_air_hours_ago_does_not_count_as_upcoming():
    """La humedad de la madrugada no dice nada de las próximas 12 h."""
    om = _hourly(72, humidities={i: 90.0 for i in range(9)}, cloud_covers={i: 95.0 for i in range(9)})

    result = _forecast(om, _current(humidity=60.0, cloud_cover=50.0))

    assert result.status_text == "Sin lluvia esperada"


# ---------------------------------------------------------------------------
# D7: la ventana es "las próximas 24 h desde ahora"
# ---------------------------------------------------------------------------

def test_rain_already_fallen_this_morning_is_not_forecast():
    om = _hourly(72, precipitations={6: 2.0, 7: 3.0, 8: 2.0})

    result = _forecast(om)

    assert result.has_rain_today is False
    assert result.status_text == "Sin lluvia esperada"


def test_rain_tomorrow_morning_inside_the_next_24_hours_counts():
    om = _hourly(72, precipitations={29: 2.0, 30: 3.0})  # 05:00 y 06:00 de mañana

    assert _forecast(om).has_rain_today is True


def test_rain_beyond_24_hours_is_ignored():
    om = _hourly(72, precipitations={40: 5.0, 41: 5.0})  # 16:00 de mañana: pasadas las 24 h

    assert _forecast(om).has_rain_today is False


def test_best_dry_window_runs_from_the_first_upcoming_slot_to_the_last_one():
    result = _forecast(_hourly(72))

    assert result.best_window_label == "Sin lluvia"
    assert result.best_window_start == "12:00"
    assert result.best_window_end == "09:00"


def test_best_dry_window_stops_at_the_rain():
    # llueve a las 18 h (franja de las 18:00): la franja seca más larga son las 3 de la madrugada a las 9
    om = _hourly(72, precipitations={16: 3.0, 17: 3.0, 18: 3.0})

    result = _forecast(om)

    assert result.best_window_start == "21:00"
    assert result.best_window_end == "09:00"


# ---------------------------------------------------------------------------
# D8: sin Open-Meteo no se inventa un cielo seco
# ---------------------------------------------------------------------------

def test_without_open_meteo_there_is_no_data():
    result = build_rain_forecast(None, _current(), now=NOW)

    assert result.status_text == "Sin datos de lluvia"
    assert result.confidence_label == "baja"
    assert result.has_rain_today is False
    assert result.best_window_start is None


# ---------------------------------------------------------------------------
# Secado de ropa: sale de las condiciones actuales y no cambió
# ---------------------------------------------------------------------------

def test_drying_is_fast_with_dry_air_wind_and_warmth():
    result = _forecast(_hourly(72), _current(humidity=50.0, wind_speed_kmh=15.0, temp_c=22.0))

    assert result.is_ideal_for_drying is True
    assert result.drying_label == "Secado rápido"


def test_drying_is_slow_with_humid_air():
    result = _forecast(_hourly(72), _current(humidity=90.0, wind_speed_kmh=5.0, temp_c=12.0))

    assert result.is_ideal_for_drying is False
    assert result.drying_label == "Secado lento"


def test_drying_is_unknown_without_current_humidity():
    result = _forecast(_hourly(72), _current(humidity=None))

    assert result.drying_label is None
