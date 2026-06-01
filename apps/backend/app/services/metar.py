"""Cliente METAR/TAF via Aviation Weather Center (aviationweather.gov).

METAR  → visibilidad actual (dato real de aeropuerto).
TAF    → pronóstico horario 24-30h (emitido por meteorólogos de aviación).

Endpoints:
  METAR: GET https://aviationweather.gov/api/data/metar?ids=SAEZ&format=json&hours=2
  TAF:   GET https://aviationweather.gov/api/data/taf?ids=SAEZ&format=json&hours=24

Sin API key requerida.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cachetools import TTLCache

from app.core.config import settings
from app.core.http_client import get_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SM_TO_M    = 1609.344    # statute miles → metros
_MAX_VIS_M  = 10_000.0    # cap de visibilidad en metros (consistente con OM)
# Argentina time zone offset (no DST)
_AR_TZ = timezone(timedelta(hours=-3))

AWC_METAR_BASE = "https://aviationweather.gov/api/data/metar"
AWC_TAF_BASE   = "https://aviationweather.gov/api/data/taf"

# ---------------------------------------------------------------------------
# Aeropuertos argentinos con coordenadas
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Airport:
    icao: str
    name: str
    lat: float
    lon: float


_AR_AIRPORTS: list[_Airport] = [
    _Airport("SAEZ", "Ezeiza",             -34.822, -58.536),
    _Airport("SABE", "Aeroparque",         -34.559, -58.416),
    _Airport("SACO", "Córdoba",            -31.323, -64.208),
    _Airport("SAME", "Mendoza",            -32.832, -68.793),
    _Airport("SARS", "Rosario",            -32.919, -60.785),
    _Airport("SANT", "Tucumán",            -26.841, -65.105),
    _Airport("SASA", "Salta",              -24.856, -65.486),
    _Airport("SASJ", "San Juan",           -31.572, -68.418),
    _Airport("SAVB", "Bariloche",          -41.151, -71.157),
    _Airport("SAWC", "Comodoro Rivadavia", -45.785, -67.499),
    _Airport("SAWG", "Río Gallegos",       -51.609, -69.313),
    _Airport("SAWO", "Neuquén",            -38.949, -68.156),
    _Airport("SAWH", "Ushuaia",            -54.843, -68.295),
    _Airport("SAAC", "Concordia",         -31.297, -57.997),
    _Airport("SAAG", "Gualeguaychú",      -33.011, -58.611),
    _Airport("SAZR", "Santa Rosa",        -36.588, -64.276),
    _Airport("SAVT", "Viedma",            -40.869, -63.000),
    _Airport("SAWP", "Malargüe",          -35.493, -69.574),
    _Airport("SAMR", "San Rafael",        -34.588, -68.404),
    _Airport("SAZM", "Mar del Plata",     -37.934, -57.573),
]

# ---------------------------------------------------------------------------
# Caches
# TTL 30 min para METAR (se actualiza cada 30-60 min)
# TTL 60 min para TAF   (se enmienda con menos frecuencia)
# NO se cachea None en errores — permite reintentos en la próxima request
# ---------------------------------------------------------------------------

_metar_cache: TTLCache[str, float]        = TTLCache(maxsize=64, ttl=1800)
_taf_cache:   TTLCache[str, list[dict]]   = TTLCache(maxsize=32, ttl=3600)

# Fenómenos de niebla reconocidos en TAF/METAR (WMO / ICAO)
_FOG_WX_CODES: frozenset[str] = frozenset({"FG", "MIFG", "BCFG", "FZFG", "BR"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en km entre dos coordenadas (Haversine)."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def nearest_airport(lat: float, lon: float) -> _Airport:
    """Retorna el aeropuerto argentino más cercano a (lat, lon)."""
    return min(_AR_AIRPORTS, key=lambda a: _haversine_km(lat, lon, a.lat, a.lon))


def _parse_taf_visib_sm(visib: object) -> float | None:
    """
    Convierte el campo `visib` de un TAF a statute miles.

    Formatos reconocidos:
      - numérico:  6, 3.0, 0.5
      - string:   "6SM", "P6SM", "1/2SM", "1 1/2SM", "6+", "3/4"
    """
    if visib is None:
        return None
    # Intento directo (int/float)
    try:
        return float(visib)
    except (TypeError, ValueError):
        pass
    s = str(visib).strip().upper()
    s = s.replace("SM", "").replace("+", "").strip()
    if s.startswith("P"):
        s = s[1:].strip()
    # Número mixto: "1 1/2" → 1.5
    parts = s.split()
    total = 0.0
    for part in parts:
        if "/" in part:
            try:
                n, d = part.split("/", 1)
                total += float(n) / float(d)
            except (ValueError, ZeroDivisionError):
                return None
        else:
            try:
                total += float(part)
            except ValueError:
                return None
    return total if total > 0 else None


# ---------------------------------------------------------------------------
# METAR — visibilidad actual
# ---------------------------------------------------------------------------

async def get_metar_visibility(icao: str) -> float | None:
    """
    Visibilidad actual (metros) del METAR de un aeropuerto.

    - Fuente: AWC, sin API key.
    - Retorna None si el fetch falla o no hay dato.
    - Solo cachea resultados EXITOSOS — los errores permiten reintento.
    - Cap a 10 km (consistente con el resto del sistema).
    """
    if icao in _metar_cache:
        logger.debug("METAR cache hit: %s → %.0f m", icao, _metar_cache[icao])
        return _metar_cache[icao]

    try:
        client = get_client()
        response = await client.get(
            AWC_METAR_BASE,
            params={"ids": icao, "format": "json", "hours": "2"},
            timeout=settings.metar_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        # NO cacheamos None — el próximo request reintentará
        logger.warning("METAR fetch failed for %s: %s", icao, exc)
        return None

    if not isinstance(data, list) or len(data) == 0:
        logger.info("METAR: no data for %s", icao)
        return None

    entry = data[0]
    visib_sm = entry.get("visib")
    if visib_sm is None:
        logger.info("METAR: no visib field for %s", icao)
        return None

    try:
        vis_m = float(visib_sm) * _SM_TO_M
    except (TypeError, ValueError):
        return None

    vis_m = min(vis_m, _MAX_VIS_M)
    logger.info(
        "METAR %s: %.2f SM → %.0f m (obs: %s)",
        icao, float(visib_sm), vis_m, entry.get("obsTime", "?"),
    )
    _metar_cache[icao] = vis_m   # solo cacheamos éxitos
    return vis_m


@dataclass(frozen=True)
class MetarVisibility:
    """Resultado de una consulta METAR de visibilidad."""
    visibility_m: float | None
    icao: str
    station_name: str
    distance_km: float
    observed_at: datetime | None


async def get_nearest_metar_visibility(lat: float, lon: float) -> MetarVisibility:
    """
    Visibilidad METAR del aeropuerto más cercano.
    Siempre retorna un objeto; `visibility_m` puede ser None.
    """
    airport = nearest_airport(lat, lon)
    dist_km = _haversine_km(lat, lon, airport.lat, airport.lon)
    vis_m = await get_metar_visibility(airport.icao)

    return MetarVisibility(
        visibility_m=vis_m,
        icao=airport.icao,
        station_name=airport.name,
        distance_km=round(dist_km, 1),
        observed_at=datetime.now(timezone.utc) if vis_m is not None else None,
    )


# ---------------------------------------------------------------------------
# TAF — pronóstico horario de visibilidad
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TafHourlySlot:
    """Slot horario derivado de un TAF."""
    hour_label: str       # "14:00" en hora local AR (UTC-3)
    visibility_m: float | None
    fog_probable: bool    # True si wx incluye FG/MIFG/BCFG/FZFG


async def get_taf_for_icao(icao: str) -> list[dict] | None:
    """
    Fetch los períodos TAF (fcsts) de un aeropuerto.

    - Solo cachea resultados con al menos un período válido.
    - Errores NO se cachean (permiten reintento).
    """
    if icao in _taf_cache:
        logger.debug("TAF cache hit: %s (%d periods)", icao, len(_taf_cache[icao]))
        return _taf_cache[icao]

    try:
        client = get_client()
        response = await client.get(
            AWC_TAF_BASE,
            params={"ids": icao, "format": "json", "hours": "24"},
            timeout=settings.metar_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning("TAF fetch failed for %s: %s", icao, exc)
        return None

    if not isinstance(data, list) or len(data) == 0:
        logger.info("TAF: no data for %s", icao)
        return None

    entry = data[0]
    fcsts: list[dict] = entry.get("fcsts") or []
    if not fcsts:
        logger.info("TAF: no fcsts for %s", icao)
        return None

    _taf_cache[icao] = fcsts
    logger.info("TAF %s: %d forecast periods cached", icao, len(fcsts))
    return fcsts


async def get_nearest_taf_hourly(
    lat: float,
    lon: float,
    hours: int = 12,
) -> list[TafHourlySlot] | None:
    """
    Pronóstico horario de visibilidad para las próximas `hours` horas
    basado en el TAF del aeropuerto más cercano.

    Retorna None si el TAF no está disponible o no tiene datos de visibilidad.
    """
    airport = nearest_airport(lat, lon)
    fcsts = await get_taf_for_icao(airport.icao)
    if not fcsts:
        return None

    # Empezar desde la próxima hora AR redonda (ej. 02:00, 03:00…).
    # Esto separa visualmente "ahora" (METAR / línea 'Ahora') del
    # pronóstico futuro (barras TAF) y evita etiquetas con minutos exactos.
    now_ar   = datetime.now(_AR_TZ)
    start_ar = now_ar.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

    slots: list[TafHourlySlot] = []

    for h in range(hours):
        target_dt = start_ar + timedelta(hours=h)
        target_ts = target_dt.timestamp()
        hour_label = target_dt.strftime("%H:%M")

        # Buscar período(s) TAF que cubran este timestamp.
        # Si varios se solapan (TEMPO sobre FM), usamos la visibilidad más baja.
        best_vis_m: float | None = None
        fog_probable = False
        any_period_found = False

        for period in fcsts:
            try:
                tf = float(period.get("timeFrom") or 0)
                tt = float(period.get("timeTo")   or 0)
            except (TypeError, ValueError):
                continue

            if not (tf <= target_ts < tt):
                continue

            any_period_found = True

            visib_sm = _parse_taf_visib_sm(period.get("visib"))
            if visib_sm is not None:
                vis_m = min(visib_sm * _SM_TO_M, _MAX_VIS_M)
                # Conservador: tomar la visibilidad más baja entre períodos solapados
                if best_vis_m is None or vis_m < best_vis_m:
                    best_vis_m = vis_m

            # Fenómenos de niebla en wxList
            wx_list: list = period.get("wxList") or []
            for wx_item in wx_list:
                wx_code = (
                    wx_item.get("wx", "") if isinstance(wx_item, dict) else str(wx_item)
                )
                if wx_code.upper() in _FOG_WX_CODES:
                    fog_probable = True
                    break

        slots.append(TafHourlySlot(
            hour_label=hour_label,
            visibility_m=best_vis_m if any_period_found else None,
            fog_probable=fog_probable,
        ))

    # Si ningún slot tiene visibilidad, el TAF no tiene datos útiles
    if all(s.visibility_m is None for s in slots):
        logger.info(
            "TAF %s: no visibility data across %d slots — returning None",
            airport.icao, hours,
        )
        return None

    return slots
