"""HTML page of the local monitor (FRA-364): the same report as the terminal, for the browser.

No JavaScript, no external resources, and every piece of text is escaped. Anything that comes from a
remote response (`source_reason`, `station_name`, `detail`...) is untrusted: it only reaches the page
through `esc()` or through a table cell, which escapes unless the cell is explicitly marked `Html`.
"""

from __future__ import annotations

import html
import math
from collections.abc import Sequence

from monitor_core.models_compare import CityComparison, DayComparison, ModelsSection
from monitor_core.production import (
    AlertasInfo,
    DashboardInfo,
    NieblaInfo,
    ProductionSection,
    format_age,
)
from monitor_core.quotas import QuotaRow, QuotasSection
from monitor_core.render import fmt_int, fmt_num, fmt_pct
from monitor_core.report import Report, SectionEntry
from monitor_core.sources import SourceProbe, SourcesSection
from monitor_core.status import Status
from monitor_core.views import flag_text
from monitor_core.views_models import (
    HEADERS as MODEL_HEADERS,
)
from monitor_core.views_models import (
    day_label_text,
    model_mm_text,
    model_temps_text,
    temps_text,
    who_rains,
)

REFRESH_WHILE_UPDATING_S = 3
PROD_URL = "https://skypulse-api-mund.onrender.com"
_BADGE_CLASS = {Status.OK: "ok", Status.WARN: "warn", Status.CRITICAL: "crit"}

CSS = """
:root{color-scheme:light dark;--bg:#f4f6fa;--card:#fff;--ink:#0b1426;--muted:#586377;--line:#d5dbe6;
--ok:#126b36;--warn:#8a5a00;--crit:#b0201d;--okbg:#dff3e6;--warnbg:#fbeccb;--critbg:#fbdcda;--skipbg:#e6e9f0}
@media (prefers-color-scheme:dark){:root{--bg:#060d1a;--card:#0d1e38;--ink:#e8edf6;--muted:#9aa7bd;
--line:#233556;--ok:#7be0a1;--warn:#f2c35b;--crit:#ff8f8a;--okbg:#10361f;--warnbg:#3a2c0a;--critbg:#4a1614;
--skipbg:#1a2a47}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:16px}
h1{font-size:1.4rem;margin:.2rem 0}h2{font-size:1.1rem;margin:0 0 .6rem;display:flex;gap:.6rem;align-items:center}
h3{font-size:1rem;margin:1rem 0 .3rem}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:14px 0}
.muted{color:var(--muted)}.small{font-size:.85rem}
.table-wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{padding:6px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;white-space:nowrap}
td.r,th.r{text-align:right}
td.wrap{white-space:normal}
.badge{display:inline-block;border-radius:999px;padding:1px 10px;font-size:.8rem;font-weight:600}
.badge.ok{background:var(--okbg);color:var(--ok)}.badge.warn{background:var(--warnbg);color:var(--warn)}
.badge.crit{background:var(--critbg);color:var(--crit)}.badge.skip{background:var(--skipbg);color:var(--muted)}
.flags{color:var(--muted);font-size:.85rem}
.bar{display:inline-block;width:140px;height:10px;border-radius:6px;background:var(--skipbg);vertical-align:middle;
overflow:hidden;margin-right:8px}
.bar span{display:block;height:100%;background:var(--ok)}
.bar.warn span{background:var(--warn)}.bar.crit span{background:var(--crit)}
.notice{border-radius:10px;padding:8px 12px;margin:12px 0;border:1px solid var(--line);background:var(--skipbg)}
.notice.crit{background:var(--critbg);color:var(--crit)}
.disagree{color:var(--warn);font-weight:600}
form{display:flex;gap:.8rem;align-items:center;margin:12px 0}
button{font:inherit;padding:6px 16px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
button:disabled{opacity:.5;cursor:not-allowed}
@media (max-width:600px){main{padding:10px}}
"""


class Html(str):
    """A fragment that is already safe HTML. Anything else is escaped when it is put in a table."""


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _badge(status: Status | None, label: str | None = None) -> Html:
    if status is None:
        return Html('<span class="badge skip">OMITIDA</span>')
    css = _BADGE_CLASS[status]
    return Html(f'<span class="badge {css}">{esc(label or status.label)}</span>')


def _status_cell(status: Status, flags: Sequence[str] = ()) -> Html:
    text = ", ".join(flag_text(f) for f in flags)
    extra = f' <span class="flags">{esc(text)}</span>' if text else ""
    return Html(f"{_badge(status)}{extra}")


def _table(
    headers: Sequence[str], rows: Sequence[Sequence[str]], align: str = ""
) -> Html:
    aligns = (align + "l" * len(headers))[: len(headers)]

    def cell(tag: str, value: str, side: str) -> str:
        css = ' class="r"' if side == "r" else ""
        body = value if isinstance(value, Html) else esc(value)
        return f"<{tag}{css}>{body}</{tag}>"

    head = "".join(cell("th", h, a) for h, a in zip(headers, aligns, strict=True))
    body = "".join(
        "<tr>" + "".join(cell("td", c, a) for c, a in zip(row, aligns, strict=True)) + "</tr>"
        for row in rows
    )
    return Html(
        f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'
    )


def _bar(pct: float, status: Status) -> Html:
    shown = min(max(pct, 0.0), 100.0)
    whole = math.floor(shown + 1e-9)
    return Html(
        f'<div class="bar {_BADGE_CLASS[status]}" role="meter" aria-valuemin="0" aria-valuemax="100" '
        f'aria-valuenow="{whole}" aria-label="Uso del cupo: {esc(fmt_pct(pct))}">'
        f'<span style="width:{shown:.1f}%"></span></div> {esc(fmt_pct(pct))}'
    )


# ------------------------------------------------------------------ 1. quotas


def _quota_row(row: QuotaRow) -> list[str]:
    limit = fmt_int(row.limit) if row.limit else "—"
    if row.error is not None:
        return [row.label, "s/d", limit, row.error, _badge(Status.WARN)]
    usage = "sin cupo propio" if row.pct is None else _bar(row.pct, row.status)
    count = fmt_int(row.count) + ("" if row.present else "*")
    return [row.label, count, limit, usage, _badge(row.status)]


def _quotas(section: QuotasSection) -> str:
    note = f"Día UTC {section.day} (el contador se reinicia a las 21:00, hora de Argentina)"
    table = _table(
        ["Servicio", "Hoy", "Cupo", "Uso", "Estado"],
        [_quota_row(r) for r in section.rows],
        align="lrll",
    )
    star = ""
    if any(not r.present and r.error is None for r in section.rows):
        star = '<p class="muted small">* sin clave en Upstash todavía: cuenta como 0.</p>'
    return f'<p class="muted small">{esc(note)}</p>{table}{star}'


# ------------------------------------------------------------------ 2. production


def _dashboard_row(info: DashboardInfo) -> list[str]:
    source = (
        "s/d" if info.source is None else f"{info.source} ({info.source_reason or 's/d'})"
    )
    station = "—"
    if info.station_icao:
        station = f"{info.station_icao} a {fmt_num(info.station_distance_km)} km"
    models = "+".join(m.upper() for m in info.forecast_models) or "ninguno"
    return [
        info.city,
        str(info.http_status or "—"),
        f"{fmt_num(info.latency_s)} s",
        source,
        station,
        format_age(info.age_minutes),
        models,
        _status_cell(info.status, info.flags),
    ]


def _niebla_row(info: NieblaInfo) -> list[str]:
    detail = info.source or "s/d"
    if info.station:
        detail += f" · {info.station} a {fmt_num(info.distance_km)} km"
    return [
        "/api/niebla",
        str(info.http_status or "—"),
        f"{fmt_num(info.latency_s)} s",
        detail,
        _status_cell(info.status, info.flags),
    ]


def _alertas_row(info: AlertasInfo) -> list[str]:
    if info.available is None:
        detail = "s/d"
    elif info.available:
        detail = "available: sí"
    else:
        detail = "available: no (la fuente oficial del SMN está caída, es conocido)"
    return [
        "/api/alertas-smn",
        str(info.http_status or "—"),
        f"{fmt_num(info.latency_s)} s",
        detail,
        _status_cell(info.status, info.flags),
    ]


def _production(section: ProductionSection) -> str:
    headers = ["Ciudad", "HTTP", "Latencia", "Fuente (motivo)", "Estación"]
    headers += ["Antigüedad", "Modelos", "Estado"]
    dashboards = _table(
        headers, [_dashboard_row(d) for d in section.dashboards], align="lrrlllll"
    )
    others = [_niebla_row(n) for n in (section.niebla,) if n]
    others += [_alertas_row(a) for a in (section.alertas,) if a]
    endpoints = _table(
        ["Endpoint", "HTTP", "Latencia", "Detalle", "Estado"], others, align="lrrll"
    )
    return (
        f'<p class="muted small">Backend: {esc(PROD_URL)} (model=consensus)</p>'
        f"{dashboards}<br>{endpoints}"
    )


# ------------------------------------------------------------------ 3. sources


def _source_row(probe: SourceProbe) -> list[str]:
    state = (
        Html('<span class="badge skip">caído conocido</span>')
        if probe.state == "known_down"
        else _badge(probe.status)
    )
    return [
        probe.label,
        str(probe.http_status or "—"),
        f"{fmt_num(probe.latency_s)} s",
        probe.detail,
        state,
    ]


def _sources(section: SourcesSection) -> str:
    table = _table(
        ["Fuente", "HTTP", "Latencia", "Detalle", "Estado"],
        [_source_row(p) for p in section.probes],
        align="lrrll",
    )
    notes = dict.fromkeys(p.note for p in section.probes if p.note)
    notes_html = "".join(f'<p class="muted small">Nota: {esc(n)}</p>' for n in notes)
    return (
        '<p class="muted small">Consultas directas desde esta PC: la IP no es la de Render.</p>'
        f"{table}{notes_html}"
    )


# ------------------------------------------------------------------ 4. models


def _day_row(day: DayComparison) -> list[str]:
    verdict: str = "—"
    if day.rain_disagreement:
        verdict = Html(
            f'<span class="disagree">DESACUERDO ({esc(who_rains(day))})</span>'
        )
    return [
        day_label_text(day),
        temps_text(day.row_temp_max, day.row_temp_min),
        model_temps_text(day.gfs),
        model_temps_text(day.ecmwf),
        model_mm_text(day.gfs),
        model_mm_text(day.ecmwf),
        verdict,
    ]


def _city(city: CityComparison) -> str:
    if not city.available:
        text = f"{city.city}: sin datos de pronóstico (ver la sección de producción)."
        return f'<p class="disagree">{esc(text)}</p>'
    count = f"{city.disagreement_days} de {len(city.days)} días con desacuerdo de lluvia"
    parts = [f"<h3>{esc(city.city)}: {esc(count)}</h3>"]
    for name in city.missing_models:
        text = f"Falta el modelo {name.upper()} en todo el pronóstico."
        parts.append(f'<p class="disagree">{esc(text)}</p>')
    parts.append(_table(MODEL_HEADERS, [_day_row(d) for d in city.days], align="lrrrrrl"))
    return "".join(parts)


def _models(section: ModelsSection) -> str:
    intro = (
        "Desacuerdo de lluvia = un modelo supera 0,9 mm en el día y el otro no "
        "(0,9 exacto no supera). La fila es lo que ve el usuario; cada modelo es el "
        "detalle que ya no se le muestra."
    )
    cities = "".join(_city(c) for c in section.cities)
    total = f"Total: {section.total_disagreement_days} días con desacuerdo de lluvia."
    return f'<p class="muted small">{esc(intro)}</p>{cities}<p><strong>{esc(total)}</strong></p>'


# ------------------------------------------------------------------ whole page

_BODIES = {
    "quotas": _quotas,
    "production": _production,
    "sources": _sources,
    "models": _models,
}


def _section(index: int, entry: SectionEntry) -> str:
    head = f"<h2>{index}. {esc(entry.title)} {_badge(entry.status)}</h2>"
    if entry.skipped:
        body = f'<p class="muted">Omitida: {esc(entry.summary)}</p>'
    elif entry.detail is None:
        body = f"<p>{esc(entry.summary)}</p>"
    else:
        body = _BODIES[entry.key](entry.detail)
    return f"<section>{head}{body}</section>"


def _summary(report: Report) -> str:
    rows = [
        [f"{i}. {e.title}", _badge(e.status), e.summary]
        for i, e in enumerate(report.sections, start=1)
    ]
    overall = (
        f"<p><strong>Estado general:</strong> {_badge(report.overall)} "
        f'<span class="muted">(código de salida {report.exit_code})</span></p>'
    )
    table = _table(["Sección", "Estado", "Detalle"], rows)
    return f"<section><h2>{len(report.sections) + 1}. Resumen</h2>{table}{overall}</section>"


def _refresh_form(updating: bool, seconds_until_refresh: int) -> str:
    blocked = updating or seconds_until_refresh > 0
    wait = (
        f'<span class="muted small">Podés actualizar en {seconds_until_refresh} s</span>'
        if seconds_until_refresh > 0 and not updating
        else ""
    )
    attr = " disabled" if blocked else ""
    return (
        '<form method="post" action="/actualizar">'
        f'<button type="submit"{attr}>Actualizar</button>{wait}</form>'
    )


def _notices(updating: bool, error: str | None) -> str:
    parts = []
    if updating:
        parts.append(
            '<p class="notice" role="status">Actualizando… (puede tardar si Render está despertando)</p>'
        )
    if error:
        parts.append(
            f'<p class="notice crit" role="alert">La última actualización falló: {esc(error)}</p>'
        )
    return "".join(parts)


def render_page(
    report: Report | None,
    *,
    updating: bool = False,
    seconds_until_refresh: int = 0,
    error: str | None = None,
) -> str:
    refresh = (
        f'<meta http-equiv="refresh" content="{REFRESH_WHILE_UPDATING_S}">'
        if updating
        else ""
    )
    if report is None:
        stamp = '<p class="muted">Todavía no hay datos.</p>'
        body = _notices(updating, error)
    else:
        stamp = f'<p class="muted">Generado: {esc(f"{report.generated_at:%Y-%m-%d %H:%M}")} UTC</p>'
        sections = "".join(_section(i, e) for i, e in enumerate(report.sections, 1))
        body = (
            _notices(updating, error)
            + _refresh_form(updating, seconds_until_refresh)
            + sections
            + _summary(report)
        )
    return (
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"{refresh}<title>SkyPulse · monitor local</title><style>{CSS}</style></head><body><main>"
        "<h1>SkyPulse · monitor local de administración</h1>"
        '<p class="muted">Solo lectura: no escribe nada. Esta página solo responde en esta PC.</p>'
        f"{stamp}{body}</main></body></html>"
    )
