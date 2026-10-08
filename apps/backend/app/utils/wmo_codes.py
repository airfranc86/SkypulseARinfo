"""Mapeo WMO weather code → descripción en español + ícono Meteocons."""
from __future__ import annotations

import unicodedata

WMO_CODE_MAP: dict[int, dict[str, str]] = {
    0:  {"description": "Despejado",                    "icon_day": "clear-day",                        "icon_night": "clear-night"},
    1:  {"description": "Mayormente despejado",         "icon_day": "mostly-clear-day",                 "icon_night": "mostly-clear-night"},
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
    96: {"description": "Tormenta con granizo",         "icon_day": "thunderstorms-overcast-hail",      "icon_night": "thunderstorms-overcast-hail"},
    99: {"description": "Tormenta intensa con granizo", "icon_day": "thunderstorms-overcast-hail",      "icon_night": "thunderstorms-overcast-hail"},
}

# Cloud cover (%) borders of the sky: below 25 little, up to 62 (inclusive) partial, above 62 a lot.
# Shared with the daily forecast sky icon (`daily_anchor`), so both read the sky the same way.
CLEAR_BELOW_PCT = 25.0
PARTLY_UP_TO_PCT = 62.0

# Convective codes whose icon depends on the cloud cover: a sunny day can have localized showers,
# storms or hail, so the icon shows the sun when there is little cloud. Each entry holds the icon for
# (little, partial, a lot) of cloud; "{t}" is replaced by "day" or "night". Overcast (3), fog (45,
# 48) and the rest keep their neutral icons; code 1 does not look at the cloud cover either.
_CLOUD_AWARE_ICONS: dict[int, tuple[str, str, str]] = {
    80: ("mostly-clear-{t}-rain", "partly-cloudy-{t}-rain", "rain"),
    81: ("mostly-clear-{t}-rain", "partly-cloudy-{t}-rain", "rain"),
    82: ("mostly-clear-{t}-rain", "partly-cloudy-{t}-rain", "rain"),
    85: ("mostly-clear-{t}-snow", "partly-cloudy-{t}-snow", "snow"),
    86: ("mostly-clear-{t}-snow", "partly-cloudy-{t}-snow", "snow"),
    95: ("thunderstorms-mostly-clear-{t}", "thunderstorms-{t}", "thunderstorms"),
    96: ("thunderstorms-mostly-clear-{t}-hail", "thunderstorms-{t}-hail", "thunderstorms-overcast-hail"),
    99: ("thunderstorms-mostly-clear-{t}-hail", "thunderstorms-{t}-hail", "thunderstorms-overcast-hail"),
}


def _cloud_level(cloud_cover_pct: float) -> int:
    """0 little, 1 partial, 2 a lot of cloud."""
    if cloud_cover_pct < CLEAR_BELOW_PCT:
        return 0
    if cloud_cover_pct <= PARTLY_UP_TO_PCT:
        return 1
    return 2


def _icon_for(code: int, is_day: bool, cloud_cover: float | None) -> str:
    """Icon of a known WMO code: by cloud cover for the convective codes, else the map's icon.

    Without a cloud cover datum the map's icon applies (today's icon).
    """
    cloud_aware = _CLOUD_AWARE_ICONS.get(code)
    if cloud_aware is not None and cloud_cover is not None:
        return cloud_aware[_cloud_level(cloud_cover)].format(t="day" if is_day else "night")
    entry = WMO_CODE_MAP[code]
    return entry["icon_day" if is_day else "icon_night"]


def describe_wmo(
    code: int | None,
    is_day: bool = True,
    cloud_cover: float | None = None,
) -> tuple[str, str]:
    """
    Retorna (description, icon) para un código WMO.
    Fallback contextual: 'clear-day' de día, 'clear-night' de noche.

    `cloud_cover` (%, opcional) afina el ícono de chubascos (80 a 82), chubascos de nieve (85, 86),
    tormenta (95) y tormenta con granizo (96, 99): con poco cielo cubierto se ve el sol. Sin dato
    queda el ícono de siempre. La descripción nunca depende de la nubosidad.
    """
    if code is None or code not in WMO_CODE_MAP:
        fallback_icon = "clear-day" if is_day else "clear-night"
        return ("Sin datos", fallback_icon)
    return WMO_CODE_MAP[code]["description"], _icon_for(code, is_day, cloud_cover)


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
    *,
    rain_confirmed: bool = True,
    cloud_cover: float | None = None,
) -> str:
    """
    Ícono del pronóstico diario. weather_code y precip_prob son campos
    independientes: un día Cubierto (código 3) puede tener prob de lluvia alta.
    En ese caso usamos 'rain' (nube llena con lluvia) en vez del overcast seco.

    Por decisión de producto el override aplica SOLO al código 3; un día
    parcialmente nublado con prob alta conserva su ícono base.

    `rain_confirmed=False` desactiva el override: el pronóstico diario lo pasa en False cuando el
    modelo ancla (ECMWF) no da más de 0,9 mm (FRA-322), así una probabilidad alta sin milímetros
    no pinta lluvia. El valor por defecto conserva el comportamiento anterior.

    `cloud_cover` es la nubosidad media del día (%): afina el ícono base de chubascos, tormenta y
    granizo (ver `describe_wmo`). No toca el override del código 3.
    """
    icon = describe_wmo(code, is_day, cloud_cover)[1]
    if rain_confirmed and code == 3 and precip_prob is not None and precip_prob >= rain_threshold:
        return "rain"
    return icon
