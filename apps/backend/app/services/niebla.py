"""La respuesta de Niebla (visibilidad de ahora y pronóstico horario) armada con las fuentes que ya se obtuvieron.

Antes este armado vivía dentro de `routers/niebla.py`. Está acá, como función pura, para que la página y el asistente de Mora
(2d-3a-2) digan lo mismo: quien llama junta las fuentes (el router por la red; Mora desde las cachés) y esta función decide.

Reglas (las de siempre):
  Visibilidad actual (ahora):
    1. METAR del aeropuerto más cercano (AWC, dato real), si lo trae (el módulo del METAR ya descartó el que está lejos o es viejo)
    2. Open-Meteo, si no hay METAR utilizable
  Pronóstico horario (12 h):
    1. TAF del aeropuerto más cercano (AWC, emitido por meteorólogos)
    2. Inferencia de niebla desde el modelo numérico (humedad, rocío, viento)
    3. Campo `visibility` de Open-Meteo (último recurso)
  Sin ninguna fuente de visibilidad actual no hay respuesta (`None`): el router la traduce a 503.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence

from app.schemas.niebla import NieblaResponse, VisibilityHourlySlot
from app.services.openmeteo import FogInferenceSlot, VisibilityData
from app.services.reportes_aeronauticos.metar import MetarVisibility
from app.services.reportes_aeronauticos.taf import TafHourlySlot
from app.services.visibilidad import classify_visibility

logger = logging.getLogger(__name__)


def _slot(hour_label: str, visibility_m: float | None) -> VisibilityHourlySlot:
    level, label, color = classify_visibility(visibility_m)
    return VisibilityHourlySlot(
        hour_label=hour_label, visibility_m=visibility_m, fog_level=level, fog_label=label, fog_color=color,
    )


def armar_niebla(
    metar: MetarVisibility,
    vis: VisibilityData | None,
    taf_slots: Sequence[TafHourlySlot] | None,
    fog_slots: Sequence[FogInferenceSlot] | None,
) -> NieblaResponse | None:
    """La respuesta de Niebla con las fuentes ya obtenidas, o `None` si no hay visibilidad actual de ninguna.

    `metar` siempre viene (aunque `visibility_m` sea `None`): la estación y la distancia se informan igual.
    """
    # Necesitamos al menos alguna fuente de visibilidad actual
    if metar.visibility_m is None and vis is None:
        return None

    # ── Visibilidad "ahora" ────────────────────────────────────────────────
    if metar.visibility_m is not None:
        current_m = metar.visibility_m
        source = "metar"
        logger.info("Visibilidad actual: METAR %s (%.0f km) → %.0f m", metar.icao, metar.distance_km, current_m)
    else:
        current_m = vis.current_m if vis else None
        source = "openmeteo"
        logger.info("METAR %s no disponible — usando Open-Meteo para visibilidad actual", metar.icao)

    level, label, color = classify_visibility(current_m)

    # ── Pronóstico horario 12h ─────────────────────────────────────────────
    hourly_slots: list[VisibilityHourlySlot]
    if taf_slots:
        # Fuente primaria: TAF (meteorólogos de aviación — cubre niebla real)
        hourly_source = "taf"
        hourly_slots = [_slot(s.hour_label, s.visibility_m) for s in taf_slots]
    elif fog_slots:
        # Fallback: inferencia de niebla desde NWP (humedad/rocío/viento)
        hourly_source = "openmeteo_inference"
        hourly_slots = [_slot(s.hour_label, s.visibility_m) for s in fog_slots]
    elif vis:
        # Último recurso: campo visibility directo de Open-Meteo
        hourly_source = "openmeteo"
        hourly_slots = [_slot(lbl, m) for lbl, m in zip(vis.hourly_labels, vis.hourly_m)]
    else:
        hourly_source = "none"
        hourly_slots = []
        logger.warning("No hourly visibility source available")
    logger.info("Hourly source: %s (%d slots)", hourly_source, len(hourly_slots))

    return NieblaResponse(
        visibility_m=current_m,
        fog_level=level,
        fog_label=label,
        fog_color=color,
        weather_code=vis.weather_code if vis else None,
        hourly=hourly_slots,
        source=source,
        metar_station=metar.icao,
        metar_station_name=metar.station_name,
        metar_distance_km=metar.distance_km,
        hourly_source=hourly_source,
    )
