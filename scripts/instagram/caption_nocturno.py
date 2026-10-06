"""Short caption of the night notice: only the intense phenomena of the affected cities.

Same tone and hard rules as the daily caption (:mod:`caption`): no model or source names (the only
mention is the fixed phrase "según el modelo" of the storm line), never an invented datum, the fog
always "posible". Lines follow the plate's hierarchy: wind, storm, heavy rain, dense fog.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import TYPE_CHECKING

from caption import CREDIT, HASHTAGS, LEGEND, PRECAUTIONS, rain_line, wind_line
from fechas import format_long_date
from lluvia_texto import rain_summary
from reglas import FOG_TEXT, STORM_TEXT, Fog, assess, format_fog_hours

if TYPE_CHECKING:
    from aviso_nocturno import NightCity

FOG_PRECAUTION = "Niebla densa posible en {cities}: manejá con luces bajas y bajá la velocidad."
MAX_PRECAUTIONS = 2

_WHEN = {0: "hoy", 1: "mañana", 2: "pasado mañana"}


def _join_names(names: Sequence[str]) -> str:
    """``A``, ``A y B``, ``A, B y C``."""
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} y {names[-1]}"


def _header(day: date, today: date) -> str:
    when = _WHEN.get((day - today).days)
    target = f"{when}, {format_long_date(day)}" if when else f"el {format_long_date(day)}"
    return f"🌙 Aviso para {target}"


def fog_line(fog: Fog) -> str:
    """``🌫️ Niebla densa posible de 04:00 a 09:00 hs, con visibilidad mínima de 200 m``."""
    when = "a las" if fog.first_hour == fog.last_hour else "de"
    return f"🌫️ {FOG_TEXT} {when} {format_fog_hours(fog)}, con visibilidad mínima de {fog.min_visibility_m} m"


def _city_block(city: NightCity) -> str:
    result = assess(city.data)
    lines = [f"📍 {city.data.city.name}"]
    if result.wind is not None:
        lines.append(wind_line(result.wind))
    if result.storm:
        lines.append(f"⛈️ {STORM_TEXT}")
    rain = rain_summary(city.data, result)
    if rain is not None and rain.heavy:
        lines.append(rain_line(rain))
    if city.fog is not None:
        lines.append(fog_line(city.fog))
    return "\n".join(lines)


def _precautions(cities: Sequence[NightCity]) -> str | None:
    """The first ``MAX_PRECAUTIONS`` that apply, in hierarchy order, each naming its cities."""
    assessed = [(city, assess(city.data)) for city in cities]
    lines = []
    for emoji, template, applies in PRECAUTIONS:
        names = [city.data.city.name for city, result in assessed if applies(result)]
        if names:
            lines.append(f"{emoji} {template.format(cities=_join_names(names))}")
    foggy = [city.data.city.name for city in cities if city.fog is not None]
    if foggy:
        lines.append(f"🌫️ {FOG_PRECAUTION.format(cities=_join_names(foggy))}")
    return "\n".join(["⚠️ Precauciones", *lines[:MAX_PRECAUTIONS]]) if lines else None


def build_night_caption(cities: Sequence[NightCity], *, today: date) -> str:
    """One caption for the affected cities of the night notice (every one must be intense)."""
    if not cities:
        raise ValueError("build_night_caption needs at least one affected city")
    if any(not city.intense for city in cities):
        raise ValueError("every city of the night notice must have an intense phenomenon")
    days = {city.data.date for city in cities}
    if len(days) != 1:
        raise ValueError("all cities must share the same date")
    sections = [
        _header(cities[0].data.date, today),
        *(_city_block(city) for city in cities),
        _precautions(cities),
        f"{LEGEND}\n{CREDIT}",
        HASHTAGS,
    ]
    return "\n\n".join(section for section in sections if section) + "\n"
