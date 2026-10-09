"""Visibility rules shared by every source (Open-Meteo, AWC METAR and TAF).

Pure module: standard library only, no network, no clock. It gathers what used to live in three
places (`openmeteo`, `metar`, `taf_decoded`):

- the 10 km cap and the statute-mile conversion,
- the parsing of the AWC `visib` field,
- the open-ended "6 or more" token ("6+" / "P6SM"), detected in ONE place,
- the fog scale (official METAR/SMN, 4 levels).
"""
from __future__ import annotations

import math

SM_TO_M = 1609.344  # statute miles -> meters
# Atmospheric visibility maxes out at 10 km for practical purposes: values beyond that do not
# differentiate "clear" conditions (the fog scale separates "Despejada" from "Buena" at 10 km).
MAX_VISIBILITY_M = 10_000.0


def parse_visibility_sm(raw: object) -> float | None:
    """AWC `visib` field -> statute miles, or None when it is not usable.

    Formats: numeric (6, 3.0, 0.5) and strings ("6SM", "P6SM", "1/2SM", "1 1/2SM", "6+", "3/4").
    NaN and infinity give None (a number is not a visibility if it is not finite).
    """
    if raw is None:
        return None
    try:
        direct = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        pass
    else:
        return direct if math.isfinite(direct) else None
    text = str(raw).strip().upper().replace("SM", "").replace("+", "").strip()
    if text.startswith("P"):
        text = text[1:].strip()
    # Mixed number: "1 1/2" -> 1.5
    total = 0.0
    for part in text.split():
        try:
            if "/" in part:
                numerator, denominator = part.split("/", 1)
                total += float(numerator) / float(denominator)
            else:
                total += float(part)
        except (ValueError, ZeroDivisionError):
            return None
    return total if math.isfinite(total) and total > 0 else None


def is_open_ended(raw: object) -> bool:
    """True for "6 or more" visibility ("6+", "P6SM"): CAVOK and good visibility in AWC."""
    text = str(raw).strip().upper() if raw is not None else ""
    return "+" in text or text.startswith("P")


def awc_visibility_m(raw: object) -> float | None:
    """AWC `visib` field -> meters capped at `MAX_VISIBILITY_M`, or None when it is not usable.

    The open-ended token is worth the 10 km cap, not 6 SM = 9 656 m. Anything else is parsed as
    statute miles. A negative number is not usable.
    """
    miles = parse_visibility_sm(raw)
    if miles is None:
        return None
    if is_open_ended(raw):
        return MAX_VISIBILITY_M
    if miles < 0:
        return None
    return min(miles * SM_TO_M, MAX_VISIBILITY_M)


def classify_visibility(v: float | None) -> tuple[int, str, str]:
    """Returns (level, label, color) from visibility in meters.

    Official METAR/SMN scale (4 levels, no separate dry-haze category):
      Niebla (FG)          < 1 km
      Neblina o bruma (BR) 1 km to < 5 km  (in Argentina neblina == bruma)
      Buena                5 km to < 10 km
      Despejada            >= 10 km
    """
    if v is None:
        return 0, "Sin datos", "#90aabb"
    if v >= 10_000:
        return 0, "Despejada", "#3ecf7a"
    if v >= 5_000:
        return 1, "Buena", "#5aaad8"
    if v >= 1_000:
        return 2, "Neblina o bruma", "#f0a020"
    return 3, "Niebla", "#e03535"
