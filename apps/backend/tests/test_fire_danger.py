"""Tests unitarios para app.services.fire_danger.

El riesgo se estima con la serie horaria de Open-Meteo (temperatura, humedad, viento y lluvia); no hay
FWI: Open-Meteo no lo trae.

Cubre:
- compute_fire_risk: todos los umbrales y casos límite
- fire_entries_from_hourly: una entrada por hora, con la lluvia de las 3 h previas
- closest_to_now: la entrada más cercana a ahora
- get_fire_danger: pide 7 días a Open-Meteo
"""
from __future__ import annotations

import dataclasses
import time
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.services.fire_danger import (
    FireDangerEntry,
    closest_to_now,
    compute_fire_risk,
    fire_entries_from_hourly,
    get_fire_danger,
)
from tests.hourly_fixtures import AR, make_hourly

OPEN_METEO = "app.services.fire_danger.get_hourly_forecast_ext"


# ---------------------------------------------------------------------------
# compute_fire_risk
# ---------------------------------------------------------------------------

class TestComputeFireRisk:

    def test_all_none_returns_zero_muy_bajo(self):
        score, label = compute_fire_risk(None, None, None, None)
        assert score == 0.0
        assert label == "Muy bajo"

    def test_muy_bajo_label_below_20(self):
        score, label = compute_fire_risk(temp_c=10.0, humidity=60.0, wind_kmh=0.0, precip_mm=0.0)
        assert score < 20
        assert label == "Muy bajo"

    def test_bajo_label_between_20_and_40(self):
        # temp=25 → (25-10)/30*30=15, hum=40 → (60-40)/60*30=10, wind=0 → total=25
        score, label = compute_fire_risk(temp_c=25.0, humidity=40.0, wind_kmh=0.0, precip_mm=0.0)
        assert 20 <= score < 40
        assert label == "Bajo"

    def test_moderado_label_between_40_and_60(self):
        # temp=30 → 20pts, hum=30 → 15pts, wind=15 → 7.5pts = 42.5
        score, label = compute_fire_risk(temp_c=30.0, humidity=30.0, wind_kmh=15.0, precip_mm=0.0)
        assert 40 <= score < 60
        assert label == "Moderado"

    def test_alto_label_between_60_and_75(self):
        # temp=40→30pts, hum=15→22.5pts, wind=20→10pts = 62.5
        score, label = compute_fire_risk(temp_c=40.0, humidity=15.0, wind_kmh=20.0, precip_mm=0.0)
        assert 60 <= score < 75
        assert label == "Alto"

    def test_muy_alto_label_between_75_and_80(self):
        # temp=40→30pts, hum=0→30pts, wind=30→15pts = 75
        score, label = compute_fire_risk(temp_c=40.0, humidity=0.0, wind_kmh=30.0, precip_mm=0.0)
        assert 75 <= score < 80
        assert label == "Muy alto"

    def test_just_below_80_is_still_muy_alto(self):
        # temp=40→30pts, hum=0→30pts, wind=39.8→19.9pts = 79.9
        score, label = compute_fire_risk(temp_c=40.0, humidity=0.0, wind_kmh=39.8, precip_mm=0.0)
        assert score == 79.9
        assert label == "Muy alto"

    def test_extremo_starts_at_exactly_80(self):
        # temp=40→30pts, hum=0→30pts, wind=40→20pts = 80: con 40 °C, aire seco y 40 km/h ya es Extremo.
        score, label = compute_fire_risk(temp_c=40.0, humidity=0.0, wind_kmh=40.0, precip_mm=0.0)
        assert score == 80.0
        assert label == "Extremo"

    def test_a_score_that_rounds_to_80_is_extremo(self):
        # Puntaje crudo 79.99 → se muestra 80.0: el nivel tiene que ser el del número que ve la persona.
        score, label = compute_fire_risk(temp_c=39.99, humidity=0.0, wind_kmh=40.0, precip_mm=0.0)
        assert score == 80.0
        assert label == "Extremo"

    def test_a_score_that_rounds_to_75_is_muy_alto(self):
        # Mismo criterio en el corte de 75: crudo 74.96 (30 + 30 + 14.96) → se muestra 75.0, que ya es "Muy alto".
        score, label = compute_fire_risk(temp_c=40.0, humidity=0.0, wind_kmh=29.92, precip_mm=0.0)
        assert score == 75.0
        assert label == "Muy alto"

    def test_extremo_is_reachable_up_to_the_theoretical_maximum(self):
        # temp: min((temp-10)/30*30, 30) → máx 30; hum: máx 30 con hum=0; wind: máx 25 con wind>=50.
        # El máximo teórico es 30+30+25 = 85: el corte de Extremo tiene que quedar por debajo.
        score, label = compute_fire_risk(temp_c=100.0, humidity=0.0, wind_kmh=100.0, precip_mm=0.0)
        assert score == 85.0
        assert label == "Extremo"

    def test_rain_pulls_an_extremo_hour_down_to_alto(self):
        # 85 − 20 de la lluvia reciente = 65 → deja de ser Extremo.
        score, label = compute_fire_risk(temp_c=100.0, humidity=0.0, wind_kmh=100.0, precip_mm=5.0)
        assert score == 65.0
        assert label == "Alto"

    def test_precipitation_reduces_score(self):
        score_dry, _ = compute_fire_risk(temp_c=35.0, humidity=30.0, wind_kmh=20.0, precip_mm=0.0)
        score_wet, _ = compute_fire_risk(temp_c=35.0, humidity=30.0, wind_kmh=20.0, precip_mm=5.0)
        assert score_wet < score_dry

    def test_precipitation_below_2mm_no_reduction(self):
        score_dry, _ = compute_fire_risk(temp_c=35.0, humidity=30.0, wind_kmh=20.0, precip_mm=0.0)
        score_trace, _ = compute_fire_risk(temp_c=35.0, humidity=30.0, wind_kmh=20.0, precip_mm=1.5)
        assert score_dry == score_trace

    def test_score_cannot_be_negative(self):
        score, _ = compute_fire_risk(temp_c=0.0, humidity=100.0, wind_kmh=0.0, precip_mm=100.0)
        assert score >= 0.0

    def test_score_capped_at_100(self):
        score, _ = compute_fire_risk(temp_c=1000.0, humidity=0.0, wind_kmh=1000.0, precip_mm=0.0)
        assert score <= 100.0

    def test_returns_tuple_of_float_and_str(self):
        result = compute_fire_risk(temp_c=25.0, humidity=50.0, wind_kmh=15.0, precip_mm=0.0)
        assert isinstance(result, tuple)
        assert isinstance(result[0], float)
        assert isinstance(result[1], str)

    def test_score_rounded_to_one_decimal(self):
        score, _ = compute_fire_risk(temp_c=25.0, humidity=45.0, wind_kmh=15.0, precip_mm=0.0)
        assert score == round(score, 1)


# ---------------------------------------------------------------------------
# fire_entries_from_hourly
# ---------------------------------------------------------------------------

class TestFireEntriesFromHourly:

    def test_one_entry_per_hour_in_order_with_the_real_instant(self):
        entries = fire_entries_from_hourly(make_hourly(48))

        assert len(entries) == 48
        assert [e.hour_label for e in entries[:3]] == ["00:00", "01:00", "02:00"]
        assert (entries[0].date, entries[24].date) == ("2026-09-19", "2026-09-20")
        assert entries[18].timestamp_s == int(datetime(2026, 9, 19, 18, 0, tzinfo=AR).timestamp())

    def test_each_entry_takes_the_temperature_humidity_and_wind_of_its_hour(self):
        om = make_hourly(temps_c={14: 33.0}, humidities={14: 22.0}, wind_speeds={14: 41.0})

        entry = fire_entries_from_hourly(om)[14]

        assert (entry.temp_c, entry.humidity, entry.wind_kmh) == (33.0, 22.0, 41.0)

    def test_rain_is_the_total_of_the_three_hours_that_end_at_each_hour(self):
        # Como el `past3hprecip` de Windy, pero disponible en cada hora.
        entries = fire_entries_from_hourly(make_hourly(precipitations={16: 1.0, 17: 1.5, 18: 0.6}))

        assert entries[18].precip_mm == pytest.approx(3.1)
        assert entries[19].precip_mm == pytest.approx(2.1)
        assert entries[20].precip_mm == pytest.approx(0.6)
        assert entries[21].precip_mm == pytest.approx(0.0)

    def test_score_and_label_are_the_ones_of_compute_fire_risk(self):
        om = make_hourly(temps_c={14: 38.0}, humidities={14: 15.0}, wind_speeds={14: 30.0})

        entry = fire_entries_from_hourly(om)[14]

        assert (entry.fire_risk_score, entry.fire_risk_label) == compute_fire_risk(38.0, 15.0, 30.0, 0.0)
        assert entry.fire_risk_label in ("Alto", "Muy alto")

    def test_a_hot_dry_windy_hour_scores_higher_than_a_mild_humid_calm_one(self):
        om = make_hourly(
            temps_c={14: 38.0, 20: 12.0}, humidities={14: 15.0, 20: 85.0}, wind_speeds={14: 30.0, 20: 3.0},
        )
        entries = fire_entries_from_hourly(om)

        assert entries[14].fire_risk_score > entries[20].fire_risk_score
        assert entries[20].fire_risk_label == "Muy bajo"

    def test_a_soaking_rain_in_the_last_three_hours_lowers_the_risk(self):
        hot_dry = {"temps_c": {14: 35.0}, "humidities": {14: 30.0}, "wind_speeds": {14: 20.0}}
        dry = fire_entries_from_hourly(make_hourly(**hot_dry))[14]
        wet = fire_entries_from_hourly(make_hourly(**hot_dry, precipitations={13: 1.5, 14: 1.5}))[14]

        assert wet.precip_mm == pytest.approx(3.0)
        assert wet.fire_risk_score < dry.fire_risk_score

    def test_a_variable_the_series_does_not_have_is_unknown_and_still_scores(self):
        om = dataclasses.replace(make_hourly(), humidities=[])

        entry = fire_entries_from_hourly(om)[14]

        assert entry.humidity is None
        assert (entry.fire_risk_score, entry.fire_risk_label) == compute_fire_risk(20.0, None, 10.0, 0.0)

    def test_an_hour_without_any_data_is_the_lowest_risk_not_a_crash(self):
        om = dataclasses.replace(
            make_hourly(), temps_c=[], humidities=[], wind_speeds=[], precipitations=[],
        )

        entry = fire_entries_from_hourly(om)[0]

        assert (entry.temp_c, entry.humidity, entry.wind_kmh, entry.precip_mm) == (None, None, None, None)
        assert (entry.fire_risk_score, entry.fire_risk_label) == (0.0, "Muy bajo")

    def test_an_empty_series_has_no_entries(self):
        assert fire_entries_from_hourly(make_hourly(0)) == []


# ---------------------------------------------------------------------------
# closest_to_now
# ---------------------------------------------------------------------------

def _entry_at(offset_s: int, temp_c: float) -> FireDangerEntry:
    """Entry sintético a `offset_s` segundos de "ahora" (negativo = pasado)."""
    return FireDangerEntry(
        date="2026-09-02",
        hour_label="00:00",
        fire_risk_score=30.0,
        fire_risk_label="Bajo",
        temp_c=temp_c,
        humidity=50.0,
        wind_kmh=10.0,
        precip_mm=0.0,
        timestamp_s=int(time.time()) + offset_s,
    )


class TestClosestToNow:
    """
    La serie no está garantizada a empezar en "ahora": la de Open-Meteo arranca a las 00:00 de hoy, y
    tomar `entries[0]` a ciegas como "condiciones actuales" mostraba la temperatura de la madrugada al
    mediodía (el bug reportado en vivo con la serie de Windy).
    """

    def test_picks_index_zero_when_already_closest(self):
        entries = [_entry_at(0, temp_c=22.0), _entry_at(3600, temp_c=24.0)]
        assert closest_to_now(entries) is entries[0]

    def test_picks_a_later_index_when_array_starts_in_the_past(self):
        # índice 0 = hace 6h (madrugada, 10°C) — exactamente el bug reportado:
        # la app mostraba 10°C con la real actual en 22°C.
        entries = [
            _entry_at(-6 * 3600, temp_c=10.0),
            _entry_at(-3 * 3600, temp_c=15.0),
            _entry_at(0, temp_c=22.0),
            _entry_at(3 * 3600, temp_c=25.0),
        ]
        closest = closest_to_now(entries)
        assert closest.temp_c == 22.0
        assert closest is entries[2]

    def test_picks_nearest_future_slot_when_nothing_matches_exactly(self):
        # Sin timestamp exacto a "ahora" — el más cercano es +1h, no -2h.
        entries = [_entry_at(-2 * 3600, temp_c=12.0), _entry_at(3600, temp_c=20.0)]
        assert closest_to_now(entries).temp_c == 20.0

    def test_single_entry_returns_it(self):
        entries = [_entry_at(-5 * 3600, temp_c=8.0)]
        assert closest_to_now(entries) is entries[0]


# ---------------------------------------------------------------------------
# get_fire_danger
# ---------------------------------------------------------------------------

class TestGetFireDanger:

    @pytest.mark.asyncio
    async def test_builds_the_entries_from_seven_days_of_open_meteo(self):
        with patch(OPEN_METEO, new_callable=AsyncMock, return_value=make_hourly(168)) as open_meteo:
            entries = await get_fire_danger(-34.6, -58.4)

        open_meteo.assert_awaited_once_with(-34.6, -58.4, days=7)
        assert len(entries) == 168
        assert all(isinstance(e, FireDangerEntry) for e in entries)

    @pytest.mark.asyncio
    async def test_without_open_meteo_there_are_no_entries(self):
        with patch(OPEN_METEO, new_callable=AsyncMock, return_value=None):
            assert await get_fire_danger(-34.6, -58.4) == []
