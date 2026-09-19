"""Franjas de 3 h y lecturas puntuales que comparten el dashboard y las herramientas."""
from __future__ import annotations

import dataclasses
from datetime import datetime

import pytest

from app.services.hourly_slots import (
    current_temp_850,
    nearest_hour_index,
    next_hour_index,
    three_hour_slots,
    upcoming_slots,
)
from tests.hourly_fixtures import AR, make_hourly

# Sábado 19/09/2026, 16:39 en Argentina
NOW = datetime(2026, 9, 19, 16, 39, tzinfo=AR)


def _slot_at(hour: int, om):
    return next(s for s in three_hour_slots(om) if s.date == "2026-09-19" and s.hour_label == f"{hour:02d}:00")


# ---------------------------------------------------------------------------
# Viento de la franja
# ---------------------------------------------------------------------------

def test_a_slot_carries_the_wind_speed_of_its_hour():
    om = make_hourly(wind_speeds={18: 33.0})

    assert _slot_at(18, om).wind_speed_kmh == pytest.approx(33.0)
    assert _slot_at(15, om).wind_speed_kmh == pytest.approx(10.0)


def test_wind_speed_is_unknown_when_the_series_has_none():
    om = dataclasses.replace(make_hourly(), wind_speeds=[])

    assert _slot_at(18, om).wind_speed_kmh is None


# ---------------------------------------------------------------------------
# Franjas que vienen
# ---------------------------------------------------------------------------

def test_upcoming_starts_at_the_slot_that_covers_the_current_hour():
    # A las 16:39 la franja de las 15:00 ya terminó hace más de una hora; la primera es la de las 18:00.
    slots = upcoming_slots(make_hourly(), NOW)

    assert slots[0].hour_label == "18:00"
    assert slots[0].date == "2026-09-19"


def test_a_slot_that_ended_less_than_an_hour_ago_still_counts():
    at_1530 = datetime(2026, 9, 19, 15, 30, tzinfo=AR)

    assert upcoming_slots(make_hourly(), at_1530)[0].hour_label == "15:00"


def test_the_grace_period_decides_how_long_an_ended_slot_still_counts():
    at_1545 = datetime(2026, 9, 19, 15, 45, tzinfo=AR)
    at_1520 = datetime(2026, 9, 19, 15, 20, tzinfo=AR)

    assert upcoming_slots(make_hourly(), at_1545, grace_s=1800)[0].hour_label == "18:00"
    assert upcoming_slots(make_hourly(), at_1520, grace_s=1800)[0].hour_label == "15:00"


def test_upcoming_respects_the_limit():
    assert [s.hour_label for s in upcoming_slots(make_hourly(), NOW, limit=3)] == ["18:00", "21:00", "00:00"]


def test_without_a_limit_upcoming_returns_every_remaining_slot():
    # 48 h desde las 00:00 del 19: 16 franjas; quedan las de las 18:00 y 21:00 de hoy y las 8 de mañana.
    assert len(upcoming_slots(make_hourly(48), NOW)) == 2 + 8


def test_after_the_end_of_the_series_there_is_nothing_upcoming():
    assert upcoming_slots(make_hourly(24), datetime(2026, 9, 21, 12, 0, tzinfo=AR)) == []


# ---------------------------------------------------------------------------
# Hora más cercana
# ---------------------------------------------------------------------------

def test_the_nearest_hour_rounds_to_the_closest_one():
    assert nearest_hour_index(make_hourly(), NOW) == 17      # 16:39 está más cerca de las 17
    assert nearest_hour_index(make_hourly(), datetime(2026, 9, 19, 16, 20, tzinfo=AR)) == 16


def test_before_or_after_the_series_the_nearest_hour_is_the_closest_end():
    om = make_hourly(24)

    assert nearest_hour_index(om, datetime(2026, 9, 18, 12, 0, tzinfo=AR)) == 0
    assert nearest_hour_index(om, datetime(2026, 9, 25, 12, 0, tzinfo=AR)) == 23


def test_an_empty_series_has_no_nearest_hour():
    assert nearest_hour_index(make_hourly(0), NOW) is None


# ---------------------------------------------------------------------------
# Próxima hora: la que cierra la hora en curso
# ---------------------------------------------------------------------------

def test_the_next_hour_is_the_first_one_after_now():
    # A las 16:39 la hora en curso (16 a 17) la cierra el valor de las 17:00.
    assert next_hour_index(make_hourly(), NOW) == 17
    # A las 17:08 la de las 17:00 ya pasó: la hora en curso (17 a 18) la cierra la de las 18:00.
    assert next_hour_index(make_hourly(), datetime(2026, 9, 19, 17, 8, tzinfo=AR)) == 18


def test_exactly_on_the_hour_that_hour_is_already_past():
    assert next_hour_index(make_hourly(), datetime(2026, 9, 19, 17, 0, tzinfo=AR)) == 18


def test_before_the_series_the_next_hour_is_the_first_one():
    assert next_hour_index(make_hourly(24), datetime(2026, 9, 18, 12, 0, tzinfo=AR)) == 0


def test_after_the_end_of_the_series_there_is_no_next_hour():
    assert next_hour_index(make_hourly(24), datetime(2026, 9, 25, 12, 0, tzinfo=AR)) is None
    assert next_hour_index(make_hourly(0), NOW) is None


# ---------------------------------------------------------------------------
# Temperatura a 850 hPa
# ---------------------------------------------------------------------------

def test_temp_850_is_the_value_of_the_nearest_hour():
    assert current_temp_850(make_hourly(temps_850_c={17: 7.5}), NOW) == pytest.approx(7.5)


def test_temp_850_is_unknown_without_data():
    assert current_temp_850(None, NOW) is None
    assert current_temp_850(dataclasses.replace(make_hourly(), temps_850_c=[]), NOW) is None
    assert current_temp_850(make_hourly(temps_850_c={17: None}), NOW) is None
