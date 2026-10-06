"""TAF decodificado por períodos a partir del JSON de AWC (FRA-365, T2).

Los casos principales usan el TAF real de SACO (tests/fixtures/awc_taf/SACO.json); los bordes de
herencia y de categoría de vuelo usan entradas mínimas armadas a mano.
"""
from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.schemas.taf import TafCloud
from app.services.taf_decoded import ceiling_ft, flight_category, normalize_taf

FIXTURE = Path(__file__).parent / "fixtures" / "awc_taf" / "SACO.json"


@pytest.fixture
def saco() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))[0]


def _utc(day: int, hour: int) -> datetime:
    return datetime(2026, 10, day, hour, 0, tzinfo=UTC)


# ---------------------------------------------------------------- TAF real de SACO


def test_header_of_the_real_saco_taf(saco) -> None:
    taf = normalize_taf(saco)
    assert taf is not None
    assert taf.icao == "SACO"
    assert taf.name == "Cordoba/Taravella Intl"
    assert taf.issued_at == _utc(6, 17)
    assert taf.valid_from == _utc(6, 18)
    assert taf.valid_to == _utc(7, 18)
    assert taf.raw.startswith("TAF SACO 061700Z 0618/0718")
    assert taf.source == "aviationweather.gov (NOAA)"
    assert len(taf.periods) == 5


def test_change_groups_probability_and_becoming_time(saco) -> None:
    taf = normalize_taf(saco)
    assert [p.change for p in taf.periods] == ["initial", "becoming", "becoming", "tempo", "becoming"]
    assert [p.probability for p in taf.periods] == [None, None, None, 40, None]
    assert taf.periods[1].becoming_by == _utc(7, 2)
    assert taf.periods[0].becoming_by is None
    assert (taf.periods[1].valid_from, taf.periods[1].valid_to) == (_utc(6, 23), _utc(7, 3))


def test_initial_period_wind_visibility_and_clouds(saco) -> None:
    first = normalize_taf(saco).periods[0]
    assert (first.wind.direction_deg, first.wind.speed_kt, first.wind.gust_kt) == (50, 15, None)
    assert first.wind.variable is False
    assert first.visibility_m == 10_000 and first.visibility_over is True
    assert [(c.cover, c.base_ft, c.kind) for c in first.clouds] == [("SCT", 3500, None)]
    assert first.weather == []


def test_tcu_is_reported_as_the_kind_of_the_cloud(saco) -> None:
    second = normalize_taf(saco).periods[1]
    assert TafCloud(cover="FEW", base_ft=4000, kind="TCU") in second.clouds


def test_numeric_visibility_in_miles_becomes_meters_rounded_to_100(saco) -> None:
    third = normalize_taf(saco).periods[2]
    assert third.visibility_m == 7000  # 4.35 SM = 7000.9 m
    assert third.visibility_over is False


def test_flight_category_of_each_period_of_the_real_taf(saco) -> None:
    taf = normalize_taf(saco)
    # VFR, VFR (techo 3500), MVFR (7000 m y techo 3000), MVFR (TEMPO: techo 2000), VFR
    assert [p.flight_category for p in taf.periods] == ["VFR", "VFR", "MVFR", "MVFR", "VFR"]


def test_temperatures_use_the_valid_time_given_by_awc(saco) -> None:
    taf = normalize_taf(saco)
    assert [(t.kind, t.celsius, t.valid_at) for t in taf.temperatures] == [
        ("max", 28.0, _utc(6, 19)),
        ("min", 14.0, _utc(7, 10)),
    ]


def test_the_result_serializes_to_json_with_utc_dates(saco) -> None:
    data = json.loads(normalize_taf(saco).model_dump_json())
    assert data["issued_at"] == "2026-10-06T17:00:00Z"
    assert data["periods"][0]["valid_from"] == "2026-10-06T18:00:00Z"


# ---------------------------------------------------------------- entradas inválidas


@pytest.mark.parametrize("entry", [None, {}, {"fcsts": []}, {"fcsts": None}, "TAF", []])
def test_entries_without_periods_are_none(entry) -> None:
    assert normalize_taf(entry) is None


def test_periods_without_a_usable_time_window_are_dropped(saco) -> None:
    broken = copy.deepcopy(saco)
    broken["fcsts"][1]["timeFrom"] = None
    broken["fcsts"][2]["timeTo"] = "no es un número"
    taf = normalize_taf(broken)
    assert len(taf.periods) == 3


def test_all_periods_unusable_is_none(saco) -> None:
    broken = copy.deepcopy(saco)
    for period in broken["fcsts"]:
        period["timeFrom"] = None
    assert normalize_taf(broken) is None


# ---------------------------------------------------------------- herencia


def _entry(*fcsts: dict) -> dict:
    return {"icaoId": "TEST", "validTimeFrom": 1791309600, "validTimeTo": 1791396000, "fcsts": list(fcsts)}


def _period(start: int, end: int, change: str | None = None, **fields) -> dict:
    base = {
        "timeFrom": 1791309600 + start * 3600,
        "timeTo": 1791309600 + end * 3600,
        "timeBec": None,
        "fcstChange": change,
        "probability": None,
        "wdir": None,
        "wspd": None,
        "wgst": None,
        "visib": None,
        "wxString": None,
        "clouds": [],
        "temp": [],
    }
    base.update(fields)
    return base


def test_a_group_that_states_nothing_inherits_wind_visibility_and_clouds() -> None:
    taf = normalize_taf(
        _entry(
            _period(0, 6, wdir=90, wspd=10, visib="6+", clouds=[{"cover": "SCT", "base": 4000, "type": None}]),
            _period(6, 12, "BECMG"),
        )
    )
    second = taf.periods[1]
    assert second.wind.direction_deg == 90 and second.wind.speed_kt == 10
    assert second.visibility_m == 10_000
    assert [c.cover for c in second.clouds] == ["SCT"]
    assert sorted(second.inherited) == ["clouds", "visibility", "wind"]
    assert taf.periods[0].inherited == []


def test_a_group_only_replaces_what_it_states() -> None:
    taf = normalize_taf(
        _entry(
            _period(0, 6, wdir=90, wspd=10, visib="6+", clouds=[{"cover": "SCT", "base": 4000, "type": None}]),
            _period(6, 12, "BECMG", visib=2.0),
        )
    )
    second = taf.periods[1]
    assert second.visibility_m == 3200 and second.visibility_over is False
    assert second.wind.speed_kt == 10
    assert second.inherited == ["wind", "clouds"]


def test_tempo_does_not_become_the_new_prevailing_but_becmg_does() -> None:
    taf = normalize_taf(
        _entry(
            _period(0, 6, wdir=90, wspd=10, visib="6+", clouds=[{"cover": "SCT", "base": 4000, "type": None}]),
            _period(6, 9, "TEMPO", visib=0.5, wdir=180, wspd=25),
            _period(9, 12, "BECMG", visib=4.0),
            _period(12, 15, "BECMG"),
        )
    )
    after_becmg = taf.periods[2]
    assert after_becmg.wind.direction_deg == 90 and after_becmg.wind.speed_kt == 10  # no hereda el TEMPO
    assert after_becmg.visibility_m == 6400
    last = taf.periods[3]
    assert last.visibility_m == 6400  # hereda del BECMG, no de la tormenta del TEMPO
    assert last.wind.speed_kt == 10


def test_the_first_group_has_nothing_to_inherit() -> None:
    taf = normalize_taf(_entry(_period(0, 6, "BECMG")))
    only = taf.periods[0]
    assert only.wind is None and only.visibility_m is None and only.clouds == []
    assert only.flight_category is None


# ---------------------------------------------------------------- viento


def test_variable_wind_has_no_direction() -> None:
    taf = normalize_taf(_entry(_period(0, 6, wdir="VRB", wspd=4)))
    wind = taf.periods[0].wind
    assert wind.variable is True and wind.direction_deg is None and wind.speed_kt == 4


def test_gusts_are_reported() -> None:
    taf = normalize_taf(_entry(_period(0, 6, wdir=290, wspd=15, wgst=28)))
    assert taf.periods[0].wind.gust_kt == 28


def test_weather_codes_are_kept_as_written() -> None:
    taf = normalize_taf(_entry(_period(0, 6, wxString="+TSRA BR")))
    assert taf.periods[0].weather == ["+TSRA", "BR"]


# ---------------------------------------------------------------- categoría de vuelo (FAA)


@pytest.mark.parametrize(
    ("vis_sm", "ceiling", "expected"),
    [
        (10.0, None, "VFR"),
        (10.0, 3500, "VFR"),
        (5.01, None, "VFR"),
        (5.0, None, "MVFR"),
        (3.0, None, "MVFR"),
        (2.99, None, "IFR"),
        (1.0, None, "IFR"),
        (0.99, None, "LIFR"),
        (10.0, 3000, "MVFR"),
        (10.0, 1000, "MVFR"),
        (10.0, 999, "IFR"),
        (10.0, 500, "IFR"),
        (10.0, 499, "LIFR"),
        (0.5, 5000, "LIFR"),
        (None, 3000, "MVFR"),
        (4.0, None, "MVFR"),
        (None, None, None),
    ],
)
def test_flight_category_thresholds(vis_sm, ceiling, expected) -> None:
    assert flight_category(vis_sm, ceiling) == expected


def test_ceiling_is_the_lowest_broken_overcast_or_vertical_visibility_layer() -> None:
    clouds = [
        TafCloud(cover="FEW", base_ft=800, kind=None),
        TafCloud(cover="SCT", base_ft=1200, kind=None),
        TafCloud(cover="BKN", base_ft=3000, kind=None),
        TafCloud(cover="OVC", base_ft=2000, kind=None),
    ]
    assert ceiling_ft(clouds) == 2000
    assert ceiling_ft([TafCloud(cover="VV", base_ft=300, kind=None)]) == 300
    assert ceiling_ft([TafCloud(cover="FEW", base_ft=800, kind="CB")]) is None
    assert ceiling_ft([]) is None


# ---------------------------------------------------------------- más TAF reales (2026-10-06)


def _real(icao: str):
    data = json.loads((FIXTURE.parent / f"{icao}.json").read_text(encoding="utf-8"))
    return normalize_taf(data[0])


def test_sari_prob30_cavok_and_fog_group() -> None:
    # PROB30 0622/0702 CAVOK BECMG 0702/0704 0500 FG OVC005
    taf = _real("SARI")
    assert [p.change for p in taf.periods] == ["initial", "prob", "becoming"]
    prob = taf.periods[1]
    assert prob.probability == 30
    assert prob.visibility_over is True and [c.cover for c in prob.clouds] == ["NSC"]
    assert prob.weather == ["NSW"]
    fog = taf.periods[2]
    assert fog.visibility_m == 500 and fog.weather == ["FG"]
    assert [(c.cover, c.base_ft) for c in fog.clouds] == [("OVC", 500)]
    assert fog.flight_category == "LIFR"
    assert [p.flight_category for p in taf.periods] == ["MVFR", "VFR", "LIFR"]


def test_sasa_variable_wind_and_tempo_prob40_with_mist() -> None:
    # BECMG 0700/0703 VRB03KT 7000 BKN025 PROB40 TEMPO 0709/0712 2000 BR OVC010
    taf = _real("SASA")
    becoming = taf.periods[2]
    assert becoming.wind.variable is True and becoming.wind.direction_deg is None
    assert becoming.wind.speed_kt == 3
    tempo = taf.periods[3]
    assert (tempo.change, tempo.probability, tempo.weather) == ("tempo", 40, ["BR"])
    assert tempo.wind.variable is True and "wind" in tempo.inherited
    assert [p.flight_category for p in taf.periods] == ["VFR", "VFR", "MVFR", "IFR", "VFR"]


def test_saar_empty_visibility_and_empty_clouds_mean_no_change() -> None:
    # TEMPO 0618/0623 08010G20KT (sin visibilidad ni nubes) y TSRA con CB más adelante
    taf = _real("SAAR")
    gusty = taf.periods[1]
    assert gusty.wind.gust_kt == 20
    assert gusty.inherited == ["visibility", "clouds"]
    assert gusty.visibility_over is True and gusty.flight_category == "VFR"
    storm = taf.periods[2]
    assert storm.weather == ["TSRA"]
    assert TafCloud(cover="FEW", base_ft=4000, kind="CB") in storm.clouds
    assert [p.flight_category for p in taf.periods] == ["VFR", "VFR", "IFR", "IFR"]
