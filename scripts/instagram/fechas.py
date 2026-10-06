"""Dates in Argentina time and their Spanish names (no dependence on the system locale)."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

# Argentina has no daylight saving time: UTC-3 all year (same constant as the backend).
AR_TZ = timezone(timedelta(hours=-3), "ART")

# The backend forecast covers today plus six days.
MAX_DAYS_AHEAD = 6

DAY_NAMES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MONTH_NAMES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def today_ar(now: datetime | None = None) -> date:
    """Calendar date in Argentina. `now` must carry a timezone; the default is the real clock."""
    if now is None:
        return datetime.now(AR_TZ).date()
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware (naive clocks depend on the machine timezone)")
    return now.astimezone(AR_TZ).date()


def resolve_target_date(*, days: int, explicit: date | None, now: datetime | None = None) -> date:
    """The forecast day: `explicit` if given, else today (AR) plus `days`.

    Raises ValueError when the day is in the past or beyond the forecast window.
    """
    today = today_ar(now)
    target = explicit if explicit is not None else today + timedelta(days=days)
    if target < today:
        raise ValueError(f"{target.isoformat()} is in the past (today is {today.isoformat()})")
    last = today + timedelta(days=MAX_DAYS_AHEAD)
    if target > last:
        raise ValueError(
            f"{target.isoformat()} is outside the forecast window (last day: {last.isoformat()})"
        )
    return target


def parse_iso_date(text: str) -> date:
    """Parse ``AAAA-MM-DD`` strictly; ValueError otherwise."""
    if not _ISO_DATE.fullmatch(text.strip()):
        raise ValueError(f"fecha inválida {text!r}: se espera AAAA-MM-DD")
    try:
        return date.fromisoformat(text.strip())
    except ValueError as exc:
        raise ValueError(f"fecha inválida {text!r}: se espera AAAA-MM-DD ({exc})") from exc


def format_long_date(day: date) -> str:
    """``miércoles 7 de octubre``."""
    return f"{DAY_NAMES[day.weekday()]} {day.day} de {MONTH_NAMES[day.month - 1]}"
