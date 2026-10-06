"""Geometry of the temperature curve of the standard plate (pure numbers, no browser)."""

from __future__ import annotations

import re

import pytest

from placa_curva import MIN_SPAN_C, temperature_curve, x_for_hour
from tipos import TempPoint

WIDTH, HEIGHT, PAD_X, PAD_Y = 900.0, 300.0, 30.0, 40.0
DAY = (12.0, 11.0, 10.0, 14.0, 21.0, 25.0, 23.0, 18.0, 15.0)  # 00, 03, ... 24 h


def curve_of(temps, hours=None):
    hours = hours if hours is not None else range(0, 25, 3)
    points = [TempPoint(hour=h, temp_c=t) for h, t in zip(hours, temps, strict=True)]
    return temperature_curve(points, width=WIDTH, height=HEIGHT, pad_x=PAD_X, pad_y=PAD_Y)


def numbers(path: str) -> list[float]:
    return [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", path)]


def test_hours_span_the_whole_width() -> None:
    assert x_for_hour(0, WIDTH, PAD_X) == PAD_X
    assert x_for_hour(24, WIDTH, PAD_X) == WIDTH - PAD_X
    assert x_for_hour(12, WIDTH, PAD_X) == pytest.approx(WIDTH / 2)


def test_one_point_per_temperature_and_the_extremes_touch_the_padding() -> None:
    curve = curve_of(DAY)
    assert curve is not None
    assert len(curve.points) == 9
    ys = [y for _, y in curve.points]
    assert min(ys) == pytest.approx(PAD_Y)  # 25 degrees at the top
    assert max(ys) == pytest.approx(HEIGHT - PAD_Y)  # 10 degrees at the bottom


def test_hottest_and_coolest_points_are_the_first_extremes() -> None:
    curve = curve_of(DAY)
    assert curve is not None
    assert curve.hottest == curve.points[5]
    assert curve.coolest == curve.points[2]
    assert (curve.hottest_hour, curve.coolest_hour) == (15, 6)


def test_small_ranges_are_not_exaggerated() -> None:
    curve = curve_of((15.0, 15.5, 16.0, 16.5, 17.0, 16.5, 16.0, 15.5, 15.0))
    assert curve is not None
    ys = [y for _, y in curve.points]
    plot = HEIGHT - 2 * PAD_Y
    assert max(ys) - min(ys) == pytest.approx(plot * 2.0 / MIN_SPAN_C)


def test_a_flat_day_draws_a_line_in_the_middle() -> None:
    curve = curve_of((20.0,) * 9)
    assert curve is not None
    assert {round(y, 6) for _, y in curve.points} == {round(HEIGHT / 2, 6)}


def test_path_is_a_smooth_line_that_never_overshoots_the_plot() -> None:
    curve = curve_of(DAY)
    assert curve is not None
    assert curve.line.startswith("M")
    assert curve.line.count("C") == 8
    ys = numbers(curve.line)[1::2]
    assert min(ys) >= PAD_Y - 1e-6
    assert max(ys) <= HEIGHT - PAD_Y + 1e-6


def test_area_closes_the_line_down_to_the_bottom() -> None:
    curve = curve_of(DAY)
    assert curve is not None
    assert curve.area.startswith(curve.line)
    assert curve.area.endswith("Z")


def test_missing_hours_are_simply_skipped() -> None:
    curve = curve_of((12.0, 25.0, 15.0), hours=(0, 15, 24))
    assert curve is not None
    assert [round(x, 3) for x, _ in curve.points] == [
        round(x_for_hour(h, WIDTH, PAD_X), 3) for h in (0, 15, 24)
    ]


@pytest.mark.parametrize("temps", [(), (18.0,)])
def test_fewer_than_two_points_draw_no_curve(temps) -> None:
    assert curve_of(temps, hours=range(0, 3 * len(temps), 3)) is None


def test_non_finite_values_are_ignored() -> None:
    curve = curve_of((12.0, float("nan"), 14.0), hours=(0, 3, 6))
    assert curve is not None
    assert len(curve.points) == 2
