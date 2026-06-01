"""Servicio de riesgo de incendio forestal.

Intenta usar el modelo `fireDanger` de Windy para obtener FWI (Fire Weather Index)
y métricas relacionadas. Si el modelo no está disponible en el plan actual (plan
gratuito), calcula un `fire_risk_score` estimado a partir de los parámetros
meteorológicos estándar de GFS (temperatura, humedad, viento, precipitación).

Exports principales:
    - get_fire_danger: lista de FireDangerEntry con pronóstico horario de riesgo.
"""
from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from datetime import datetime

from cachetools import TTLCache

from httpx import HTTPStatusError, TimeoutException as HttpxTimeout

from app.core.config import settings
from app.core.http_client import get_client
from app.services.windy import (
    WindyNotConfiguredError,
    _fetch_raw,
    _safe_get,
    _k_to_c,
    _AR_TZ,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache específico para fire danger (TTL 1 hora)
# ---------------------------------------------------------------------------

_fire_raw_cache: TTLCache = TTLCache(maxsize=128, ttl=3600)
_fire_cache_lock = asyncio.Lock()

# ---------------------------------------------------------------------------
# Parámetros FWI de Windy
# ---------------------------------------------------------------------------

_FIRE_PARAMETERS = ["fwi", "dsr", "dc", "dmc", "ffmc"]
_FIRE_LEVELS = ["surface"]

# ---------------------------------------------------------------------------
# Tipos de datos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FireDangerEntry:
    """Un slot horario de riesgo de incendio."""
    date: str
    hour_label: str
    fwi: float | None           # FWI si disponible desde Windy fireDanger, None si estimado
    fire_risk_score: float      # 0–100
    fire_risk_label: str        # "Muy bajo" / "Bajo" / "Moderado" / "Alto" / "Muy alto" / "Extremo"
    temp_c: float | None
    humidity: float | None
    wind_kmh: float | None
    precip_mm: float | None
    is_estimated: bool          # True si fue calculado, False si viene del modelo fireDanger


# ---------------------------------------------------------------------------
# Lógica de cálculo de score (fallback)
# ---------------------------------------------------------------------------

def _compute_fire_risk(
    temp_c: float | None,
    humidity: float | None,
    wind_kmh: float | None,
    precip_mm: float | None,
) -> tuple[float, str]:
    """
    Score 0–100 basado en la lógica de NOAA Fire Weather Watch:
    - temp alta = más riesgo
    - humedad baja = más riesgo
    - viento alto = más riesgo
    - precipitación reciente = menos riesgo
    """
    score = 0.0
    if temp_c is not None:
        score += min((temp_c - 10) / 30 * 30, 30)   # max 30 pts
    if humidity is not None:
        score += max((60 - humidity) / 60 * 30, 0)   # max 30 pts
    if wind_kmh is not None:
        score += min(wind_kmh / 50 * 25, 25)          # max 25 pts
    if precip_mm is not None and precip_mm > 2:
        score = max(score - 20, 0)                    # lluvia reciente reduce riesgo
    score = max(0.0, min(100.0, score))

    if score < 20:
        label = "Muy bajo"
    elif score < 40:
        label = "Bajo"
    elif score < 60:
        label = "Moderado"
    elif score < 75:
        label = "Alto"
    elif score < 90:
        label = "Muy alto"
    else:
        label = "Extremo"

    return round(score, 1), label


def _fwi_to_label(fwi: float) -> str:
    """Convierte el FWI de Windy a etiqueta de riesgo (escala canadiense CFFDRS)."""
    if fwi < 5.2:
        return "Muy bajo"
    if fwi < 11.2:
        return "Bajo"
    if fwi < 21.3:
        return "Moderado"
    if fwi < 38.0:
        return "Alto"
    if fwi < 50.0:
        return "Muy alto"
    return "Extremo"


def _fwi_to_score(fwi: float) -> float:
    """Convierte FWI (0–∞) a score normalizado 0–100."""
    # FWI escala: 0=sin riesgo, ~50 ya es extremo. Normalizamos a 100 con tope suave.
    normalized = min(fwi / 50.0 * 100.0, 100.0)
    return round(normalized, 1)


# ---------------------------------------------------------------------------
# Fetch raw fireDanger
# ---------------------------------------------------------------------------

async def _fetch_raw_fire(lat: float, lon: float) -> dict | None:
    """
    Intenta obtener el payload crudo de Windy con model='fireDanger'.
    Devuelve None si el modelo no está disponible o la respuesta es inválida.

    Raises:
        WindyNotConfiguredError: Si windy_api_key está vacío.
    """
    if not settings.windy_api_key:
        raise WindyNotConfiguredError("windy_api_key no configurada")

    cache_key = ("fire", round(lat, 4), round(lon, 4))

    async with _fire_cache_lock:
        if cache_key in _fire_raw_cache:
            logger.debug("Fire danger cache hit for %s", cache_key)
            return _fire_raw_cache[cache_key]

    payload = {
        "lat": lat,
        "lon": lon,
        "model": "fireDanger",
        "parameters": _FIRE_PARAMETERS,
        "levels": _FIRE_LEVELS,
        "key": settings.windy_api_key,
    }

    try:
        client = get_client()
        response = await client.post(
            settings.windy_base_url,
            json=payload,
            timeout=settings.fire_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()

        # Validar que la respuesta contiene al menos el FWI
        if not data.get("ts") or not data.get("fwi-surface"):
            logger.info("fireDanger model returned no FWI data — will use fallback estimation")
            return None

        async with _fire_cache_lock:
            _fire_raw_cache[cache_key] = data

        return data

    except HttpxTimeout as exc:
        logger.warning("fireDanger model timeout — will use GFS fallback: %s", exc)
        return None
    except HTTPStatusError as exc:
        logger.warning("fireDanger model HTTP %s — will use GFS fallback", exc.response.status_code)
        return None
    except Exception as exc:
        logger.warning("fireDanger model unavailable (%s) — will use GFS fallback", exc)
        return None


# ---------------------------------------------------------------------------
# Parser fireDanger → entries
# ---------------------------------------------------------------------------

def _parse_fire_entries_from_fwi(data: dict) -> list[FireDangerEntry]:
    """Convierte el payload de fireDanger a FireDangerEntry usando FWI real."""
    ts_ms_list: list[int] = data.get("ts", [])
    fwi_list: list[float | None] = data.get("fwi-surface", [])

    # Parámetros meteorológicos de apoyo (pueden estar ausentes en fireDanger)
    temp_k: list[float | None] = data.get("temp-surface", [])
    rh: list[float | None] = data.get("rh-surface", [])
    wind_u: list[float | None] = data.get("wind_u-surface", [])
    wind_v: list[float | None] = data.get("wind_v-surface", [])
    precip: list[float | None] = data.get("past3hprecip-surface", [])

    entries: list[FireDangerEntry] = []
    for i, ts_ms in enumerate(ts_ms_list):
        dt_ar = datetime.fromtimestamp(ts_ms / 1000.0, tz=_AR_TZ)
        date_str = dt_ar.strftime("%Y-%m-%d")
        hour_label = dt_ar.strftime("%H:%M")

        fwi_val = _safe_get(fwi_list, i)
        if fwi_val is None:
            continue

        score = _fwi_to_score(fwi_val)
        label = _fwi_to_label(fwi_val)

        # Wind speed opcional desde componentes u/v
        wind_kmh: float | None = None
        u = _safe_get(wind_u, i) if wind_u else None
        v = _safe_get(wind_v, i) if wind_v else None
        if u is not None and v is not None:
            wind_kmh = round(math.sqrt(u * u + v * v) * 3.6, 2)

        entries.append(
            FireDangerEntry(
                date=date_str,
                hour_label=hour_label,
                fwi=round(fwi_val, 2),
                fire_risk_score=score,
                fire_risk_label=label,
                temp_c=_k_to_c(_safe_get(temp_k, i)) if temp_k else None,
                humidity=_safe_get(rh, i) if rh else None,
                wind_kmh=wind_kmh,
                precip_mm=_safe_get(precip, i) if precip else None,
                is_estimated=False,
            )
        )

    return entries


def _parse_fire_entries_from_gfs(lat: float, lon: float, data: dict) -> list[FireDangerEntry]:
    """Genera FireDangerEntry estimados a partir del payload GFS estándar."""
    ts_ms_list: list[int] = data.get("ts", [])
    temp_k: list[float | None] = data.get("temp-surface", [])
    rh: list[float | None] = data.get("rh-surface", [])
    wind_u: list[float | None] = data.get("wind_u-surface", [])
    wind_v: list[float | None] = data.get("wind_v-surface", [])
    precip: list[float | None] = data.get("past3hprecip-surface", [])

    entries: list[FireDangerEntry] = []
    for i, ts_ms in enumerate(ts_ms_list):
        dt_ar = datetime.fromtimestamp(ts_ms / 1000.0, tz=_AR_TZ)
        date_str = dt_ar.strftime("%Y-%m-%d")
        hour_label = dt_ar.strftime("%H:%M")

        temp_c = _k_to_c(_safe_get(temp_k, i))
        humidity = _safe_get(rh, i)
        precip_mm = _safe_get(precip, i)

        wind_kmh: float | None = None
        u = _safe_get(wind_u, i)
        v = _safe_get(wind_v, i)
        if u is not None and v is not None:
            wind_kmh = round(math.sqrt(u * u + v * v) * 3.6, 2)

        score, label = _compute_fire_risk(temp_c, humidity, wind_kmh, precip_mm)

        entries.append(
            FireDangerEntry(
                date=date_str,
                hour_label=hour_label,
                fwi=None,
                fire_risk_score=score,
                fire_risk_label=label,
                temp_c=round(temp_c, 1) if temp_c is not None else None,
                humidity=round(humidity, 1) if humidity is not None else None,
                wind_kmh=wind_kmh,
                precip_mm=round(precip_mm, 2) if precip_mm is not None else None,
                is_estimated=True,
            )
        )

    return entries


# ---------------------------------------------------------------------------
# Función pública
# ---------------------------------------------------------------------------

async def get_fire_danger(lat: float, lon: float) -> list[FireDangerEntry]:
    """
    Pronóstico de riesgo de incendio. Intenta fireDanger model, fallback a estimación GFS.

    Raises:
        WindyNotConfiguredError: Si windy_api_key está vacío.
        Exception: Ante cualquier error de red o HTTP que no sea el modelo fireDanger.
    """
    if not settings.windy_api_key:
        raise WindyNotConfiguredError("windy_api_key no configurada")

    # 1. Intentar fireDanger model
    fire_data = await _fetch_raw_fire(lat, lon)
    if fire_data is not None:
        entries = _parse_fire_entries_from_fwi(fire_data)
        if entries:
            logger.info("fire_danger: using fireDanger model for (%.4f, %.4f)", lat, lon)
            return entries

    # 2. Fallback: GFS estándar + estimación
    logger.info("fire_danger: falling back to GFS estimation for (%.4f, %.4f)", lat, lon)
    gfs_data = await _fetch_raw(lat, lon)
    return _parse_fire_entries_from_gfs(lat, lon, gfs_data)
