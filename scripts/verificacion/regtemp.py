"""Parser for the SMN ``regtemp`` daily temperature file (fixed width, latin-1).

Format: two header lines (column names, then dashes) and one row per station and day::

    FECHA    TMAX  TMIN  NOMBRE
    -------- ----- ----- ----------------------------------------
    04102026  22.6  12.2 AEROPARQUE AERO
    04102026             BENITO JUAREZ AERO

``FECHA`` is ``ddmmaaaa``; TMAX/TMIN may be blank (no observation) or negative.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

Span = tuple[int, int | None]

# (date, tmax, tmin, name) character spans, derived from the real file header.
DEFAULT_SPANS: tuple[Span, Span, Span, Span] = ((0, 8), (9, 14), (15, 20), (21, None))

_DASH_RUN = re.compile(r"-+")


class RegtempParseError(ValueError):
    """Raised when a data line of a regtemp file cannot be parsed."""


@dataclass(frozen=True)
class DailyObs:
    """One station-day of observed extreme temperatures (degrees C)."""

    date: dt.date
    station_name: str
    tmax: float | None
    tmin: float | None


def _is_dash_line(stripped: str) -> bool:
    return "-" in stripped and set(stripped) <= {"-", " "}


def _spans_from_dashes(line: str) -> tuple[Span, Span, Span, Span] | None:
    runs = [(m.start(), m.end()) for m in _DASH_RUN.finditer(line)]
    if len(runs) != 4:
        return None
    (d0, d1), (a0, a1), (b0, b1), (n0, _) = runs
    return ((d0, d1), (a0, a1), (b0, b1), (n0, None))


def _fail(line_no: int, line: str, reason: str) -> RegtempParseError:
    return RegtempParseError(f"line {line_no}: {reason}: {line!r}")


def _parse_date(raw: str, line_no: int, line: str) -> dt.date:
    if len(raw) != 8 or not raw.isdigit():
        raise _fail(line_no, line, f"invalid date {raw!r} (expected ddmmaaaa)")
    try:
        return dt.datetime.strptime(raw, "%d%m%Y").date()
    except ValueError:
        raise _fail(line_no, line, f"invalid calendar date {raw!r}") from None


def _parse_temperature(raw: str, line_no: int, line: str) -> float | None:
    text = raw.strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        raise _fail(line_no, line, f"invalid temperature {text!r}") from None
    if not math.isfinite(value):
        raise _fail(line_no, line, f"non-finite temperature {text!r}")
    return value


def _slice(line: str, span: Span) -> str:
    start, end = span
    return line[start:end]


def _parse_row(line: str, line_no: int, spans: tuple[Span, Span, Span, Span]) -> DailyObs:
    date_span, tmax_span, tmin_span, name_span = spans
    day = _parse_date(_slice(line, date_span).strip(), line_no, line)
    name = _slice(line, name_span).strip()
    if not name:
        raise _fail(line_no, line, "missing station name")
    return DailyObs(
        date=day,
        station_name=name,
        tmax=_parse_temperature(_slice(line, tmax_span), line_no, line),
        tmin=_parse_temperature(_slice(line, tmin_span), line_no, line),
    )


def parse_regtemp(text: str) -> tuple[DailyObs, ...]:
    """Parse the full text of a regtemp file into daily observations.

    Blank lines and the two header lines are ignored. Any other line must be a valid
    data row, otherwise ``RegtempParseError`` is raised with the 1-based line number.
    """
    spans = DEFAULT_SPANS
    rows: list[DailyObs] = []
    for line_no, raw in enumerate(text.split("\n"), start=1):
        line = raw.rstrip("\r")
        stripped = line.strip()
        if not stripped or stripped.upper().startswith("FECHA"):
            continue
        if _is_dash_line(stripped):
            spans = _spans_from_dashes(line) or spans
            continue
        rows.append(_parse_row(line, line_no, spans))
    return tuple(rows)


def load_regtemp(path: str | Path) -> tuple[DailyObs, ...]:
    """Read a regtemp file from disk (latin-1) and parse it."""
    return parse_regtemp(Path(path).read_text(encoding="latin-1"))


def group_by_station(observations: Iterable[DailyObs]) -> dict[str, tuple[DailyObs, ...]]:
    """Group observations by SMN station name, preserving input order within a station."""
    grouped: dict[str, list[DailyObs]] = {}
    for obs in observations:
        grouped.setdefault(obs.station_name, []).append(obs)
    return {name: tuple(items) for name, items in grouped.items()}
