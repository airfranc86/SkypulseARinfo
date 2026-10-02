"""Orquestador: SMN primero (si está activado), Open-Meteo como fallback."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException

from app.core.cache import CacheOutcome
from app.core.config import settings
from app.schemas.weather import (
    SourceMeta,
    SourceReason,
    StationMeta,
    WeatherCurrentResponse,
)
from app.services import smn, openmeteo
from app.services.calculators import compute_sensacion_termica
from app.services.openmeteo import OpenMeteoCurrent
from app.services.smn import SmnObservation
from app.utils.geo import degrees_to_cardinal

logger = logging.getLogger(__name__)

# Umbral de UX para marcar un dato de Open-Meteo como "viejo" en la respuesta.
# Desacoplado del TTL interno del caché (implementación) — es una decisión de
# cuánto puede envejecer el clima "actual" antes de que valga la pena avisar.
_OPENMETEO_STALE_AFTER = timedelta(minutes=15)


def _classify_smn(smn_obs: SmnObservation | None, now: datetime) -> SourceReason:
    """Motivo por el que se usa (o no) la observación del SMN; "smn_nearby_fresh" = usarla."""
    if smn_obs is None:
        return "smn_unavailable"
    if smn_obs.distance_km > settings.smn_max_distance_km:
        return "smn_too_far"
    if (now - smn_obs.observed_at) > timedelta(minutes=settings.smn_max_age_minutes):
        return "smn_stale"
    if smn_obs.temp_c is None or smn_obs.humidity is None:
        return "smn_missing_fields"
    return "smn_nearby_fresh"


def _smn_response(
    lat: float, lon: float, smn_obs: SmnObservation, now: datetime
) -> WeatherCurrentResponse:
    station_meta = StationMeta(
        name=smn_obs.station_name,
        lat=smn_obs.station_lat,
        lon=smn_obs.station_lon,
        distance_km=smn_obs.distance_km,
        observed_at=smn_obs.observed_at,
    )
    meta = SourceMeta(
        source="smn",
        reason="smn_nearby_fresh",
        station=station_meta,
        fetched_at=now,
        # cache_hit lo expone smn.get_nearest_observation: True si la lista de estaciones
        # salió del TTLCache y no de un fetch nuevo.
        cache_hit=smn_obs.cache_hit,
        observed_at=smn_obs.observed_at,
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


def _has_readings(om: OpenMeteoCurrent | None) -> bool:
    """Open-Meteo a veces devuelve 200 con todos los campos en null (p.ej. fecha sin datos publicados)."""
    return om is not None and any(
        v is not None for v in (om.temp_c, om.humidity, om.wind_speed_kmh, om.pressure_hpa)
    )


async def _openmeteo_response(
    lat: float, lon: float, reason: SourceReason, now: datetime
) -> WeatherCurrentResponse:
    cache_outcome = CacheOutcome()
    om = await openmeteo.get_current(lat, lon, cache_outcome=cache_outcome)

    # Un 200 sin ninguna lectura se trata como ausencia de datos.
    if om is None or not _has_readings(om):
        logger.error("Ambas fuentes no disponibles para (%s, %s)", lat, lon)
        raise HTTPException(status_code=503, detail="all_sources_unavailable")

    # `stale` mide la edad de NUESTRO dato (fetched_at), no la hora que reporta Open-Meteo.
    stale = (now - om.fetched_at) > _OPENMETEO_STALE_AFTER
    if stale:
        logger.warning(
            "Open-Meteo stale fallback servido para (%s, %s) — dato de %s",
            lat, lon, om.fetched_at,
        )

    meta = SourceMeta(
        source="openmeteo",
        reason=reason,
        station=None,
        fetched_at=om.fetched_at,
        cache_hit=cache_outcome.hit,
        stale=stale,
        observed_at=om.observed_at,
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


async def aggregate_current(lat: float, lon: float) -> WeatherCurrentResponse:
    """
    Árbol de decisión:
    0. SMN desactivado (`settings.smn_enabled`, por defecto) → Open-Meteo sin llamar al SMN
    1. SMN cercano + fresco + campos completos → usar SMN
    2-6. Cualquier condición fallida → fallback Open-Meteo
    7. Ambas fuentes caídas → 503
    """
    now = datetime.now(timezone.utc)
    smn_obs: SmnObservation | None = None
    reason: SourceReason

    if settings.smn_enabled:
        smn_obs = await smn.get_nearest_observation(lat, lon)
        reason = _classify_smn(smn_obs, now)
    else:
        reason = "smn_disabled"

    if reason == "smn_nearby_fresh" and smn_obs is not None:
        return _smn_response(lat, lon, smn_obs, now)

    # Con el SMN apagado por configuración es lo esperable en cada request: no ensuciar el INFO.
    log = logger.debug if reason == "smn_disabled" else logger.info
    log("Usando Open-Meteo — razón: %s", reason)
    return await _openmeteo_response(lat, lon, reason, now)
