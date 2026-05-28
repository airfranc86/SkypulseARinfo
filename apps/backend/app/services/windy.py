"""Cliente async para la API Windy Point Forecast v2 (modelo GFS de NOAA).

Este servicio es la fuente PRIMARIA de pronósticos en SkyPulse.
Open-Meteo solo se usa como fallback cuando Windy no está configurado o falla.

Exports principales:
    - get_laundry_forecast: 7 días agregados a partir de slots de 3h (uso: tender-ropa).
    - get_hourly_forecast: slots horarios crudos enriquecidos (uso: dashboard, deporte).
    - get_daily_forecast: agregado diario rico (uso: lavar-coche, dashboard).
    - get_temp_850hpa_first: temperatura en 850 hPa del slot horario más reciente
      (uso: cota-de-nieve).
"""
from __future__ import annotations

import asyncio
import logging
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from cachetools import TTLCache

from app.core.config import settings
from app.core.http_client import get_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Excepciones del servicio
# ---------------------------------------------------------------------------

class WindyNotConfiguredError(Exception):
    """Se lanza cuando windy_api_key no está configurada."""


# ---------------------------------------------------------------------------
# Tipos de datos
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LaundryDayRaw:
    """Día agregado para tender-ropa (legacy — mantener firma)."""
    date: str           # "2026-05-20"
    temp_max_c: float
    temp_min_c: float
    humidity_mean: float
    wind_speed_kmh: float
    precip_sum_mm: float
    precip_prob: float
    wind_dir_cardinal: str | None = None


@dataclass(frozen=True)
class WindyHourlyEntry:
    """Un slot horario de Windy GFS para uso general en el dashboard / herramientas."""
    timestamp_ms: int
    timestamp_s: int
    date: str                      # "2026-05-21"
    hour_label: str                # "14:00"
    temp_c: float | None
    humidity: float | None
    wind_speed_kmh: float | None
    wind_gust_kmh: float | None
    wind_dir_deg: float | None
    wind_dir_cardinal: str | None
    precip_3h_mm: float | None
    cloud_cover_pct: float | None  # promedio de lclouds/mclouds/hclouds
    dewpoint_c: float | None
    temp_850_c: float | None       # solo si se solicitó level 850h


@dataclass(frozen=True)
class WindyDailyEntry:
    """Día agregado a partir de slots horarios Windy GFS."""
    date: str
    temp_max_c: float | None
    temp_min_c: float | None
    humidity_mean: float | None
    wind_speed_max_kmh: float | None
    wind_speed_mean_kmh: float | None
    wind_gust_max_kmh: float | None
    wind_dir_cardinal: str | None
    precip_sum_mm: float | None
    precip_prob: float | None       # %, basado en proporción de slots con lluvia
    cloud_cover_mean: float | None


# ---------------------------------------------------------------------------
# Cache + Lock
# ---------------------------------------------------------------------------

# Cache de pronóstico crudo (data tal como llega de Windy). Las funciones
# públicas reutilizan este payload para evitar gastar cuota innecesariamente.
_raw_cache: TTLCache = TTLCache(maxsize=256, ttl=3600)
_cache_lock = asyncio.Lock()
# Eventos para coordinar coroutines concurrentes que piden el mismo cache_key.
# Previene el race condition TOCTOU: dos coroutines miss-check simultáneo → doble fetch.
_fetch_events: dict[tuple[float, float], asyncio.Event] = {}

# Alias legacy retained for backward compatibility with tests/scripts that
# referenced the old in-memory cache.
_forecast_cache: TTLCache = _raw_cache

# Zona horaria Argentina = UTC-3
_AR_TZ = timezone(timedelta(hours=-3))

# Parámetros que se piden a Windy. Se solicitan ambos niveles (surface + 850h)
# en una sola request para evitar duplicar llamadas a la API.
_WINDY_PARAMETERS = [
    "temp", "rh", "wind", "windGust", "precip",
    "lclouds", "mclouds", "hclouds", "dewpoint",
]
_WINDY_LEVELS = ["surface", "850h"]


# ---------------------------------------------------------------------------
# Helpers de conversión
# ---------------------------------------------------------------------------

_CARDINAL_DIRS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO",
]


def _degrees_to_cardinal(deg: float) -> str:
    """Convierte grados meteorológicos (0=N, 90=E) a punto cardinal (16 direcciones)."""
    ix = round(deg / 22.5) % 16
    return _CARDINAL_DIRS[ix]


def _ms_to_kmh(ms: float | None) -> float | None:
    return ms * 3.6 if ms is not None else None


def _k_to_c(k: float | None) -> float | None:
    return k - 273.15 if k is not None else None


def _safe_get(lst: list, idx: int) -> float | None:
    if 0 <= idx < len(lst):
        v = lst[idx]
        return v if v is not None else None
    return None


def _avg(values: list[float]) -> float | None:
    valid = [v for v in values if v is not None]
    if not valid:
        return None
    return sum(valid) / len(valid)


# ---------------------------------------------------------------------------
# Fetch crudo (compartido por todas las funciones públicas)
# ---------------------------------------------------------------------------

async def _fetch_raw(lat: float, lon: float) -> dict:
    """
    Devuelve el payload crudo de Windy para (lat, lon).
    Cachea por (lat, lon) redondeado a 4 decimales durante 1 h.

    Patrón de deduplicación: si dos coroutines solicitan el mismo cache_key
    simultáneamente, solo una hace el fetch; la otra espera via asyncio.Event.

    Raises:
        WindyNotConfiguredError: Si windy_api_key está vacío.
        Exception: Cualquier error de red o HTTP de Windy.
    """
    if not settings.windy_api_key:
        raise WindyNotConfiguredError("windy_api_key no configurada")

    cache_key = (round(lat, 4), round(lon, 4))

    async with _cache_lock:
        if cache_key in _raw_cache:
            logger.debug("Windy cache hit for %s", cache_key)
            return _raw_cache[cache_key]

        if cache_key in _fetch_events:
            # Otra coroutine ya está haciendo el fetch — subscribirse
            event: asyncio.Event | None = _fetch_events[cache_key]
        else:
            # Primera en llegar — registrar intención de fetch
            event = asyncio.Event()
            _fetch_events[cache_key] = event
            event = None  # sentinel: esta coroutine debe hacer el fetch

    if event is not None:
        # Esperar fuera del lock a que la coroutine fetcher termine
        await event.wait()
        async with _cache_lock:
            return _raw_cache[cache_key]

    # Esta coroutine es la responsable del fetch
    try:
        payload = {
            "lat": lat,
            "lon": lon,
            "model": settings.windy_model,
            "parameters": _WINDY_PARAMETERS,
            "levels": _WINDY_LEVELS,
            "key": settings.windy_api_key,
        }

        client = get_client()
        response = await client.post(
            settings.windy_base_url,
            json=payload,
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()

        async with _cache_lock:
            _raw_cache[cache_key] = data
        return data
    finally:
        # Señalar a las coroutines esperando y limpiar el evento
        async with _cache_lock:
            ev = _fetch_events.pop(cache_key, None)
        if ev is not None:
            ev.set()


# ---------------------------------------------------------------------------
# Parser → slots horarios
# ---------------------------------------------------------------------------

def _parse_hourly(data: dict) -> list[WindyHourlyEntry]:
    """Convierte el payload crudo de Windy a una lista ordenada de WindyHourlyEntry."""
    ts_ms_list: list[int] = data.get("ts", [])
    temp_k: list[float | None] = data.get("temp-surface", [])
    rh: list[float | None] = data.get("rh-surface", [])
    wind_u: list[float | None] = data.get("wind_u-surface", [])
    wind_v: list[float | None] = data.get("wind_v-surface", [])
    gust_ms: list[float | None] = data.get("gust-surface", []) or data.get("windGust-surface", [])
    precip: list[float | None] = data.get("past3hprecip-surface", [])
    lclouds: list[float | None] = data.get("lclouds-surface", [])
    mclouds: list[float | None] = data.get("mclouds-surface", [])
    hclouds: list[float | None] = data.get("hclouds-surface", [])
    dew_k: list[float | None] = data.get("dewpoint-surface", [])
    temp_850_k: list[float | None] = data.get("temp-850h", [])

    entries: list[WindyHourlyEntry] = []
    for i, ts_ms in enumerate(ts_ms_list):
        dt_ar = datetime.fromtimestamp(ts_ms / 1000.0, tz=_AR_TZ)
        date_str = dt_ar.strftime("%Y-%m-%d")
        hour_label = dt_ar.strftime("%H:%M")

        u = _safe_get(wind_u, i)
        v = _safe_get(wind_v, i)
        wind_speed_kmh: float | None = None
        wind_dir_deg: float | None = None
        wind_dir_cardinal: str | None = None
        if u is not None and v is not None:
            speed_ms = math.sqrt(u * u + v * v)
            wind_speed_kmh = round(speed_ms * 3.6, 2)
            # Dirección de origen (de dónde viene el viento)
            wind_dir_deg = math.degrees(math.atan2(-u, -v)) % 360
            wind_dir_cardinal = _degrees_to_cardinal(wind_dir_deg)

        clouds = [c for c in (
            _safe_get(lclouds, i),
            _safe_get(mclouds, i),
            _safe_get(hclouds, i),
        ) if c is not None]
        cloud_cover_pct = (sum(clouds) / len(clouds)) if clouds else None

        entries.append(
            WindyHourlyEntry(
                timestamp_ms=int(ts_ms),
                timestamp_s=int(ts_ms // 1000),
                date=date_str,
                hour_label=hour_label,
                temp_c=_k_to_c(_safe_get(temp_k, i)),
                humidity=_safe_get(rh, i),
                wind_speed_kmh=wind_speed_kmh,
                wind_gust_kmh=_ms_to_kmh(_safe_get(gust_ms, i)),
                wind_dir_deg=wind_dir_deg,
                wind_dir_cardinal=wind_dir_cardinal,
                precip_3h_mm=_safe_get(precip, i),
                cloud_cover_pct=cloud_cover_pct,
                dewpoint_c=_k_to_c(_safe_get(dew_k, i)),
                temp_850_c=_k_to_c(_safe_get(temp_850_k, i)),
            )
        )

    return entries


# ---------------------------------------------------------------------------
# Función pública: pronóstico horario
# ---------------------------------------------------------------------------

async def get_hourly_forecast(lat: float, lon: float) -> list[WindyHourlyEntry]:
    """
    Pronóstico horario desde Windy GFS.
    Cada entrada cubre típicamente 3 h (resolución nativa de GFS en Windy).

    Raises:
        WindyNotConfiguredError: si windy_api_key está vacío.
        Exception: ante cualquier error de red o HTTP.
    """
    data = await _fetch_raw(lat, lon)
    return _parse_hourly(data)


# ---------------------------------------------------------------------------
# Función pública: pronóstico diario agregado
# ---------------------------------------------------------------------------

async def get_daily_forecast(lat: float, lon: float, days: int = 7) -> list[WindyDailyEntry]:
    """
    Pronóstico diario agregado a partir de slots horarios.
    Agrupa por fecha local AR (UTC-3) y devuelve hasta `days` días.

    Raises:
        WindyNotConfiguredError: si windy_api_key está vacío.
        Exception: ante cualquier error de red o HTTP.
    """
    hourly = await get_hourly_forecast(lat, lon)

    # Agrupar por fecha local
    by_date: dict[str, list[WindyHourlyEntry]] = defaultdict(list)
    for h in hourly:
        by_date[h.date].append(h)

    sorted_dates = sorted(by_date.keys())[:days]
    result: list[WindyDailyEntry] = []

    for date_str in sorted_dates:
        slots = by_date[date_str]

        temps = [s.temp_c for s in slots if s.temp_c is not None]
        hums = [s.humidity for s in slots if s.humidity is not None]
        wind_speeds = [s.wind_speed_kmh for s in slots if s.wind_speed_kmh is not None]
        gusts = [s.wind_gust_kmh for s in slots if s.wind_gust_kmh is not None]
        precips = [s.precip_3h_mm for s in slots if s.precip_3h_mm is not None]
        clouds = [s.cloud_cover_pct for s in slots if s.cloud_cover_pct is not None]

        # Dirección media del viento — vector mean sobre cos/sin
        wind_dir_cardinal: str | None = None
        dir_vectors = [s.wind_dir_deg for s in slots if s.wind_dir_deg is not None]
        if dir_vectors:
            sin_sum = sum(math.sin(math.radians(d)) for d in dir_vectors)
            cos_sum = sum(math.cos(math.radians(d)) for d in dir_vectors)
            mean_deg = math.degrees(math.atan2(sin_sum, cos_sum)) % 360
            wind_dir_cardinal = _degrees_to_cardinal(mean_deg)

        # Probabilidad de lluvia: % de slots con precipitación notable
        n_total = len(slots) or 1
        n_rainy = sum(1 for p in precips if p > 0.1)
        precip_prob = (n_rainy / n_total) * 100.0 if precips else None

        result.append(
            WindyDailyEntry(
                date=date_str,
                temp_max_c=round(max(temps), 2) if temps else None,
                temp_min_c=round(min(temps), 2) if temps else None,
                humidity_mean=round(sum(hums) / len(hums), 2) if hums else None,
                wind_speed_max_kmh=round(max(wind_speeds), 2) if wind_speeds else None,
                wind_speed_mean_kmh=round(sum(wind_speeds) / len(wind_speeds), 2) if wind_speeds else None,
                wind_gust_max_kmh=round(max(gusts), 2) if gusts else None,
                wind_dir_cardinal=wind_dir_cardinal,
                precip_sum_mm=round(sum(precips), 2) if precips else None,
                precip_prob=round(precip_prob, 2) if precip_prob is not None else None,
                cloud_cover_mean=round(sum(clouds) / len(clouds), 2) if clouds else None,
            )
        )

    return result


# ---------------------------------------------------------------------------
# Función pública: temp en 850 hPa más reciente (cota de nieve)
# ---------------------------------------------------------------------------

async def get_temp_850hpa_first(lat: float, lon: float) -> float | None:
    """
    Devuelve la temperatura en 850 hPa (°C) del slot horario más cercano al presente.

    Útil para `compute_cota_de_nieve` que actualmente solo necesita un valor puntual.

    Raises:
        WindyNotConfiguredError: si windy_api_key está vacío.
        Exception: ante cualquier error de red o HTTP.
    """
    hourly = await get_hourly_forecast(lat, lon)
    for h in hourly:
        if h.temp_850_c is not None:
            return h.temp_850_c
    return None


# ---------------------------------------------------------------------------
# Función pública: laundry forecast (legacy, mantener firma)
# ---------------------------------------------------------------------------

async def get_laundry_forecast(lat: float, lon: float) -> list[LaundryDayRaw]:
    """
    Pronóstico de 7 días desde Windy GFS, agregado a una estructura específica
    para tender-ropa. Implementado encima de `get_daily_forecast` para reutilizar
    el cache y consolidar la lógica de agregación.

    Raises:
        WindyNotConfiguredError: si windy_api_key está vacío.
    """
    daily = await get_daily_forecast(lat, lon, days=7)

    result: list[LaundryDayRaw] = []
    for d in daily:
        result.append(
            LaundryDayRaw(
                date=d.date,
                temp_max_c=d.temp_max_c if d.temp_max_c is not None else 0.0,
                temp_min_c=d.temp_min_c if d.temp_min_c is not None else 0.0,
                humidity_mean=d.humidity_mean if d.humidity_mean is not None else 0.0,
                wind_speed_kmh=d.wind_speed_mean_kmh if d.wind_speed_mean_kmh is not None else 0.0,
                precip_sum_mm=d.precip_sum_mm if d.precip_sum_mm is not None else 0.0,
                precip_prob=d.precip_prob if d.precip_prob is not None else 0.0,
                wind_dir_cardinal=d.wind_dir_cardinal,
            )
        )

    return result


# ---------------------------------------------------------------------------
# Helpers legacy (sync) — preservados para tests unitarios
# ---------------------------------------------------------------------------

def _aggregate_to_daily(data: dict) -> list[LaundryDayRaw]:
    """
    Versión sincrónica del agregador. Convierte el payload crudo de Windy en
    una lista de LaundryDayRaw replicando exactamente la lógica anterior.

    Mantenida para tests unitarios que validan el comportamiento del agregador
    sin tener que mockear el cliente HTTP completo.
    """
    ts_ms_list: list[int] = data.get("ts", [])
    temp_k_list: list[float] = data.get("temp-surface", [])
    rh_list: list[float] = data.get("rh-surface", [])
    wind_u_list: list[float] = data.get("wind_u-surface", [])
    wind_v_list: list[float] = data.get("wind_v-surface", [])
    precip_list: list[float] = data.get("past3hprecip-surface", [])

    daily: dict[str, dict] = defaultdict(lambda: {
        "temps_k": [],
        "rh": [],
        "wind_speeds": [],
        "wind_u": [],
        "wind_v": [],
        "precip": [],
        "n": 0,
    })

    for i, ts_ms in enumerate(ts_ms_list):
        dt_ar = datetime.fromtimestamp(ts_ms / 1000.0, tz=_AR_TZ)
        date_str = dt_ar.strftime("%Y-%m-%d")
        bucket = daily[date_str]

        temp_k = temp_k_list[i] if i < len(temp_k_list) else None
        if temp_k is not None:
            bucket["temps_k"].append(temp_k)

        rh = rh_list[i] if i < len(rh_list) else None
        if rh is not None:
            bucket["rh"].append(rh)

        u = wind_u_list[i] if i < len(wind_u_list) else None
        v = wind_v_list[i] if i < len(wind_v_list) else None
        if u is not None and v is not None:
            speed_ms = math.sqrt(u ** 2 + v ** 2)
            bucket["wind_speeds"].append(speed_ms)
            bucket["wind_u"].append(u)
            bucket["wind_v"].append(v)

        precip = precip_list[i] if i < len(precip_list) else None
        if precip is not None:
            bucket["precip"].append(precip)

        bucket["n"] += 1

    sorted_dates = sorted(daily.keys())[:7]

    result: list[LaundryDayRaw] = []
    for date_str in sorted_dates:
        b = daily[date_str]

        temps_c = [k - 273.15 for k in b["temps_k"]]
        temp_max_c = max(temps_c) if temps_c else 0.0
        temp_min_c = min(temps_c) if temps_c else 0.0

        humidity_mean = (sum(b["rh"]) / len(b["rh"])) if b["rh"] else 0.0

        wind_speed_kmh = (
            (sum(b["wind_speeds"]) / len(b["wind_speeds"])) * 3.6
            if b["wind_speeds"]
            else 0.0
        )

        wind_dir_cardinal: str | None = None
        if b["wind_u"] and b["wind_v"]:
            mean_u = sum(b["wind_u"]) / len(b["wind_u"])
            mean_v = sum(b["wind_v"]) / len(b["wind_v"])
            deg = math.degrees(math.atan2(-mean_u, -mean_v)) % 360
            wind_dir_cardinal = _degrees_to_cardinal(deg)

        precip_sum_mm = sum(b["precip"])
        n_total = b["n"] if b["n"] > 0 else 1
        n_rainy = sum(1 for p in b["precip"] if p > 0.1)
        precip_prob = (n_rainy / n_total) * 100.0

        result.append(
            LaundryDayRaw(
                date=date_str,
                temp_max_c=round(temp_max_c, 2),
                temp_min_c=round(temp_min_c, 2),
                humidity_mean=round(humidity_mean, 2),
                wind_speed_kmh=round(wind_speed_kmh, 2),
                precip_sum_mm=round(precip_sum_mm, 2),
                precip_prob=round(precip_prob, 2),
                wind_dir_cardinal=wind_dir_cardinal,
            )
        )

    return result


async def _fetch_and_aggregate(lat: float, lon: float) -> list[LaundryDayRaw]:
    """Legacy: realiza el POST a Windy y agrega los datos horarios a diarios."""
    data = await _fetch_raw(lat, lon)
    return _aggregate_to_daily(data)
