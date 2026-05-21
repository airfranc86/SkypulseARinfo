"""Mapeo WMO weather code → descripción en español + ícono Meteocons."""
from __future__ import annotations

WMO_CODE_MAP: dict[int, dict[str, str]] = {
    0:  {"description": "Despejado",                    "icon_day": "clear-day",                        "icon_night": "clear-night"},
    1:  {"description": "Mayormente despejado",         "icon_day": "partly-cloudy-day",                "icon_night": "partly-cloudy-night"},
    2:  {"description": "Parcialmente nublado",         "icon_day": "partly-cloudy-day",                "icon_night": "partly-cloudy-night"},
    3:  {"description": "Cubierto",                     "icon_day": "overcast-day",                     "icon_night": "overcast-night"},
    45: {"description": "Niebla",                       "icon_day": "fog-day",                          "icon_night": "fog-night"},
    48: {"description": "Niebla con escarcha",          "icon_day": "fog-day",                          "icon_night": "fog-night"},
    51: {"description": "Llovizna leve",                "icon_day": "partly-cloudy-day-drizzle",        "icon_night": "partly-cloudy-night-drizzle"},
    53: {"description": "Llovizna moderada",            "icon_day": "drizzle",                          "icon_night": "drizzle"},
    55: {"description": "Llovizna intensa",             "icon_day": "drizzle",                          "icon_night": "drizzle"},
    56: {"description": "Llovizna helada leve",         "icon_day": "sleet",                            "icon_night": "sleet"},
    57: {"description": "Llovizna helada",              "icon_day": "sleet",                            "icon_night": "sleet"},
    61: {"description": "Lluvia leve",                  "icon_day": "partly-cloudy-day-rain",           "icon_night": "partly-cloudy-night-rain"},
    63: {"description": "Lluvia moderada",              "icon_day": "rain",                             "icon_night": "rain"},
    65: {"description": "Lluvia intensa",               "icon_day": "rain",                             "icon_night": "rain"},
    66: {"description": "Lluvia helada leve",           "icon_day": "sleet",                            "icon_night": "sleet"},
    67: {"description": "Lluvia helada",                "icon_day": "sleet",                            "icon_night": "sleet"},
    71: {"description": "Nieve leve",                  "icon_day": "partly-cloudy-day-snow",           "icon_night": "partly-cloudy-night-snow"},
    73: {"description": "Nieve moderada",               "icon_day": "snow",                             "icon_night": "snow"},
    75: {"description": "Nieve intensa",                "icon_day": "snow",                             "icon_night": "snow"},
    77: {"description": "Granizo de nieve",             "icon_day": "snow",                             "icon_night": "snow"},
    80: {"description": "Chubascos leves",              "icon_day": "partly-cloudy-day-rain",           "icon_night": "partly-cloudy-night-rain"},
    81: {"description": "Chubascos moderados",          "icon_day": "rain",                             "icon_night": "rain"},
    82: {"description": "Chubascos violentos",          "icon_day": "rain",                             "icon_night": "rain"},
    85: {"description": "Chubascos de nieve",           "icon_day": "snow",                             "icon_night": "snow"},
    86: {"description": "Chubascos de nieve intensos",  "icon_day": "snow",                             "icon_night": "snow"},
    95: {"description": "Tormenta",                     "icon_day": "thunderstorms-day",                "icon_night": "thunderstorms-night"},
    96: {"description": "Tormenta con granizo",         "icon_day": "thunderstorms-day",                "icon_night": "thunderstorms-night"},
    99: {"description": "Tormenta intensa con granizo", "icon_day": "thunderstorms-day",                "icon_night": "thunderstorms-night"},
}


def describe_wmo(code: int | None, is_day: bool = True) -> tuple[str, str]:
    """
    Retorna (description, icon) para un código WMO.
    Fallback a ('Sin datos', 'clear-day') para códigos no mapeados o None.
    """
    if code is None or code not in WMO_CODE_MAP:
        return ("Sin datos", "clear-day")
    entry = WMO_CODE_MAP[code]
    icon_key = "icon_day" if is_day else "icon_night"
    return entry["description"], entry[icon_key]
