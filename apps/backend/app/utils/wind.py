"""Utilidades de viento: escala Beaufort, tier de intensidad, rotación."""
from __future__ import annotations

_BEAUFORT_THRESHOLDS: list[tuple[float, int]] = [
    (1.0,   1),
    (6.0,   2),
    (12.0,  3),
    (20.0,  4),
    (29.0,  5),
    (39.0,  6),
    (50.0,  7),
    (62.0,  8),
    (75.0,  9),
    (89.0,  10),
    (103.0, 11),
    (118.0, 12),
]


def beaufort_from_kmh(speed: float | None) -> int:
    if speed is None:
        return 0
    for threshold, level in _BEAUFORT_THRESHOLDS:
        if speed < threshold:
            return level - 1
    return 12


def wind_intensity_tier(speed: float | None) -> str | None:
    if speed is None:
        return None
    if speed < 35.0:
        return "leve"
    if speed < 60.0:
        return "moderada"
    return "intensa"


def wind_icon_code(speed: float | None) -> str | None:
    tier = wind_intensity_tier(speed)
    if tier in (None, "leve"):
        return None
    return f"wind-beaufort-{beaufort_from_kmh(speed)}"


def detect_wind_shift(
    dirs_deg: list[float | None],
    threshold_deg: float = 90.0,
) -> list[bool]:
    result: list[bool] = []
    for i, current in enumerate(dirs_deg):
        if i == 0:
            result.append(False)
            continue
        prev = dirs_deg[i - 1]
        if prev is None or current is None:
            result.append(False)
            continue
        diff = abs(current - prev) % 360.0
        angular_diff = min(diff, 360.0 - diff)
        result.append(angular_diff >= threshold_deg)
    return result
