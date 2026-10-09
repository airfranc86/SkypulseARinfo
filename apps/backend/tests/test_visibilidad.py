"""Visibility rules in one place (`app.services.visibilidad`): parsing of AWC `visib`, the open-ended
"6+" / "P6SM" token and the fog scale. Pure tests: no network, no clock.

The values pinned here are the ones the system returned before the rules were gathered in one module
(see also the 1a characterization tests).
"""
from __future__ import annotations

import pytest

from app.services.taf_decoded import normalize_taf
from app.services.visibilidad import (
    MAX_VISIBILITY_M,
    SM_TO_M,
    awc_visibility_m,
    classify_visibility,
    is_open_ended,
    parse_visibility_sm,
)

NAN = float("nan")
INF = float("inf")


def test_constants() -> None:
    assert MAX_VISIBILITY_M == 10_000.0
    assert SM_TO_M == 1609.344


# ---------------------------------------------------------------- parse_visibility_sm (statute miles)


@pytest.mark.parametrize(
    ("raw", "miles"),
    [
        ("6+", 6.0),
        ("P6SM", 6.0),
        ("P6", 6.0),
        ("10+", 10.0),
        ("6SM", 6.0),
        ("4.35", 4.35),
        (4.35, 4.35),
        (6, 6.0),
        (0.5, 0.5),
        ("1/2SM", 0.5),
        ("3/4", 0.75),
        ("1 1/2", 1.5),
        ("1 1/2SM", 1.5),
        (" 3 ", 3.0),
    ],
)
def test_parse_visibility_sm_reads_every_format_awc_sends(raw, miles) -> None:
    assert parse_visibility_sm(raw) == pytest.approx(miles)


@pytest.mark.parametrize("raw", [None, "", "  ", "abc", "1/0", "1/x", "P", NAN, INF, -INF, "nan", "inf"])
def test_parse_visibility_sm_gives_none_for_unusable_values(raw) -> None:
    assert parse_visibility_sm(raw) is None


# ---------------------------------------------------------------- is_open_ended ("6 or more")


@pytest.mark.parametrize("raw", ["6+", "P6SM", "P6", "p6sm", " 6+ ", "10+"])
def test_open_ended_tokens(raw) -> None:
    assert is_open_ended(raw) is True


@pytest.mark.parametrize("raw", [None, "", "6", "6SM", "4.35", "1 1/2", 6, 6.0, "abc"])
def test_closed_values_are_not_open_ended(raw) -> None:
    assert is_open_ended(raw) is False


# ---------------------------------------------------------------- awc_visibility_m (meters, capped)


@pytest.mark.parametrize("raw", ["6+", "P6SM", "P6", "10+"])
def test_open_ended_visibility_is_the_10_km_cap_not_six_miles(raw) -> None:
    assert awc_visibility_m(raw) == 10_000.0
    assert awc_visibility_m(raw) != pytest.approx(6 * SM_TO_M)


@pytest.mark.parametrize(
    ("raw", "meters"),
    [
        ("4.35", 7000.6464),
        (4.35, 7000.6464),
        ("1 1/2", 2414.016),
        ("1/2SM", 804.672),
        ("3/4", 1207.008),
        (6, 9656.064),
        ("6", 9656.064),
        (0, 0.0),
        ("0", 0.0),
        (7, 10_000.0),  # 7 SM = 11 265 m: topped at 10 km
        ("25", 10_000.0),
    ],
)
def test_closed_visibility_is_miles_to_meters_capped_at_10_km(raw, meters) -> None:
    assert awc_visibility_m(raw) == pytest.approx(meters)


@pytest.mark.parametrize("raw", [None, "", "abc", -1, "-1", NAN, INF, "nan", "inf"])
def test_awc_visibility_m_gives_none_for_unusable_values(raw) -> None:
    assert awc_visibility_m(raw) is None


# ---------------------------------------------------------------- classify_visibility (fog scale)


@pytest.mark.parametrize(
    ("meters", "level", "label", "color"),
    [
        (None, 0, "Sin datos", "#90aabb"),
        (0.0, 3, "Niebla", "#e03535"),
        (999.0, 3, "Niebla", "#e03535"),
        (1_000.0, 2, "Neblina o bruma", "#f0a020"),
        (4_999.0, 2, "Neblina o bruma", "#f0a020"),
        (5_000.0, 1, "Buena", "#5aaad8"),
        (9_999.0, 1, "Buena", "#5aaad8"),
        (10_000.0, 0, "Despejada", "#3ecf7a"),
        (50_000.0, 0, "Despejada", "#3ecf7a"),
    ],
)
def test_classify_visibility_boundaries(meters, level, label, color) -> None:
    assert classify_visibility(meters) == (level, label, color)


def test_open_ended_visibility_classifies_as_clear() -> None:
    assert classify_visibility(awc_visibility_m("6+"))[1] == "Despejada"
    assert classify_visibility(awc_visibility_m(6))[1] == "Buena"  # 6 SM written as a number is 9 656 m


# ---------------------------------------------------------------- the TAF normalizer shares the rules


def _entry(visib: object) -> dict:
    return {
        "icaoId": "TEST",
        "fcsts": [
            {
                "timeFrom": 1791309600,
                "timeTo": 1791331200,
                "fcstChange": None,
                "visib": visib,
                "clouds": [],
                "temp": [],
            }
        ],
    }


@pytest.mark.parametrize("bad", [NAN, INF, -INF, "nan"])
def test_taf_with_a_non_finite_visibility_no_longer_raises(bad) -> None:
    taf = normalize_taf(_entry(bad))
    assert taf is not None
    period = taf.periods[0]
    assert period.visibility_m is None
    assert period.visibility_over is False


def test_taf_open_ended_and_closed_visibility_values_are_unchanged() -> None:
    open_period = normalize_taf(_entry("P6SM")).periods[0]
    assert (open_period.visibility_m, open_period.visibility_over) == (10_000, True)
    closed_period = normalize_taf(_entry(4.35)).periods[0]
    assert (closed_period.visibility_m, closed_period.visibility_over) == (7000, False)
