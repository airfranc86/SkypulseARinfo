"""What the plate says, in hierarchy order (pure: no HTML, no I/O).

Hierarchy (FRA-326): 1) wind alert, 2) storm, 3) rain (probability, amount, critical window),
4) maximum, minimum and sky. Severity is always written, never only coloured:

- ``Alerta`` (red): what makes the plate an alert: gusts of 50 km/h or more, a storm, rain above 15 mm.
- ``Atención`` (amber): rain that does not reach the alert, shown on an alert plate.

Numbers follow the caption (same rounding) and the rain text is decided once for both
(`lluvia_texto.rain_summary`), so plate and caption never disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from caption import CREDIT, format_mm
from fechas import format_long_date
from lluvia_texto import DRY, SMALL_AMOUNT, rain_summary
from reglas import (
    STORM_TEXT,
    VARIANT_LABEL,
    Assessment,
    RainInfo,
    Variante,
    Window,
    WindAlert,
    assess,
    format_window,
    gust_window,
    rain_window,
    round_half_up,
    wind_origin,
)
from tipos import ReportData, TempPoint

Level = Literal["alerta", "atencion"]
BlockKind = Literal["wind", "storm", "rain"]

LEVEL_LABEL: dict[str, str] = {"alerta": "Alerta", "atencion": "Atención"}
PLATE_LEGEND = "Pronóstico de SkyPulse · no es un aviso oficial · smn.gob.ar"
MINUS = "−"
# Sky texts that only restate a phenomenon that already has its own block.
_RAIN_SKIES = frozenset({"Lluvia", "Lluvia leve", "Llovizna", "Lluvia helada"})


@dataclass(frozen=True)
class Badge:
    level: Level
    topic: str

    @property
    def label(self) -> str:
        return LEVEL_LABEL[self.level]


@dataclass(frozen=True)
class Figure:
    value: str
    unit: str
    caption: str | None = None
    prefix: str | None = None  # small word before the number ("hasta")


@dataclass(frozen=True)
class TimeWindow:
    """A critical window and where it sits on a 00-24 h ruler (percent of the day)."""

    label: str
    text: str
    start_pct: float
    width_pct: float


@dataclass(frozen=True)
class AlertBlock:
    kind: BlockKind
    badge: Badge
    figures: tuple[Figure, ...]
    lead: str | None  # text before the figures ("Ráfagas de") or the whole message (storm)
    trail: str | None  # text after the figures ("del sur")
    window: TimeWindow | None


@dataclass(frozen=True)
class Row:
    """A labelled line of the summary: ``Lluvia | 60 % · 3 mm | Más intensa de ...``."""

    label: str
    value: str
    note: str | None


@dataclass(frozen=True)
class PlateContent:
    variante: Variante
    city: str
    date_label: str
    alerts: tuple[AlertBlock, ...]
    dense: bool  # three alert blocks: the tightest layout
    compact: bool  # wind and rain blocks together: the two tallest blocks need a tighter layout
    temp_max: str | None
    temp_min: str | None
    sky: str | None
    sky_icon: str | None
    rain: Row | None
    wind: Row | None
    curve: tuple[TempPoint, ...]
    credit: str
    legend: str


def _time_window(window: Window | None, label: str) -> TimeWindow | None:
    if window is None:
        return None
    start, end = window
    return TimeWindow(
        label=label,
        text=format_window(window),
        start_pct=start / 24 * 100,
        width_pct=(end - start) / 24 * 100,
    )


def _wind_block(alert: WindAlert, data: ReportData) -> AlertBlock:
    return AlertBlock(
        kind="wind",
        badge=Badge("alerta", "Viento fuerte"),
        figures=(Figure(str(alert.gust_kmh), "km/h"),),
        lead="Ráfagas de",
        trail=alert.origin,
        window=_time_window(gust_window(data.slots), "Más fuertes"),
    )


def _storm_block() -> AlertBlock:
    return AlertBlock(
        kind="storm", badge=Badge("alerta", "Tormenta"), figures=(), lead=STORM_TEXT, trail=None, window=None
    )


def _rain_block(rain: RainInfo, data: ReportData, qualifier: str | None) -> AlertBlock:
    figures = [] if rain.prob_pct is None else [Figure(str(rain.prob_pct), "%", "probabilidad")]
    figures.append(Figure(format_mm(rain.mm), "mm", "en el día", prefix=qualifier))
    badge = Badge("alerta", "Lluvia fuerte") if rain.heavy else Badge("atencion", "Lluvia")
    return AlertBlock(
        kind="rain",
        badge=badge,
        figures=tuple(figures),
        lead=None,
        trail=None,
        window=_time_window(rain_window(data.slots), "Más intensa"),
    )


def _alert_blocks(data: ReportData, result: Assessment) -> tuple[AlertBlock, ...]:
    blocks: list[AlertBlock] = []
    if result.wind is not None:
        blocks.append(_wind_block(result.wind, data))
    if result.storm:
        blocks.append(_storm_block())
    if result.rain is not None:
        summary = rain_summary(data, result)
        blocks.append(_rain_block(result.rain, data, None if summary is None else summary.qualifier))
    return tuple(blocks)


def _rain_row(data: ReportData, result: Assessment) -> Row | None:
    summary = rain_summary(data, result)
    if summary is None:
        return None  # the amount is unknown: nothing is said
    if summary.kind == "lluvia" and summary.mm is not None:
        amount = " ".join(p for p in (summary.qualifier, f"{format_mm(summary.mm)} mm") if p)
        parts = ([] if summary.prob_pct is None else [f"{summary.prob_pct} %"]) + [amount]
        note = None if summary.window is None else f"Más intensa de {summary.window}"
        return Row("Lluvia", " · ".join(parts), note)
    if summary.kind == "poca":
        return Row("Lluvia", f"{summary.prob_pct} %", SMALL_AMOUNT)
    return Row("Lluvia", DRY, None)


def _wind_row(data: ReportData) -> Row | None:
    gust = None if data.wind_gust_max is None else f"Ráfagas de hasta {round_half_up(data.wind_gust_max)} km/h"
    if data.wind_speed_max is None:
        return None if gust is None else Row("Viento", gust, None)
    origin = wind_origin(data.wind_dir_deg)
    speed = f"{round_half_up(data.wind_speed_max)} km/h"
    return Row("Viento", speed if origin is None else f"{speed} {origin}", gust)


def _sky(result: Assessment, has_blocks: bool) -> str | None:
    if result.sky is None or not has_blocks:
        return result.sky
    redundant = (result.storm and result.sky == "Tormenta") or (
        result.rain is not None and result.sky in _RAIN_SKIES
    )
    return None if redundant else result.sky


def _degrees(value: int | None) -> str | None:
    """``24°``; below zero with a real minus sign (``−3°``), which reads better than a hyphen in big type."""
    if value is None:
        return None
    return f"{MINUS}{abs(value)}°" if value < 0 else f"{value}°"


def build_content(data: ReportData, variante: Variante) -> PlateContent:
    """Every text of one plate. The alert blocks only exist on the ``Alerta`` variant."""
    if variante not in VARIANT_LABEL:
        raise ValueError(f"unknown variant {variante!r}: expected one of {sorted(VARIANT_LABEL)}")
    result = assess(data)
    alerts = _alert_blocks(data, result) if variante == "Alerta" else ()
    covered = {block.kind for block in alerts}
    long_date = format_long_date(data.date)
    return PlateContent(
        variante=variante,
        city=data.city.name,
        date_label=long_date[:1].upper() + long_date[1:],
        alerts=alerts,
        dense=len(alerts) >= 3,
        compact=len(alerts) < 3 and {"wind", "rain"} <= covered,
        temp_max=_degrees(data.temp_max),
        temp_min=_degrees(data.temp_min),
        sky=_sky(result, bool(alerts)),
        sky_icon=data.icon or None,
        rain=None if "rain" in covered else _rain_row(data, result),
        wind=None if "wind" in covered else _wind_row(data),
        curve=data.temp_curve,
        credit=CREDIT,
        legend=PLATE_LEGEND,
    )
