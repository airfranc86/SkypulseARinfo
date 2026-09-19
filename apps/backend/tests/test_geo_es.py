"""Cardinales de 16 puntos en español (los que espera el puntaje de tender ropa)."""
from __future__ import annotations

import pytest

from app.services.calculators import _WIND_DIR_MULTIPLIER
from app.utils.geo import degrees_to_cardinal_es


@pytest.mark.parametrize(
    "deg, expected",
    [
        (0, "N"), (22.5, "NNE"), (45, "NE"), (67.5, "ENE"),
        (90, "E"), (112.5, "ESE"), (135, "SE"), (157.5, "SSE"),
        (180, "S"), (202.5, "SSO"), (225, "SO"), (247.5, "OSO"),
        (270, "O"), (292.5, "ONO"), (315, "NO"), (337.5, "NNO"),
    ],
)
def test_the_sixteen_points_use_spanish_letters(deg: float, expected: str):
    assert degrees_to_cardinal_es(deg) == expected


def test_west_is_o_not_w():
    assert degrees_to_cardinal_es(270) == "O"
    assert degrees_to_cardinal_es(292.5) == "ONO"


@pytest.mark.parametrize("deg, expected", [(11, "N"), (12, "NNE"), (348, "NNO"), (349, "N"), (359.9, "N")])
def test_the_edge_between_two_points_rounds_to_the_nearest(deg: float, expected: str):
    assert degrees_to_cardinal_es(deg) == expected


@pytest.mark.parametrize("deg, expected", [(360, "N"), (450, "E"), (-90, "O")])
def test_degrees_outside_0_360_wrap_around(deg: float, expected: str):
    assert degrees_to_cardinal_es(deg) == expected


def test_the_labels_match_the_ones_the_laundry_score_understands():
    # Con las letras en inglés (SW, W, NW) el multiplicador por dirección nunca se aplicaba.
    produced = {degrees_to_cardinal_es(step * 22.5) for step in range(16)}
    assert produced - set(_WIND_DIR_MULTIPLIER) <= {"SO"}
    assert {"S", "N", "O", "NO"} <= set(_WIND_DIR_MULTIPLIER)
