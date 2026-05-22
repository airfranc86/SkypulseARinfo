"""Orquestador: SMN primero, Open-Meteo como fallback."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException

from app.core.config import settings
from app.schemas.weather import (
    SourceMeta,
    SourceReason,
    StationMeta,
    WeatherCurrentResponse,
)
from app.services import smn, openmeteo
from app.services.calculators import compute_sensacion_termica

logger = logging.getLogger(__name__)

# Direcciones cardinales en 8 puntos — cada sector abarca 45°
_CARDINALS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def degrees_to_cardinal(deg: float) -> str:
    """Convierte grados (0–360) a dirección cardinal de 8 puntos."""
    # Normalizar a [0, 360)
    deg = deg % 360
    # Cada sector es 45°. Desplazamos 22.5° para centrar N en 0.
    index = int((deg + 22.5) / 45) % 8
    return _CARDINALS[index]


async def aggregate_current(lat: float, lon: float) -> WeatherCurrentResponse:
    """
    Árbol de decisión:
    1. SMN cercano + fresco + campos completos → usar SMN
    2-6. Cualquier condición fallida → fallback Open-Meteo
    7. Ambas fuentes caídas → 503
    """
    now = datetime.now(timezone.utc)
    smn_obs = await smn.get_nearest_observation(lat, lon)

    reason: SourceReason
    use_smn = False

    if smn_obs is None:
        reason = "smn_unavailable"
    elif smn_obs.distance_km > settings.smn_max_distance_km:
        reason = "smn_too_far"
    elif (now - smn_obs.observed_at) > timedelta(minutes=settings.smn_max_age_minutes):
        reason = "smn_stale"
    elif smn_obs.temp_c is None or smn_obs.humidity is None:
        reason = "smn_missing_fields"
    else:
        reason = "smn_nearby_fresh"
        use_smn = True

    if use_smn and smn_obs is not None:
        station_meta = StationMeta(
            name=smn_obs.station_name,
            lat=smn_obs.station_lat,
            lon=smn_obs.station_lon,
            distance_km=smn_obs.distance_km,
            observed_at=smn_obs.observed_at,
        )
        meta = SourceMeta(
            source="smn",
            reason=reason,
            station=station_meta,
            fetched_at=now,
            # El cache_hit lo detectamos via el atributo interno del TTLCache:
            # si la obs llegó del cache, la TTLCache ya lo reflejó en _fetch_stations.
            # Acá marcamos False porque no tenemos acceso directo al flag; se puede
            # extender en el futuro exponiendo el flag desde smn.get_nearest_observation.
            cache_hit=False,
        )
        wind_cardinal = (
            degrees_to_cardinal(smn_obs.wind_dir_deg)
            if smn_obs.wind_dir_deg is not None
            else None
        )
        feels_like_c: float | None = None
        if smn_obs.temp_c is not None:
            feels_like_c = compute_sensacion_termica(
                temp_c=smn_obs.temp_c,
                humidity=smn_obs.humidity,
                wind_speed_kmh=smn_obs.wind_speed_kmh,
            ).feels_like_c

        return WeatherCurrentResponse(
            lat=lat,
            lon=lon,
            temp_c=smn_obs.temp_c,
            feels_like_c=feels_like_c,
            humidity=smn_obs.humidity,
            wind_speed_kmh=smn_obs.wind_speed_kmh,
            wind_dir_deg=smn_obs.wind_dir_deg,
            wind_dir_cardinal=wind_cardinal,
            pressure_hpa=smn_obs.pressure_hpa,
            precip_1h_mm=smn_obs.precip_1h_mm,
            cloud_cover=None,
            description=smn_obs.description,
            meta=meta,
        )

    # --- Fallback: Open-Meteo ---
    logger.info("Usando Open-Meteo — razón: %s", reason)
    om = await openmeteo.get_current(lat, lon)

    # Open-Meteo a veces devuelve 200 con todos los campos en null
    # (p.ej. fecha sin datos publicados). Lo tratamos como ausencia de datos.
    if om is None or not any(
        v is not None for v in (om.temp_c, om.humidity, om.wind_speed_kmh, om.pressure_hpa)
    ):
        logger.error("Ambas fuentes no disponibles para (%s, %s)", lat, lon)
        raise HTTPException(status_code=503, detail="all_sources_unavailable")

    meta = SourceMeta(
        source="openmeteo",
        reason=reason,
        station=None,
        fetched_at=now,
        cache_hit=False,
    )
    wind_cardinal = (
        degrees_to_cardinal(om.wind_dir_deg)
        if om.wind_dir_deg is not None
        else None
    )
    return WeatherCurrentResponse(
        lat=lat,
        lon=lon,
        temp_c=om.temp_c,
        feels_like_c=om.feels_like_c,
        humidity=om.humidity,
        wind_speed_kmh=om.wind_speed_kmh,
        wind_dir_deg=om.wind_dir_deg,
        wind_dir_cardinal=wind_cardinal,
        pressure_hpa=om.pressure_hpa,
        precip_1h_mm=om.precip_1h_mm,
        cloud_cover=om.cloud_cover,
        description=om.description,
        weather_code=om.weather_code,
        meta=meta,
    )
