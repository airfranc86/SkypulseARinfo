"""Text rendering of the report sections (Spanish, rioplatense). JSON lives in report.py."""

from __future__ import annotations

from collections.abc import Sequence

from monitor_core.production import (
    AlertasInfo,
    DashboardInfo,
    NieblaInfo,
    ProductionSection,
    format_age,
)
from monitor_core.quotas import QuotaRow, QuotasSection
from monitor_core.render import Painter, fmt_int, fmt_num, render_table, usage_bar
from monitor_core.report import Report, SectionEntry
from monitor_core.sources import SourceProbe, SourcesSection
from monitor_core.status import Status
from monitor_core.views_models import view_models

FLAG_TEXT = {
    "lento": "lento (> 3 s)",
    "429": "429 (límite de pedidos)",
    "503": "503 (no disponible)",
    "sin_respuesta": "sin respuesta",
    "falta_modelo": "falta un modelo",
    "dato_viejo": "dato viejo",
    "respuesta_invalida": "respuesta inválida",
}
RULE = "═" * 3


def flag_text(flag: str) -> str:
    if flag.startswith("http_"):
        return f"HTTP {flag[5:]}"
    return FLAG_TEXT.get(flag, flag)


def status_cell(painter: Painter, status: Status, flags: Sequence[str] = ()) -> str:
    text = status.label + (
        f" · {', '.join(flag_text(f) for f in flags)}" if flags else ""
    )
    return painter.status(text, status)


def section_header(painter: Painter, index: int, entry: SectionEntry) -> str:
    badge = "OMITIDA" if entry.status is None else entry.status.label
    colored = (
        painter.paint(badge, "dim")
        if entry.status is None
        else painter.status(badge, entry.status)
    )
    return f"{painter.paint(f'{RULE} {index}. {entry.title}', 'bold')}  [{colored}]"


def view_skipped(painter: Painter, entry: SectionEntry) -> list[str]:
    return [f"  {painter.paint('Omitida: ' + entry.summary, 'dim')}"]


# ------------------------------------------------------------------ 1. quotas


def _quota_row(painter: Painter, row: QuotaRow) -> list[str]:
    if row.error is not None:
        return [
            row.label,
            "s/d",
            fmt_int(row.limit) if row.limit else "—",
            row.error,
            painter.status("ATENCIÓN", Status.WARN),
        ]
    usage = (
        "sin cupo propio"
        if row.pct is None
        else painter.status(usage_bar(row.pct), row.status)
    )
    count = fmt_int(row.count) + ("" if row.present else "*")
    return [
        row.label,
        count,
        fmt_int(row.limit) if row.limit else "—",
        usage,
        painter.status(row.status.label, row.status),
    ]


def view_quotas(painter: Painter, section: QuotasSection) -> list[str]:
    lines = [
        f"  Día UTC {section.day} (el contador se reinicia a las 21:00, hora de Argentina)"
    ]
    rows = [_quota_row(painter, row) for row in section.rows]
    lines += render_table(
        ["Servicio", "Hoy", "Cupo", "Uso", "Estado"], rows, align="lrll"
    )
    if any(not r.present and r.error is None for r in section.rows):
        lines.append(
            painter.paint("  * sin clave en Upstash todavía: cuenta como 0.", "dim")
        )
    return lines


# ------------------------------------------------------------------ 2. production


def _dashboard_row(painter: Painter, info: DashboardInfo) -> list[str]:
    source = (
        "s/d"
        if info.source is None
        else f"{info.source} ({info.source_reason or 's/d'})"
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
        status_cell(painter, info.status, info.flags),
    ]


def _niebla_row(painter: Painter, info: NieblaInfo) -> list[str]:
    station = f"{info.source or 's/d'}" + (
        f" · {info.station} a {fmt_num(info.distance_km)} km" if info.station else ""
    )
    return [
        "/api/niebla",
        str(info.http_status or "—"),
        f"{fmt_num(info.latency_s)} s",
        station,
        status_cell(painter, info.status, info.flags),
    ]


def _alertas_row(painter: Painter, info: AlertasInfo) -> list[str]:
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
        status_cell(painter, info.status, info.flags),
    ]


def view_production(painter: Painter, section: ProductionSection) -> list[str]:
    lines = [
        f"  Backend: {painter.paint('https://skypulse-api-mund.onrender.com', 'info')}  (model=consensus)"
    ]
    headers = [
        "Ciudad",
        "HTTP",
        "Latencia",
        "Fuente (motivo)",
        "Estación",
        "Antigüedad",
        "Modelos",
        "Estado",
    ]
    lines += render_table(
        headers,
        [_dashboard_row(painter, d) for d in section.dashboards],
        align="lrrlllll",
    )
    others: list[list[str]] = []
    if section.niebla:
        others.append(_niebla_row(painter, section.niebla))
    if section.alertas:
        others.append(_alertas_row(painter, section.alertas))
    lines.append("")
    lines += render_table(
        ["Endpoint", "HTTP", "Latencia", "Detalle", "Estado"], others, align="lrrll"
    )
    return lines


# ------------------------------------------------------------------ 3. sources


def _source_row(painter: Painter, probe: SourceProbe) -> list[str]:
    if probe.state == "known_down":
        state = painter.paint("caído conocido", "dim")
    else:
        state = painter.status(probe.status.label, probe.status)
    return [
        probe.label,
        str(probe.http_status or "—"),
        f"{fmt_num(probe.latency_s)} s",
        probe.detail,
        state,
    ]


def view_sources(painter: Painter, section: SourcesSection) -> list[str]:
    lines = ["  Consultas directas desde esta PC: la IP no es la de Render."]
    lines += render_table(
        ["Fuente", "HTTP", "Latencia", "Detalle", "Estado"],
        [_source_row(painter, p) for p in section.probes],
        align="lrrll",
    )
    notes = dict.fromkeys(p.note for p in section.probes if p.note)
    lines += [painter.paint(f"  Nota: {note}", "dim") for note in notes]
    return lines


# ------------------------------------------------------------------ 5. summary


def view_summary(painter: Painter, report: Report) -> list[str]:
    rows = []
    for index, entry in enumerate(report.sections, start=1):
        state = (
            painter.paint("OMITIDA", "dim")
            if entry.status is None
            else painter.status(entry.status.label, entry.status)
        )
        rows.append([f"{index}. {entry.title}", state, entry.summary])
    lines = render_table(["Sección", "Estado", "Detalle"], rows)
    overall = painter.status(report.overall.label, report.overall)
    lines.append("")
    lines.append(
        f"  {painter.paint('Estado general:', 'bold')} {overall}  (código de salida {report.exit_code})"
    )
    return lines


# ------------------------------------------------------------------ whole report

_BODY_VIEWS = {
    "quotas": view_quotas,
    "production": view_production,
    "sources": view_sources,
    "models": view_models,
}


def _entry_lines(painter: Painter, entry: SectionEntry) -> list[str]:
    if entry.skipped:
        return view_skipped(painter, entry)
    if entry.detail is None:
        return [f"  {painter.status(entry.summary, entry.status or Status.WARN)}"]
    return _BODY_VIEWS[entry.key](painter, entry.detail)


def render_report(report: Report, painter: Painter) -> str:
    title = painter.paint("SkyPulse · monitor local de administración", "bold")
    lines = [
        f"{title}  (solo lectura: no escribe nada)",
        f"Generado: {report.generated_at:%Y-%m-%d %H:%M} UTC",
        "",
    ]
    for index, entry in enumerate(report.sections, start=1):
        lines.append(section_header(painter, index, entry))
        lines += _entry_lines(painter, entry)
        lines.append("")
    lines.append(painter.paint(f"{RULE} {len(report.sections) + 1}. Resumen", "bold"))
    lines += view_summary(painter, report)
    return "\n".join(lines)
