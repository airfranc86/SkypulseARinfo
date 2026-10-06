"""The single daily Instagram caption for the three cities (pure text, Rioplatense Spanish).

Hard rules: never name the weather models (the only mention is the fixed phrase
"según el modelo" of the storm line), never invent a datum (a missing value is left out), never
quantify hail, no technicalities.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date

from fechas import format_long_date
from lluvia_texto import DRY, SMALL_AMOUNT, RainSummary, rain_summary
from reglas import STORM_TEXT, Assessment, WindAlert, assess, round_half_up
from tipos import ReportData

LEGEND = "Pronóstico de SkyPulse, no es un aviso oficial. Consultá los avisos del SMN en smn.gob.ar"
CREDIT = "Datos: SkyPulse"
HASHTAGS = "#Clima #Argentina #Pronóstico #SkyPulse"

_WHEN = {0: "hoy", 1: "mañana", 2: "pasado mañana"}

_SKY_EMOJI = {
    "Despejado": "☀️",
    "Parcialmente nublado": "⛅",
    "Cubierto": "☁️",
    "Niebla": "🌫️",
    "Llovizna": "🌦️",
    "Lluvia leve": "🌦️",
    "Lluvia": "🌧️",
    "Lluvia helada": "🧊",
    "Nieve leve": "❄️",
    "Nieve": "❄️",
    "Tormenta": "⛈️",
}
# Sky texts that only restate a phenomenon that already has its own line.
_RAIN_SKIES = frozenset({"Lluvia", "Lluvia leve", "Llovizna", "Lluvia helada"})

Precaution = tuple[str, str, Callable[[Assessment], bool]]
PRECAUTIONS: tuple[Precaution, ...] = (
    ("💨", "Viento fuerte en {cities}: asegurá los objetos sueltos y manejá con precaución.",
     lambda a: a.wind is not None),
    ("⛈️", "Tormenta fuerte posible en {cities}: evitá refugiarte bajo árboles y seguí los avisos oficiales.",
     lambda a: a.storm),
    ("🌧️", "Lluvia fuerte en {cities}: evitá las zonas anegables y salí con tiempo.",
     lambda a: a.rain is not None and a.rain.heavy),
)


def _join_names(names: Sequence[str]) -> str:
    """``A``, ``A y B``, ``A, B y C``."""
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} y {names[-1]}"


def format_mm(mm: float) -> str:
    """Rain amount like the caption says it: whole from 10 mm, else one decimal with a comma."""
    if mm >= 10:
        return str(round_half_up(mm))
    text = f"{mm:.1f}"
    return text.removesuffix(".0").replace(".", ",")


def _header(day: date, today: date) -> str:
    when = _WHEN.get((day - today).days)
    target = f"{when}, {format_long_date(day)}" if when else f"el {format_long_date(day)}"
    return f"🌤️ Pronóstico para {target}"


def _temperatures(data: ReportData) -> str | None:
    parts = []
    if data.temp_max is not None:
        parts.append(f"Máx. {data.temp_max}°")
    if data.temp_min is not None:
        parts.append(f"Mín. {data.temp_min}°")
    return f"🌡️ {' · '.join(parts)}" if parts else None


def _sky_line(result: Assessment) -> str | None:
    if result.sky is None:
        return None
    redundant = (result.storm and result.sky == "Tormenta") or (
        result.rain is not None and result.sky in _RAIN_SKIES
    )
    return None if redundant else f"{_SKY_EMOJI.get(result.sky, '🌤️')} {result.sky}"


def rain_line(rain: RainSummary) -> str:
    """Same decision as the plate (`lluvia_texto.rain_summary`), worded for the caption."""
    if rain.kind == "seco":
        return f"☂️ {DRY}"
    probability = None if rain.prob_pct is None else f"{rain.prob_pct} % de probabilidad"
    if rain.kind == "poca":
        return f"🌦️ Lluvia: {', '.join(p for p in (SMALL_AMOUNT, probability) if p)}"
    parts = [] if probability is None else [probability]
    if rain.mm is not None:
        parts.append(f"{rain.qualifier or 'unos'} {format_mm(rain.mm)} mm")
    if rain.window is not None:
        parts.append(f"más intensa de {rain.window}")
    return f"🌧️ Lluvia: {', '.join(parts)}"


def wind_line(wind: WindAlert) -> str:
    line = f"💨 Ráfagas de hasta {wind.gust_kmh} km/h"
    if wind.origin is not None:
        line += f" {wind.origin}"
    if wind.window is not None:
        line += f", más fuertes de {wind.window}"
    return line


def _city_block(data: ReportData, result: Assessment) -> str:
    lines: list[str | None] = [
        f"📍 {data.city.name}",
        _temperatures(data),
        _sky_line(result),
    ]
    rain = rain_summary(data, result)
    if rain is not None:
        lines.append(rain_line(rain))
    if result.wind is not None:
        lines.append(wind_line(result.wind))
    if result.storm:
        lines.append(f"⛈️ {STORM_TEXT}")
    return "\n".join(line for line in lines if line)


def _precautions(assessed: Sequence[tuple[ReportData, Assessment]]) -> str | None:
    lines = []
    for emoji, template, applies in PRECAUTIONS:
        names = [data.city.name for data, result in assessed if applies(result)]
        if names:
            lines.append(f"{emoji} {template.format(cities=_join_names(names))}")
    return "\n".join(["⚠️ Precauciones", *lines]) if lines else None


def build_caption(reports: Sequence[ReportData], *, today: date) -> str:
    """One caption for every city of the day. `today` (AR) decides "mañana" vs "pasado mañana"."""
    if not reports:
        raise ValueError("build_caption needs at least one city")
    days = {report.date for report in reports}
    if len(days) != 1:
        raise ValueError("all cities must share the same date")
    assessed = [(report, assess(report)) for report in reports]
    sections = [
        _header(reports[0].date, today),
        *(_city_block(data, result) for data, result in assessed),
        _precautions(assessed),
        f"{LEGEND}\n{CREDIT}",
        HASHTAGS,
    ]
    return "\n\n".join(section for section in sections if section) + "\n"
