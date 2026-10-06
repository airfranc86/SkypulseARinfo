"""Geometry of the temperature curve of the standard plate (pure: numbers in, SVG paths out).

The line is a monotone cubic (Fritsch-Carlson): smooth, and it never overshoots the data, so the
drawn peak is the real peak and the curve never leaves the plot.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from tipos import TempPoint

DAY_HOURS = 24
# A day that only moves 2 degrees must not look like a heat wave: the vertical scale always spans
# at least this many degrees.
MIN_SPAN_C = 6.0

Point = tuple[float, float]


@dataclass(frozen=True)
class CurveGeometry:
    points: tuple[Point, ...]
    line: str  # SVG path of the curve
    area: str  # the curve closed down to the bottom of the plot (for the soft fill)
    hottest: Point
    coolest: Point
    hottest_hour: int
    coolest_hour: int


def x_for_hour(hour: float, width: float, pad_x: float) -> float:
    return pad_x + hour / DAY_HOURS * (width - 2 * pad_x)


def _scale(temps: Sequence[float]) -> tuple[float, float]:
    """(low, high) of the vertical axis, widened around the middle to at least MIN_SPAN_C."""
    low, high = min(temps), max(temps)
    if high - low < MIN_SPAN_C:
        middle = (low + high) / 2
        return middle - MIN_SPAN_C / 2, middle + MIN_SPAN_C / 2
    return low, high


def _tangents(points: Sequence[Point]) -> list[float]:
    """Fritsch-Carlson tangents: zero at local extremes, limited so the curve stays monotone."""
    slopes = [
        (y1 - y0) / (x1 - x0) for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False)
    ]
    inner = [0.0 if a * b <= 0 else (a + b) / 2 for a, b in zip(slopes, slopes[1:], strict=False)]
    tangents = [slopes[0], *inner, slopes[-1]]
    for index, slope in enumerate(slopes):
        if slope == 0:
            tangents[index] = tangents[index + 1] = 0.0
            continue
        alpha, beta = tangents[index] / slope, tangents[index + 1] / slope
        norm = math.hypot(alpha, beta)
        if norm > 3:
            tangents[index] = 3 * alpha / norm * slope
            tangents[index + 1] = 3 * beta / norm * slope
    return tangents


def _fmt(value: float) -> str:
    return f"{value:.1f}"


def _smooth_path(points: Sequence[Point]) -> str:
    tangents = _tangents(points)
    parts = [f"M{_fmt(points[0][0])},{_fmt(points[0][1])}"]
    for index, ((x0, y0), (x1, y1)) in enumerate(zip(points, points[1:], strict=False)):
        third = (x1 - x0) / 3
        c1 = (x0 + third, y0 + tangents[index] * third)
        c2 = (x1 - third, y1 - tangents[index + 1] * third)
        parts.append(
            f"C{_fmt(c1[0])},{_fmt(c1[1])} {_fmt(c2[0])},{_fmt(c2[1])} {_fmt(x1)},{_fmt(y1)}"
        )
    return " ".join(parts)


def temperature_curve(
    points: Sequence[TempPoint],
    *,
    width: float,
    height: float,
    pad_x: float,
    pad_y: float,
) -> CurveGeometry | None:
    """Curve of the day inside a ``width`` x ``height`` plot; None with fewer than two usable points."""
    valid = sorted(
        (p for p in points if math.isfinite(p.temp_c) and 0 <= p.hour <= DAY_HOURS),
        key=lambda p: p.hour,
    )
    if len(valid) < 2:
        return None
    low, high = _scale([p.temp_c for p in valid])
    plot = height - 2 * pad_y

    def y_for(temp: float) -> float:
        return pad_y + (high - temp) / (high - low) * plot

    xy = tuple((x_for_hour(p.hour, width, pad_x), y_for(p.temp_c)) for p in valid)
    hot = max(range(len(valid)), key=lambda i: (valid[i].temp_c, -i))
    cool = min(range(len(valid)), key=lambda i: (valid[i].temp_c, i))
    line = _smooth_path(xy)
    bottom = _fmt(height - pad_y)
    area = f"{line} L{_fmt(xy[-1][0])},{bottom} L{_fmt(xy[0][0])},{bottom} Z"
    return CurveGeometry(
        points=xy,
        line=line,
        area=area,
        hottest=xy[hot],
        coolest=xy[cool],
        hottest_hour=valid[hot].hour,
        coolest_hour=valid[cool].hour,
    )
