"""Cliente METAR/TAF via Aviation Weather Center (aviationweather.gov).

METAR  → visibilidad actual (dato real de aeropuerto).
TAF    → pronóstico horario 24-30h (emitido por meteorólogos de aviación).

Endpoints:
  METAR: GET https://aviationweather.gov/api/data/metar?ids=SAEZ&format=json&hours=2
  TAF:   GET https://aviationweather.gov/api/data/taf?ids=SAEZ&format=json
         (sin `hours`: AWC responde HTTP 400 si se lo manda; el TAF ya trae su vigencia)

Sin API key requerida.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cachetools import TTLCache

from app.core import usage_counter
from app.core.config import settings
from app.core.http_client import get_client
from app.services.reportes_aeronauticos.aeropuertos import (
    nearest_airport,
    nearest_airport_with_distance,
)
from app.services.visibilidad import awc_visibility_m
from app.utils.parsing import parse_float

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Argentina time zone offset (no DST)
_AR_TZ = timezone(timedelta(hours=-3))

AWC_METAR_BASE = "https://aviationweather.gov/api/data/metar"
AWC_TAF_BASE   = "https://aviationweather.gov/api/data/taf"

# ---------------------------------------------------------------------------
# Caches
# TTL 30 min para METAR (se actualiza cada 30-60 min)
# TTL 60 min para TAF   (se enmienda con menos frecuencia)
# NO se cachea None en errores — permite reintentos en la próxima request
# El METAR se cachea junto con su hora de observación: la antigüedad se verifica en cada lectura.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _MetarReading:
    """Visibilidad de un METAR y la hora (UTC) en que se observó."""
    visibility_m: float
    observed_at: datetime


_metar_cache: TTLCache[str, _MetarReading] = TTLCache(maxsize=64, ttl=1800)
_taf_cache:   TTLCache[str, dict]         = TTLCache(maxsize=32, ttl=3600)  # entrada completa de AWC

# Fenómenos de niebla reconocidos en TAF/METAR (WMO / ICAO)
_FOG_WX_CODES: frozenset[str] = frozenset({"FG", "MIFG", "BCFG", "FZFG", "BR"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_fog(wx_string: object) -> bool:
    """True si el `wxString` de AWC ("-RA BR", "+TSRA FG") trae algún fenómeno de niebla.

    Compara cada código completo, sin el prefijo de intensidad (+/-): "BRAND" no cuenta.
    """
    if not isinstance(wx_string, str):
        return False
    return any(code.lstrip("+-") in _FOG_WX_CODES for code in wx_string.upper().split())


# ---------------------------------------------------------------------------
# METAR — visibilidad actual
# ---------------------------------------------------------------------------

def _obs_time(entry: dict) -> datetime | None:
    """Hora de observación (UTC) del `obsTime` de AWC (epoch s); None si falta o no es válida."""
    seconds = parse_float(entry.get("obsTime"))
    if seconds is None or not math.isfinite(seconds):
        return None
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _is_recent(observed_at: datetime, now: datetime) -> bool:
    """True si el reporte no supera `settings.metar_max_age_minutes` (inclusivo: 90 min todavía pasa)."""
    return now - observed_at <= timedelta(minutes=settings.metar_max_age_minutes)


async def _get_metar_reading(icao: str, now: datetime) -> _MetarReading | None:
    """
    Último METAR utilizable de un aeropuerto: visibilidad (m) y hora de observación.

    - Fuente: AWC, sin API key.
    - Descarta (None) un reporte sin `obsTime` válido o más viejo que `settings.metar_max_age_minutes`.
      La antigüedad se verifica en cada lectura, también cuando el dato sale de la caché.
    - Solo cachea resultados EXITOSOS y vigentes — los errores y los reportes viejos permiten reintento.
    - Cap a 10 km (consistente con el resto del sistema).
    """
    cached = _metar_cache.get(icao)
    if cached is not None:
        if _is_recent(cached.observed_at, now):
            logger.debug("METAR cache hit: %s → %.0f m", icao, cached.visibility_m)
            return cached
        # Vencido desde que se cacheó: se descarta y se consulta de nuevo a AWC.
        _metar_cache.pop(icao, None)
        logger.info("METAR %s: cached report too old (%s) — refetching", icao, cached.observed_at)

    try:
        client = get_client()
        usage_counter.record("metar_awc")
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

    if not isinstance(data, list) or len(data) == 0 or not isinstance(data[0], dict):
        logger.info("METAR: no data for %s", icao)
        return None

    entry = data[0]
    visib_sm = entry.get("visib")
    if visib_sm is None:
        logger.info("METAR: no visib field for %s", icao)
        return None

    vis_m = awc_visibility_m(visib_sm)
    if vis_m is None:
        logger.info("METAR: unparseable visib %r for %s", visib_sm, icao)
        return None

    observed_at = _obs_time(entry)
    if observed_at is None:
        logger.info("METAR: no valid obsTime for %s — discarded", icao)
        return None
    if not _is_recent(observed_at, now):
        logger.info("METAR: report of %s too old (%s) — discarded", icao, observed_at)
        return None

    logger.info("METAR %s: visib %r → %.0f m (obs: %s)", icao, visib_sm, vis_m, observed_at)
    reading = _MetarReading(visibility_m=vis_m, observed_at=observed_at)
    _metar_cache[icao] = reading   # solo cacheamos éxitos vigentes
    return reading


async def get_metar_visibility(icao: str, now: datetime | None = None) -> float | None:
    """
    Visibilidad actual (metros) del METAR de un aeropuerto, o None si no hay dato utilizable
    (fetch fallido, sin `obsTime` válido o reporte de más de `settings.metar_max_age_minutes`).
    """
    reading = await _get_metar_reading(icao, now or datetime.now(timezone.utc))
    return reading.visibility_m if reading else None


@dataclass(frozen=True)
class MetarVisibility:
    """Resultado de una consulta METAR de visibilidad."""
    visibility_m: float | None
    icao: str
    station_name: str
    distance_km: float
    observed_at: datetime | None   # hora real de observación del METAR (UTC); None si se descartó


async def get_nearest_metar_visibility(
    lat: float, lon: float, now: datetime | None = None
) -> MetarVisibility:
    """
    Visibilidad METAR del aeropuerto más cercano.

    Siempre retorna un objeto; `visibility_m` es None si el aeropuerto está a más de
    `settings.metar_max_distance_km` (no se llama a AWC) o si el METAR no es utilizable o es viejo
    (ver `_get_metar_reading`). La estación y la distancia se informan igual.
    """
    now = now or datetime.now(timezone.utc)
    airport, dist_km = nearest_airport_with_distance(lat, lon)
    reading: _MetarReading | None = None
    if dist_km > settings.metar_max_distance_km:
        logger.info(
            "METAR %s not used: %.1f km > %.1f km", airport.icao, dist_km, settings.metar_max_distance_km
        )
    else:
        reading = await _get_metar_reading(airport.icao, now)

    return MetarVisibility(
        visibility_m=reading.visibility_m if reading else None,
        icao=airport.icao,
        station_name=airport.name,
        distance_km=round(dist_km, 1),
        observed_at=reading.observed_at if reading else None,
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


class TafFetchError(Exception):
    """AWC no respondió con un TAF utilizable (red, HTTP de error o JSON inválido)."""


async def fetch_taf_entry(icao: str) -> dict | None:
    """
    Entrada completa del TAF de AWC (texto crudo, vigencia y períodos `fcsts`).

    - Devuelve None si AWC respondió pero el aeropuerto no tiene TAF (no es un error).
    - Lanza `TafFetchError` si AWC falló: así la ruta distingue "no hay TAF" (404) de
      "no pudimos consultarlo" (503).
    - Solo cachea entradas con al menos un período; los errores NO se cachean.
    """
    cached = _taf_cache.get(icao)
    if cached is not None:
        logger.debug("TAF cache hit: %s", icao)
        return cached

    try:
        client = get_client()
        usage_counter.record("metar_awc")
        response = await client.get(
            AWC_TAF_BASE,
            params={"ids": icao, "format": "json"},
            timeout=settings.metar_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        raise TafFetchError(f"{type(exc).__name__}: {exc}") from exc

    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        logger.info("TAF: no data for %s", icao)
        return None

    entry = data[0]
    if not entry.get("fcsts"):
        logger.info("TAF: no fcsts for %s", icao)
        return None

    _taf_cache[icao] = entry
    logger.info("TAF %s: %d forecast periods cached", icao, len(entry["fcsts"]))
    return entry


async def get_taf_for_icao(icao: str) -> list[dict] | None:
    """
    Períodos TAF (fcsts) de un aeropuerto, para el pronóstico horario de Niebla.

    Versión tolerante: cualquier error devuelve None (el llamador cae a otra fuente).
    """
    try:
        entry = await fetch_taf_entry(icao)
    except TafFetchError as exc:
        logger.warning("TAF fetch failed for %s: %s", icao, exc)
        return None
    return entry["fcsts"] if entry else None


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

            # "6+" (6 millas o más) vale el tope de 10 km, no 6 SM = 9.656 m.
            vis_m = awc_visibility_m(period.get("visib"))
            if vis_m is not None:
                # Conservador: tomar la visibilidad más baja entre períodos solapados
                if best_vis_m is None or vis_m < best_vis_m:
                    best_vis_m = vis_m

            # Fenómenos de niebla en `wxString` ("-RA BR"); AWC no manda `wxList`.
            if _has_fog(period.get("wxString")):
                fog_probable = True

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
