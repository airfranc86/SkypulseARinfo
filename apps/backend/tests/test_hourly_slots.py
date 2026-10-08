"""Tests de `build_hourly_schema`: la tira horaria del dashboard sale de Open-Meteo, en franjas de 3 h.

Windy (plan Testing) devolvía los datos mezclados al azar, así que ya no alimenta nada de lo que ve
el usuario. Las franjas conservan la forma de siempre (una cada 3 h, con los milímetros de las 3 h
previas, como `past3hprecip` de Windy) para que la tira y el veredicto del héroe no cambien.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.dashboard_builder import build_hourly_schema
from app.services.openmeteo import HourlyForecastExt
from tests.hourly_fixtures import AR
from tests.hourly_fixtures import make_hourly as _hourly


def _slot(hourly: HourlyForecastExt, hour: int):
    """La franja de las `hour` h del primer día (índice de hora = hour)."""
    schema = build_hourly_schema(hourly)
    return next(e for e in schema.entries if e.date == "2026-09-19" and e.hour_label == f"{hour:02d}:00")


# ---------------------------------------------------------------------------
# Forma: una franja cada 3 h, en las horas locales múltiplo de 3
# ---------------------------------------------------------------------------

def test_one_slot_every_three_hours_on_local_hours():
    schema = build_hourly_schema(_hourly(48))

    assert [e.hour_label for e in schema.entries[:8]] == [
        "00:00", "03:00", "06:00", "09:00", "12:00", "15:00", "18:00", "21:00",
    ]
    assert len(schema.entries) == 16
    assert {e.date for e in schema.entries} == {"2026-09-19", "2026-09-20"}


def test_timestamps_and_dates_are_the_real_instants_of_each_slot():
    schema = build_hourly_schema(_hourly(48))
    slot = next(e for e in schema.entries if e.date == "2026-09-19" and e.hour_label == "18:00")

    assert slot.timestamp == int(datetime(2026, 9, 19, 18, 0, tzinfo=AR).timestamp())
    # 18:00 en Argentina son las 21:00 UTC
    assert slot.timestamp == int(datetime(2026, 9, 19, 21, 0, tzinfo=timezone.utc).timestamp())


def test_without_open_meteo_the_strip_is_empty():
    schema = build_hourly_schema(None)

    assert schema.entries == []


def test_the_strip_carries_only_its_entries():
    """Sin etiqueta ni probabilidad de consenso: ninguna pantalla las usaba."""
    assert set(build_hourly_schema(_hourly()).model_dump()) == {"entries"}
    assert set(build_hourly_schema(None).model_dump()) == {"entries"}


# ---------------------------------------------------------------------------
# Lluvia: los milímetros de las 3 h previas y una probabilidad de verdad
# ---------------------------------------------------------------------------

def test_precip_is_the_three_hour_total_ending_at_the_slot():
    # La tormenta de mañana en el pronóstico real: 4,4 + 1,7 + 2,3 mm entre las 16 y las 18 h
    hourly = _hourly(precipitations={16: 4.4, 17: 1.7, 18: 2.3, 19: 1.7, 20: 4.8, 21: 1.5})

    assert _slot(hourly, 15).precip_mm == pytest.approx(0.0)
    assert _slot(hourly, 18).precip_mm == pytest.approx(8.4)
    assert _slot(hourly, 21).precip_mm == pytest.approx(8.0)


def test_sampling_every_three_hours_does_not_lose_or_invent_rain():
    hourly = _hourly(precipitations={5: 0.4, 9: 2.0, 16: 4.4, 17: 1.7, 18: 2.3})
    schema = build_hourly_schema(hourly)

    total_slots = sum(e.precip_mm or 0.0 for e in schema.entries if e.date == "2026-09-19")
    total_hours = sum(hourly.precipitations[:24])
    assert total_slots == pytest.approx(total_hours)


def test_precip_prob_is_the_real_probability_not_a_zero_or_hundred():
    """Antes se fabricaba 0 o 100 según hubiera más de 0,1 mm en el slot de Windy."""
    hourly = _hourly(precip_probs={16: 42.0, 17: 67.0, 18: 86.0})

    slot = _slot(hourly, 18)
    assert slot.precip_prob == pytest.approx(86.0)  # el máximo de las 3 h
    assert _slot(hourly, 15).precip_prob == pytest.approx(0.0)


def test_a_probability_can_coexist_with_no_measurable_rain():
    """Probabilidad y cantidad son cosas distintas: 42 % con 0 mm sigue siendo 42 %."""
    hourly = _hourly(precip_probs={14: 42.0}, precipitations={14: 0.0})

    assert _slot(hourly, 15).precip_prob == pytest.approx(42.0)
    assert _slot(hourly, 15).precip_mm == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Cielo: el ícono sigue a lo peor de las 3 h, sin contradecir la lluvia
# ---------------------------------------------------------------------------

def test_weather_code_is_the_worst_of_the_window_and_the_icon_follows():
    hourly = _hourly(weather_codes={16: 3, 17: 51, 18: 95})

    slot = _slot(hourly, 18)
    assert slot.weather_code == 95
    # La serie de prueba trae 10 % de nubosidad: sol con tormenta.
    assert slot.icon == "thunderstorms-mostly-clear-day"


def test_the_icon_follows_the_cloud_cover_of_the_slot_hour():
    storm = {16: 3, 17: 51, 18: 95}
    cloudy = _hourly(weather_codes=storm, cloud_covers={18: 90.0})
    partly = _hourly(weather_codes=storm, cloud_covers={18: 40.0})

    assert _slot(cloudy, 18).icon == "thunderstorms"
    assert _slot(partly, 18).icon == "thunderstorms-day"


def test_the_night_slot_gets_the_night_variant():
    hourly = _hourly(weather_codes={21: 99}, cloud_covers={21: 10.0})

    slot = _slot(hourly, 21)
    assert slot.is_day is False
    assert slot.icon == "thunderstorms-mostly-clear-night-hail"


def test_the_icon_reads_the_sky_of_the_hour_of_the_worst_code_not_the_label_hour():
    # Tormenta a las 16 h bajo 90 % de nubes; a las 18 h (la hora de la franja) ya despejó.
    hourly = _hourly(weather_codes={16: 95}, cloud_covers={16: 90.0, 17: 60.0, 18: 5.0})

    slot = _slot(hourly, 18)
    assert slot.weather_code == 95
    assert slot.icon == "thunderstorms"


def test_a_storm_under_a_clear_sky_keeps_the_sun_even_if_the_label_hour_is_cloudy():
    # Tormenta aislada a las 16 h con cielo despejado; a las 18 h la franja ya está nublada.
    hourly = _hourly(weather_codes={16: 99}, cloud_covers={16: 5.0, 17: 50.0, 18: 90.0})

    assert _slot(hourly, 18).icon == "thunderstorms-mostly-clear-day-hail"


def test_without_cloud_cover_at_the_worst_hour_the_icon_is_neutral_never_another_hours_sky():
    hourly = _hourly(weather_codes={16: 95}, cloud_covers={16: None, 17: 5.0, 18: 5.0})

    assert _slot(hourly, 18).icon == "thunderstorms"


def test_when_the_worst_code_repeats_the_latest_hour_gives_the_sky():
    # El mismo código 95 a las 16 h (nublado) y a las 17 h (despejado): manda la última hora.
    hourly = _hourly(weather_codes={16: 95, 17: 95}, cloud_covers={16: 90.0, 17: 5.0, 18: 90.0})

    assert _slot(hourly, 18).icon == "thunderstorms-mostly-clear-day"


def test_the_slot_cloud_cover_stays_the_value_of_the_label_hour():
    # `cloud_cover` de la franja alimenta el aviso de llovizna junto con la humedad: no cambia.
    from app.services.hourly_slots import three_hour_slots

    hourly = _hourly(weather_codes={16: 95}, cloud_covers={16: 90.0, 18: 5.0})
    slot = next(s for s in three_hour_slots(hourly) if s.date == "2026-09-19" and s.hour_label == "18:00")

    assert slot.cloud_cover == pytest.approx(5.0)


def test_a_slot_without_cloud_cover_keeps_the_neutral_icon():
    hourly = _hourly(weather_codes={18: 99}, cloud_covers={18: None})

    assert _slot(hourly, 18).icon == "thunderstorms-overcast-hail"


def test_a_clear_window_keeps_a_clear_icon():
    slot = _slot(_hourly(), 12)

    assert slot.weather_code == 0
    assert slot.icon == "clear-day"


def test_temperature_and_day_flag_are_the_value_at_the_slot_hour():
    hourly = _hourly(temps_c={17: 25.0, 18: 21.5}, precipitations={17: 1.0})

    slot = _slot(hourly, 18)
    assert slot.temp_c == pytest.approx(21.5)
    assert slot.is_day is True
    assert _slot(hourly, 21).is_day is False


# ---------------------------------------------------------------------------
# Ráfagas y tormentas: lo que antes solo daba Windy
# ---------------------------------------------------------------------------

def test_gusts_use_the_strongest_of_the_window():
    hourly = _hourly(wind_gusts_kmh={16: 34.9, 17: 55.5, 18: 22.7})

    assert _slot(hourly, 18).wind_gusts_kmh == pytest.approx(55.5)


def test_convective_risk_uses_the_highest_cape_of_the_window():
    hourly = _hourly(cape_j_kg={16: 900.0, 17: 3200.0, 18: 1200.0})

    assert _slot(hourly, 18).convective_risk == "high"
    assert _slot(hourly, 12).convective_risk == "low"


def test_without_gust_or_cape_data_the_slot_says_unknown_instead_of_inventing_calm():
    hourly = _hourly()
    hourly = HourlyForecastExt(
        **{**hourly.__dict__, "wind_gusts_kmh": [], "cape_j_kg": []}
    )

    slot = _slot(hourly, 18)
    assert slot.wind_gusts_kmh is None
    assert slot.convective_risk is None


def test_freezing_level_is_carried_from_the_slot_hour():
    hourly = _hourly(freezing_level_heights_m={18: 3480.0})

    assert _slot(hourly, 18).freezing_level_height_m == pytest.approx(3480.0)


# ---------------------------------------------------------------------------
# Bordes
# ---------------------------------------------------------------------------

def test_first_slot_of_the_series_uses_only_the_hours_it_has():
    hourly = _hourly(precipitations={0: 0.7})

    assert _slot(hourly, 0).precip_mm == pytest.approx(0.7)


def test_missing_values_in_the_window_are_skipped_not_counted_as_zero():
    hourly = _hourly(precipitations={16: None, 17: 1.5, 18: None})

    assert _slot(hourly, 18).precip_mm == pytest.approx(1.5)


def test_a_window_with_no_data_at_all_is_unknown_not_dry():
    hourly = _hourly(precipitations={16: None, 17: None, 18: None})

    assert _slot(hourly, 18).precip_mm is None
