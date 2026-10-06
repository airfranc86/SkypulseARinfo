"""Text rendering of section 4: the GFS vs ECMWF table per city."""

from __future__ import annotations

from monitor_core.models_compare import (
    CityComparison,
    DayComparison,
    ModelNumbers,
    ModelsSection,
    rain_votes,
)
from monitor_core.render import Painter, fmt_num, render_table

HEADERS = ["Día", "Fila °C", "GFS °C", "ECMWF °C", "GFS mm", "ECMWF mm", "Lluvia"]


def temps_text(tmax: float | None, tmin: float | None) -> str:
    if tmax is None and tmin is None:
        return "s/d"
    return f"{fmt_num(tmax, 0)}/{fmt_num(tmin, 0)}"


def model_temps_text(model: ModelNumbers | None) -> str:
    return "s/d" if model is None else temps_text(model.temp_max, model.temp_min)


def model_mm_text(model: ModelNumbers | None) -> str:
    return "s/d" if model is None else fmt_num(model.precip_sum)


def who_rains(day: DayComparison) -> str:
    gfs = rain_votes(day.gfs.precip_sum if day.gfs else None)
    ecmwf = rain_votes(day.ecmwf.precip_sum if day.ecmwf else None)
    if gfs and not ecmwf:
        return "solo GFS"
    if ecmwf and not gfs:
        return "solo ECMWF"
    return "por redondeo"


def day_label_text(day: DayComparison) -> str:
    short = f"{day.date[8:10]}/{day.date[5:7]}" if len(day.date) >= 10 else day.date
    return f"{day.day_label} {short}".strip()


def _day_row(painter: Painter, day: DayComparison) -> list[str]:
    verdict = "—"
    if day.rain_disagreement:
        verdict = painter.paint(f"DESACUERDO ({who_rains(day)})", "warn")
    return [
        day_label_text(day),
        temps_text(day.row_temp_max, day.row_temp_min),
        model_temps_text(day.gfs),
        model_temps_text(day.ecmwf),
        model_mm_text(day.gfs),
        model_mm_text(day.ecmwf),
        verdict,
    ]


def _city_header(painter: Painter, city: CityComparison) -> str:
    days = len(city.days)
    count = f"{city.disagreement_days} de {days} días con desacuerdo de lluvia"
    style = "warn" if city.disagreement_days else "ok"
    return f"  {painter.paint(city.city, 'bold')}: {painter.paint(count, style)}"


def view_city(painter: Painter, city: CityComparison) -> list[str]:
    if not city.available:
        text = f"  {city.city}: sin datos de pronóstico (ver la sección de producción)."
        return [painter.paint(text, "warn")]
    lines = [_city_header(painter, city)]
    for name in city.missing_models:
        lines.append(
            painter.paint(
                f"  Falta el modelo {name.upper()} en todo el pronóstico.", "warn"
            )
        )
    lines += render_table(
        HEADERS, [_day_row(painter, d) for d in city.days], align="lrrrrrl"
    )
    return lines


def view_models(painter: Painter, section: ModelsSection) -> list[str]:
    lines = [
        "  Desacuerdo de lluvia = un modelo supera 0,9 mm en el día y el otro no (0,9 exacto no supera).",
        "  La fila es lo que ve el usuario; cada modelo es el detalle que ya no se le muestra.",
    ]
    for city in section.cities:
        lines.append("")
        lines += view_city(painter, city)
    lines.append("")
    lines.append(
        f"  Total: {section.total_disagreement_days} días con desacuerdo de lluvia."
    )
    return lines
