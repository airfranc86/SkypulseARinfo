"""HTML pieces of the plate. Every text goes through :func:`esc`; numbers come from our own code.

Elements that must stay inside the safe zone carry ``data-key`` (and ``data-zone``) so the layout
probe can check them; ``data-fit`` marks texts that must never overflow their box.
"""

from __future__ import annotations

from html import escape

from placa_curva import CurveGeometry, temperature_curve, x_for_hour
from placa_layout import FOOTER_BOX
from placa_textos import AlertBlock, Badge, Figure, PlateContent, Row, TimeWindow

CHART_WIDTH, CHART_HEIGHT = 936, 250
CHART_PAD_X, CHART_PAD_Y = 36, 60
RULER_HOURS = (0, 6, 12, 18, 24)
_EDGE_PX = 70  # labels closer than this to a side are anchored to that side

_ICONS = {
    "alerta": (
        '<path d="M12 3 2 20.5h20z" fill="none" stroke="currentColor" stroke-width="2.4" '
        'stroke-linejoin="round"/><path d="M12 9.5v5M12 17.3v.3" stroke="currentColor" '
        'stroke-width="2.6" stroke-linecap="round"/>'
    ),
    "atencion": (
        '<circle cx="12" cy="12" r="9.4" fill="none" stroke="currentColor" stroke-width="2.4"/>'
        '<path d="M12 7v6.2M12 16.4v.3" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/>'
    ),
    "lluvia": (
        '<path d="M12 2.8c3.6 4.6 6.6 8.3 6.6 11.6a6.6 6.6 0 0 1-13.2 0c0-3.3 3-7 6.6-11.6z" '
        'fill="none" stroke="currentColor" stroke-width="2"/>'
    ),
    "viento": (
        '<path d="M3 8.5h11a3 3 0 1 0-3-3M3 12.5h15a3 3 0 1 1-3 3M3 16.5h7" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
    ),
}


def esc(text: str) -> str:
    return escape(text, quote=True)


def icon(name: str, css_class: str = "ico") -> str:
    return f'<svg class="{css_class}" viewBox="0 0 24 24" aria-hidden="true">{_ICONS[name]}</svg>'


def key(name: str, zone: str = "content") -> str:
    return f'data-key="{esc(name)}" data-zone="{zone}"'


# ---------------------------------------------------------------------------
# Header and footer
# ---------------------------------------------------------------------------

def header(content: PlateContent, logo_uri: str) -> str:
    return (
        '<header class="head">'
        f'<div class="brand" {key("brand")}>'
        f'<img class="brand-logo" src="{esc(logo_uri)}" alt="">'
        '<span class="brand-name">SkyPulse</span>'
        '<span class="brand-tag">Pronóstico</span>'
        "</div>"
        f'<h1 class="city" {key("city")} data-fit="city">{esc(content.city)}</h1>'
        f'<p class="date" {key("date")} data-fit="date">{esc(content.date_label)}</p>'
        "</header>"
    )


def footer(content: PlateContent) -> str:
    return (
        f'<footer class="footer" style="{FOOTER_BOX.css()}">'
        f'<p class="credit" {key("credit", "footer")}>{esc(content.credit)}</p>'
        f'<p class="legend" {key("legend", "footer")} data-fit="legend">{esc(content.legend)}</p>'
        "</footer>"
    )


# ---------------------------------------------------------------------------
# Alert blocks
# ---------------------------------------------------------------------------

def badge(item: Badge) -> str:
    return (
        f'<p class="badge badge--{item.level}">{icon(item.level)}'
        f'<span class="badge-level">{esc(item.label)}</span>'
        '<span class="badge-sep" aria-hidden="true">·</span>'
        f'<span class="badge-topic">{esc(item.topic)}</span></p>'
    )


def figure(item: Figure) -> str:
    caption = "" if item.caption is None else f'<span class="figure-caption">{esc(item.caption)}</span>'
    prefix = "" if item.prefix is None else f'<span class="figure-prefix">{esc(item.prefix)}</span> '
    return (
        '<span class="figure">'
        f'<span class="figure-number">{prefix}<span class="figure-value">{esc(item.value)}</span> '
        f'<span class="figure-unit">{esc(item.unit)}</span></span>{caption}</span>'
    )


def ruler(window: TimeWindow) -> str:
    hours = "".join(
        f'<span style="left:{h / 24 * 100:.2f}%">{h:02d}</span>' for h in RULER_HOURS
    )
    return (
        '<div class="ruler" aria-hidden="true"><div class="ruler-track">'
        f'<div class="ruler-span" style="left:{window.start_pct:.2f}%;width:{window.width_pct:.2f}%"></div>'
        f'</div><div class="ruler-hours">{hours}</div></div>'
    )


def time_window(window: TimeWindow, *, with_ruler: bool) -> str:
    return (
        '<div class="window">'
        f'<p class="window-text"><span class="window-label">{esc(window.label)}</span> '
        f'<span class="window-time">{esc(window.text)}</span></p>'
        f"{ruler(window) if with_ruler else ''}</div>"
    )


def _wind_body(block: AlertBlock) -> str:
    figures = "".join(figure(item) for item in block.figures)
    trail = "" if block.trail is None else f' <span class="alert-trail">{esc(block.trail)}</span>'
    return (
        f'<p class="alert-lead">{esc(block.lead or "")}</p>'
        f'<p class="alert-figures alert-figures--inline" data-fit="wind-figures">{figures}{trail}</p>'
    )


def _block_body(block: AlertBlock) -> str:
    if block.kind == "wind":
        return _wind_body(block)
    if block.kind == "storm":
        return f'<p class="alert-message">{esc(block.lead or "")}</p>'
    figures = "".join(figure(item) for item in block.figures)
    return f'<p class="alert-figures" data-fit="rain-figures">{figures}</p>'


def alert_block(block: AlertBlock, *, primary: bool, with_ruler: bool) -> str:
    """One alert; `with_ruler` draws the 24 h ruler (only the first critical window gets one)."""
    rank = "primary" if primary else "secondary"
    window = "" if block.window is None else time_window(block.window, with_ruler=with_ruler)
    return (
        f'<article class="alert alert--{block.kind} alert--{rank} alert--{block.badge.level}" '
        f'{key(f"alert-{block.kind}")}>'
        f"{badge(block.badge)}{_block_body(block)}{window}</article>"
    )


# ---------------------------------------------------------------------------
# Rows, temperatures and sky
# ---------------------------------------------------------------------------

def row(item: Row, name: str) -> str:
    note = "" if item.note is None else f'<span class="row-note">{esc(item.note)}</span>'
    return (
        f'<div class="row row--{name}" {key(f"row-{name}")} data-fit="row-{name}">'
        f'{icon(name, "ico row-ico")}<span class="row-label">{esc(item.label)}</span>'
        f'<span class="row-text"><span class="row-value">{esc(item.value)}</span>{note}</span></div>'
    )


def _present_rows(content: PlateContent) -> list[tuple[Row, str]]:
    return [(item, name) for item, name in ((content.rain, "lluvia"), (content.wind, "viento")) if item]


def rows(content: PlateContent) -> str:
    parts = [row(item, name) for item, name in _present_rows(content)]
    return f'<section class="rows">{"".join(parts)}</section>' if parts else ""


def summary_lines(content: PlateContent) -> str:
    """The rain / wind rows as short lines under the temperatures (alert plates have little room)."""
    lines = []
    for item, name in _present_rows(content):
        note = "" if item.note is None else f'<span class="summary-note">{esc(item.note)}</span>'
        lines.append(
            f'<p class="summary-line" data-fit="line-{name}">{icon(name, "ico summary-ico")}'
            f'<span class="summary-label">{esc(item.label)}</span> '
            f'<span class="summary-value">{esc(item.value)}</span>{note}</p>'
        )
    return "".join(lines)


def sky_icon(icon_uri: str | None, css_class: str) -> str:
    return "" if icon_uri is None else f'<img class="{css_class}" src="{esc(icon_uri)}" alt="">'


def temperature(label: str, value: str | None, modifier: str) -> str:
    if value is None:
        return ""
    return (
        f'<div class="temp temp--{modifier}"><span class="temp-label">{esc(label)}</span>'
        f'<span class="temp-value">{esc(value)}</span></div>'
    )


# ---------------------------------------------------------------------------
# Temperature chart
# ---------------------------------------------------------------------------

def _anchor(x: float) -> str:
    if x < _EDGE_PX:
        return "start"
    return "end" if x > CHART_WIDTH - _EDGE_PX else "middle"


def _curve_svg(curve: CurveGeometry, content: PlateContent) -> str:
    hot_x, hot_y = curve.hottest
    cool_x, cool_y = curve.coolest
    labels = []
    if content.temp_max is not None:
        labels.append(
            f'<circle class="curve-dot" cx="{hot_x:.1f}" cy="{hot_y:.1f}" r="11"/>'
            f'<text class="curve-label" x="{hot_x:.1f}" y="{hot_y - 24:.1f}" '
            f'text-anchor="{_anchor(hot_x)}">{esc(content.temp_max)}</text>'
        )
    if content.temp_min is not None:
        labels.append(
            f'<circle class="curve-dot curve-dot--cool" cx="{cool_x:.1f}" cy="{cool_y:.1f}" r="11"/>'
            f'<text class="curve-label curve-label--cool" x="{cool_x:.1f}" y="{cool_y + 56:.1f}" '
            f'text-anchor="{_anchor(cool_x)}">{esc(content.temp_min)}</text>'
        )
    ticks = "".join(
        f'<line class="curve-tick" x1="{x:.1f}" x2="{x:.1f}" y1="{CHART_PAD_Y - 30}" '
        f'y2="{CHART_HEIGHT - CHART_PAD_Y}"/>'
        for x in (x_for_hour(h, CHART_WIDTH, CHART_PAD_X) for h in (6, 12, 18))
    )
    return (
        f'<svg class="curve" viewBox="0 0 {CHART_WIDTH} {CHART_HEIGHT}" width="{CHART_WIDTH}" '
        f'height="{CHART_HEIGHT}" aria-hidden="true"><defs><linearGradient id="curve-fill" x1="0" '
        'x2="0" y1="0" y2="1"><stop offset="0" stop-color="#c8a84b" stop-opacity=".34"/>'
        '<stop offset="1" stop-color="#c8a84b" stop-opacity="0"/></linearGradient></defs>'
        f'{ticks}<path class="curve-area" d="{curve.area}"/><path class="curve-line" d="{curve.line}"/>'
        f'{"".join(labels)}</svg>'
    )


def _hour_labels() -> str:
    spans = "".join(
        f'<span style="left:{x_for_hour(h, CHART_WIDTH, CHART_PAD_X) / CHART_WIDTH * 100:.2f}%">'
        f"{h:02d}</span>"
        for h in RULER_HOURS
    )
    return f'<div class="curve-hours">{spans}<span class="curve-hours-unit">hs</span></div>'


def chart(content: PlateContent) -> str:
    """The curve of the day; a minimum-maximum bar without hourly data; nothing without both."""
    curve = temperature_curve(
        content.curve,
        width=CHART_WIDTH,
        height=CHART_HEIGHT,
        pad_x=CHART_PAD_X,
        pad_y=CHART_PAD_Y,
    )
    if curve is not None:
        return (
            f'<section class="chart" {key("chart")}>'
            '<h2 class="section-title">Temperatura durante el día</h2>'
            f"{_curve_svg(curve, content)}{_hour_labels()}</section>"
        )
    if content.temp_min is None or content.temp_max is None:
        return ""
    return (
        f'<section class="chart chart--minmax" {key("chart")}>'
        '<h2 class="section-title">Temperatura del día</h2>'
        f'<div class="minmax"><span class="minmax-end">{esc(content.temp_min)}</span>'
        f'<span class="minmax-bar"></span><span class="minmax-end">{esc(content.temp_max)}</span></div>'
        "</section>"
    )
