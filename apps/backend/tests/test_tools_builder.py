"""Armado de datos de las herramientas (tender ropa, deporte, lavar el auto) desde Open-Meteo.

Windy (plan Testing) devolvía los datos mezclados al azar; las herramientas ahora salen de la misma
serie horaria de Open-Meteo que el dashboard, en franjas de 3 h para la tira y agregada por día para
los pronósticos de varios días.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.services.hourly_slots import three_hour_slots, upcoming_slots
from app.services.tools_builder import conditions_now, daily_aggregates, outlook, slot_scores
from tests.hourly_fixtures import AR, make_hourly

# Sábado 19/09/2026, 16:39 en Argentina
NOW = datetime(2026, 9, 19, 16, 39, tzinfo=AR)


# ---------------------------------------------------------------------------
# Condiciones de ahora
# ---------------------------------------------------------------------------

def test_current_conditions_are_the_values_of_the_nearest_hour():
    om = make_hourly(temps_c={17: 27.0}, humidities={17: 41.0}, wind_speeds={17: 22.0})

    now = conditions_now(om, NOW)

    assert (now.temp_c, now.humidity, now.wind_speed_kmh) == (27.0, 41.0, 22.0)


def test_a_variable_the_series_does_not_have_is_unknown_not_zero():
    om = dataclasses.replace(make_hourly(), humidities=[])

    now = conditions_now(om, NOW)

    assert now.humidity is None
    assert now.temp_c == pytest.approx(20.0)


def test_an_empty_series_has_unknown_current_conditions():
    now = conditions_now(make_hourly(0), NOW)

    assert (now.temp_c, now.humidity, now.wind_speed_kmh) == (None, None, None)


# ---------------------------------------------------------------------------
# Lo que viene en las próximas horas
# ---------------------------------------------------------------------------

def test_outlook_adds_the_rain_of_the_next_hours_from_the_current_one():
    om = make_hourly(precipitations={17: 1.0, 20: 2.0, 24: 5.0})

    assert outlook(om, NOW, hours=6).precip_mm == pytest.approx(3.0)     # horas 17 a 22
    assert outlook(om, NOW, hours=12).precip_mm == pytest.approx(8.0)    # suma la de las 24


def test_outlook_does_not_count_what_already_fell_or_a_storm_that_already_passed():
    # A las 17:08 el valor de las 17:00 (lluvia de 16 a 17, código de tormenta) ya es pasado.
    om = make_hourly(precipitations={17: 2.0, 18: 1.0}, weather_codes={17: 95}, cape_j_kg={17: 1800.0})
    at_1708 = datetime(2026, 9, 19, 17, 8, tzinfo=AR)

    ahead = outlook(om, at_1708, hours=6)

    assert ahead.precip_mm == pytest.approx(1.0)
    assert ahead.storm_code is None
    assert ahead.cape_j_kg == pytest.approx(0.0)


def test_outlook_rain_is_unknown_when_no_hour_has_data():
    om = dataclasses.replace(make_hourly(), precipitations=[None] * 48)

    assert outlook(om, NOW, hours=6).precip_mm is None


def test_outlook_takes_the_highest_cape_of_the_window():
    om = make_hourly(cape_j_kg={19: 1390.0, 21: 300.0, 30: 4000.0})

    assert outlook(om, NOW, hours=6).cape_j_kg == pytest.approx(1390.0)


def test_outlook_reports_the_first_storm_code_of_the_window():
    om = make_hourly(weather_codes={18: 61, 19: 3, 20: 95, 21: 96})

    assert outlook(om, NOW, hours=6).storm_code == 95


def test_plain_rain_is_not_a_storm_code():
    assert outlook(make_hourly(weather_codes={19: 61, 20: 65}), NOW, hours=6).storm_code is None


def test_outlook_stops_where_the_series_ends():
    om = make_hourly(24, precipitations={22: 2.0, 23: 1.0})

    assert outlook(om, NOW, hours=12).precip_mm == pytest.approx(3.0)


def test_an_empty_series_has_no_outlook():
    result = outlook(make_hourly(0), NOW, hours=6)

    assert (result.precip_mm, result.cape_j_kg, result.storm_code) == (None, None, None)


# ---------------------------------------------------------------------------
# Puntaje de cada franja
# ---------------------------------------------------------------------------

def test_each_slot_is_scored_with_its_own_conditions():
    om = make_hourly(
        temps_c={18: 24.0}, humidities={18: 48.0}, wind_speeds={18: 14.0},
        precipitations={16: 0.5, 17: 0.5, 18: 1.0}, weather_codes={17: 95}, cape_j_kg={18: 1200.0},
    )
    calls: list[tuple] = []

    def score_fn(temp, humidity, wind, precip, weather_code=None, cape_j_kg=None):
        calls.append((temp, humidity, wind, precip, weather_code, cape_j_kg))
        return SimpleNamespace(score=61)

    scores = slot_scores(upcoming_slots(om, NOW, limit=1), score_fn)

    assert calls == [(24.0, 48.0, 14.0, 2.0, 95, 1200.0)]
    slot = upcoming_slots(om, NOW, limit=1)[0]
    assert (scores[0].timestamp, scores[0].hour_label, scores[0].score, scores[0].is_best) == (
        slot.timestamp, "18:00", 61, False,
    )


def test_scoring_keeps_the_order_and_the_count_of_the_slots():
    om = make_hourly()

    scores = slot_scores(three_hour_slots(om), lambda *a, **k: SimpleNamespace(score=10))

    assert [s.hour_label for s in scores[:3]] == ["00:00", "03:00", "06:00"]
    assert len(scores) == len(three_hour_slots(om))


# ---------------------------------------------------------------------------
# Un día por fecha
# ---------------------------------------------------------------------------

def test_one_aggregate_per_local_date_in_order():
    days = daily_aggregates(make_hourly(72), days=7)

    assert [d.date for d in days] == ["2026-09-19", "2026-09-20", "2026-09-21"]


def test_the_number_of_days_is_capped():
    assert len(daily_aggregates(make_hourly(72), days=2)) == 2


def test_temperature_is_the_max_and_min_of_the_day():
    days = daily_aggregates(make_hourly(temps_c={5: 9.5, 15: 31.0, 30: 40.0}), days=2)

    assert (days[0].temp_max_c, days[0].temp_min_c) == (31.0, 9.5)
    assert days[1].temp_max_c == pytest.approx(40.0)


def test_humidity_and_wind_are_the_mean_of_the_day_and_the_wind_also_has_its_max():
    om = make_hourly(24, humidities={0: 100.0, 1: 0.0}, wind_speeds={0: 34.0, 1: 34.0})

    day = daily_aggregates(om, days=1)[0]

    assert day.humidity_mean == pytest.approx((100.0 + 0.0 + 50.0 * 22) / 24)
    assert day.wind_speed_mean_kmh == pytest.approx((34.0 * 2 + 10.0 * 22) / 24)
    assert day.wind_speed_max_kmh == pytest.approx(34.0)


def test_rain_is_the_total_of_the_day_and_the_probability_the_highest():
    om = make_hourly(24, precipitations={17: 4.4, 18: 2.3, 19: 1.7}, precip_probs={17: 40.0, 18: 97.0, 19: 60.0})

    day = daily_aggregates(om, days=1)[0]

    assert day.precip_sum_mm == pytest.approx(8.4)
    assert day.precip_prob_max == pytest.approx(97.0)


def test_the_weather_code_is_the_worst_of_the_day():
    om = make_hourly(24, weather_codes={3: 3, 10: 61, 18: 96})

    assert daily_aggregates(om, days=1)[0].weather_code == 96


def test_cape_is_the_highest_of_the_day():
    assert daily_aggregates(make_hourly(24, cape_j_kg={17: 1390.0, 18: 900.0}), days=1)[0].cape_max_j_kg == 1390.0


def test_wind_direction_is_the_vector_mean_in_spanish_letters():
    # 350° y 10° promedian al norte; el promedio de los números daría el sur.
    om = make_hourly(24, wind_dirs_deg={h: (350.0 if h % 2 else 10.0) for h in range(24)})

    assert daily_aggregates(om, days=1)[0].wind_dir_cardinal == "N"


def test_a_west_wind_is_reported_as_o():
    om = make_hourly(24, wind_dirs_deg={h: 270.0 for h in range(24)})

    assert daily_aggregates(om, days=1)[0].wind_dir_cardinal == "O"


def test_a_day_without_a_variable_leaves_it_unknown_instead_of_zero():
    om = dataclasses.replace(
        make_hourly(24), wind_dirs_deg=[], cape_j_kg=[], humidities=[], precip_probs=[], precipitations=[None] * 24,
    )

    day = daily_aggregates(om, days=1)[0]

    assert day.wind_dir_cardinal is None
    assert day.cape_max_j_kg is None
    assert day.humidity_mean is None
    assert day.precip_prob_max is None
    assert day.precip_sum_mm is None
    assert day.temp_max_c == pytest.approx(20.0)


def test_an_empty_series_has_no_days():
    assert daily_aggregates(make_hourly(0), days=5) == []
