"""Cliente async para la API Windy Point Forecast v2."""
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
    date: str           # "2026-05-20"
    temp_max_c: float
    temp_min_c: float
    humidity_mean: float
    wind_speed_kmh: float
    precip_sum_mm: float
    precip_prob: float
    wind_dir_cardinal: str | None = None


# ---------------------------------------------------------------------------
# Cache + Lock
# ---------------------------------------------------------------------------

_forecast_cache: TTLCache = TTLCache(maxsize=256, ttl=3600)
_cache_lock = asyncio.Lock()

# Zona horaria Argentina = UTC-3
_AR_TZ = timezone(timedelta(hours=-3))


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

async def get_laundry_forecast(lat: float, lon: float) -> list[LaundryDayRaw]:
    """
    Obtiene pronóstico de 7 días desde Windy ECMWF para (lat, lon).
    Retorna lista de LaundryDayRaw, uno por día (día 0 = hoy en UTC-3).

    Raises:
        WindyNotConfiguredError: Si windy_api_key está vacío.
    """
    if not settings.windy_api_key:
        raise WindyNotConfiguredError("windy_api_key no configurada")

    cache_key = (round(lat, 4), round(lon, 4))

    async with _cache_lock:
        if cache_key in _forecast_cache:
            logger.debug("Windy cache hit for %s", cache_key)
            return _forecast_cache[cache_key]

    result = await _fetch_and_aggregate(lat, lon)

    async with _cache_lock:
        _forecast_cache[cache_key] = result

    return result


async def _fetch_and_aggregate(lat: float, lon: float) -> list[LaundryDayRaw]:
    """Realiza el POST a Windy y agrega los datos horarios a diarios."""
    payload = {
        "lat": lat,
        "lon": lon,
        "model": "gfs",        # ecmwf requiere plan pago — gfs disponible en plan gratuito
        "parameters": ["temp", "rh", "wind", "precip"],  # "wind" retorna wind_u + wind_v; "precip" → past3hprecip-surface
        "levels": ["surface"],
        "key": settings.windy_api_key,
    }

    try:
        client = get_client()
        response = await client.post(
            settings.windy_base_url,
            json=payload,
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning("Windy fetch failed: %s", exc)
        raise

    return _aggregate_to_daily(data)


_CARDINAL_DIRS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO",
]


def _degrees_to_cardinal(deg: float) -> str:
    """Convierte grados meteorológicos (0=N, 90=E) a punto cardinal (16 direcciones)."""
    ix = round(deg / 22.5) % 16
    return _CARDINAL_DIRS[ix]


def _aggregate_to_daily(data: dict) -> list[LaundryDayRaw]:
    """
    Agrupa arrays horarios de Windy por fecha local (UTC-3) y calcula métricas diarias.
    """
    ts_ms_list: list[int] = data.get("ts", [])
    temp_k_list: list[float] = data.get("temp-surface", [])
    rh_list: list[float] = data.get("rh-surface", [])
    wind_u_list: list[float] = data.get("wind_u-surface", [])
    wind_v_list: list[float] = data.get("wind_v-surface", [])
    precip_list: list[float] = data.get("past3hprecip-surface", [])

    # Estructura: date_str -> lista de valores horarios
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

    # Ordenar fechas y tomar máximo 7 días
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

        # Dirección media del viento: vector medio de u/v → atan2 → cardinal
        wind_dir_cardinal: str | None = None
        if b["wind_u"] and b["wind_v"]:
            mean_u = sum(b["wind_u"]) / len(b["wind_u"])
            mean_v = sum(b["wind_v"]) / len(b["wind_v"])
            # Convertir componentes u/v a grados meteorológicos (dirección de origen)
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
