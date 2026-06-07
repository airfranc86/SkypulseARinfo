"""Mapeo WMO weather code → descripción en español + ícono Meteocons."""
from __future__ import annotations

import unicodedata

WMO_CODE_MAP: dict[int, dict[str, str]] = {
    0:  {"description": "Despejado",                    "icon_day": "clear-day",                        "icon_night": "clear-night"},
    1:  {"description": "Mayormente despejado",         "icon_day": "partly-cloudy-day",                "icon_night": "partly-cloudy-night"},
    2:  {"description": "Parcialmente nublado",         "icon_day": "partly-cloudy-day",                "icon_night": "partly-cloudy-night"},
    3:  {"description": "Cubierto",                     "icon_day": "overcast",                         "icon_night": "overcast"},
    45: {"description": "Niebla",                       "icon_day": "fog",                              "icon_night": "fog"},
    48: {"description": "Niebla con escarcha",          "icon_day": "fog",                              "icon_night": "fog"},
    51: {"description": "Llovizna leve",                "icon_day": "overcast-drizzle",                 "icon_night": "overcast-drizzle"},
    53: {"description": "Llovizna moderada",            "icon_day": "overcast-drizzle",                 "icon_night": "overcast-drizzle"},
    55: {"description": "Llovizna intensa",             "icon_day": "overcast-drizzle",                 "icon_night": "overcast-drizzle"},
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
    77: {"description": "Granos de nieve",              "icon_day": "snow",                             "icon_night": "snow"},
    80: {"description": "Chubascos leves",              "icon_day": "partly-cloudy-day-rain",           "icon_night": "partly-cloudy-night-rain"},
    81: {"description": "Chubascos moderados",          "icon_day": "rain",                             "icon_night": "rain"},
    82: {"description": "Chubascos violentos",          "icon_day": "rain",                             "icon_night": "rain"},
    85: {"description": "Chubascos de nieve",           "icon_day": "snow",                             "icon_night": "snow"},
    86: {"description": "Chubascos de nieve intensos",  "icon_day": "snow",                             "icon_night": "snow"},
    95: {"description": "Tormenta",                     "icon_day": "thunderstorms",                    "icon_night": "thunderstorms"},
    96: {"description": "Tormenta con granizo",         "icon_day": "hail",                             "icon_night": "hail"},
    99: {"description": "Tormenta intensa con granizo", "icon_day": "hail",                             "icon_night": "hail"},
}


def describe_wmo(code: int | None, is_day: bool = True) -> tuple[str, str]:
    """
    Retorna (description, icon) para un código WMO.
    Fallback contextual: 'clear-day' de día, 'clear-night' de noche.
    """
    if code is None or code not in WMO_CODE_MAP:
        fallback_icon = "clear-day" if is_day else "clear-night"
        return ("Sin datos", fallback_icon)
    entry = WMO_CODE_MAP[code]
    icon_key = "icon_day" if is_day else "icon_night"
    return entry["description"], entry[icon_key]


def _normalize_es(text: str) -> str:
    """Minúsculas + sin tildes, para matchear texto del SMN de forma robusta."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def icon_from_description_es(text: str | None, is_day: bool = True) -> str | None:
    """
    Deriva un ícono Meteocons desde el texto en español del SMN.

    El SMN entrega una descripción ("Cubierto", "Lluvias", ...) pero NO entrega
    weather_code, por lo que describe_wmo(None) caería al fallback 'clear-day'
    contradiciendo el texto. Este helper traduce el texto al ícono correcto.

    Retorna None cuando ninguna palabra clave matchea (el llamador conserva su
    fallback actual ⇒ cero regresión).
    """
    if not text or not text.strip():
        return None

    t = _normalize_es(text)
    suffix = "day" if is_day else "night"

    # Precipitación (lo más específico primero para evitar falsos positivos).
    # 'thunderstorms' es neutro (rayo sin sol) ⇒ no lleva sufijo day/night.
    if "tormenta" in t:
        return "thunderstorms"
    if "llovizn" in t:
        return "overcast-drizzle"
    if "aguanieve" in t:
        return "sleet"
    if "nieve" in t or "nevad" in t:
        return "snow"
    if any(k in t for k in ("lluvia", "chaparr", "chubasco", "precipit")):
        return "rain"
    # 'fog' es neutro (nube + bruma, sin sol/luna) ⇒ no lleva sufijo day/night.
    if any(k in t for k in ("niebla", "neblina", "bruma")):
        return "fog"

    # Nubosidad ("algo/parcial/ligeramente nublado" antes que "nublado" pleno).
    # 'overcast' es neutro (nube gris, sin sol) ⇒ no lleva sufijo day/night.
    if "cubierto" in t:
        return "overcast"
    if any(k in t for k in ("algo nublado", "parcial", "ligeramente")):
        return f"partly-cloudy-{suffix}"
    if "nublado" in t:
        return "overcast"
    if "despejado" in t or "claro" in t:
        return f"clear-{suffix}"

    return None


def resolve_daily_icon(
    code: int | None,
    precip_prob: float | None,
    is_day: bool = True,
    rain_threshold: float = 60.0,
) -> str:
    """
    Ícono del pronóstico diario. weather_code y precip_prob son campos
    independientes: un día Cubierto (código 3) puede tener prob de lluvia alta.
    En ese caso usamos 'rain' (nube llena con lluvia) en vez del overcast seco.

    Por decisión de producto el override aplica SOLO al código 3; un día
    parcialmente nublado con prob alta conserva su ícono base.
    """
    icon = describe_wmo(code, is_day)[1]
    if code == 3 and precip_prob is not None and precip_prob >= rain_threshold:
        return "rain"
    return icon
