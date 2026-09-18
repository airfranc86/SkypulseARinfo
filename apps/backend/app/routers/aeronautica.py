"""Router de herramientas aeronáuticas.

POST /api/v1/aeronautica/density-altitude
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.core.rate_limit import limiter
from app.schemas.aeronautica import DensityAltitudeRequest, DensityAltitudeResponse
from app.services.aeronautica import compute_density_altitude

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/density-altitude",
    response_model=DensityAltitudeResponse,
    summary="Altitud de Densidad y su impacto en velamen y aeronave de salto",
)
@limiter.limit("30/minute")
async def post_density_altitude(
    request: Request,
    payload: DensityAltitudeRequest,
) -> DensityAltitudeResponse:
    """
    Altitud de Densidad con corrección por humedad (Magnus-Tetens) y derivadas
    operativas: σ, TAS, wing loading efectivo, pérdida de flare, incremento de
    carrera de despegue y pérdida de potencia (solo motor a pistón).
    """
    logger.info("POST /density-altitude model=%s", payload.aircraft_model)

    result = compute_density_altitude(
        elev_ft=payload.elev_ft,
        qnh_hpa=payload.qnh_hpa,
        oat_c=payload.oat_c,
        td_c=payload.td_c,
        wl_nom=payload.wl_nom,
        ias_kt=payload.ias_kt,
        aircraft_model=payload.aircraft_model,
    )

    return DensityAltitudeResponse(
        density_altitude_ft=round(result.density_altitude_ft, 1),
        pressure_altitude_ft=round(result.pressure_altitude_ft, 1),
        sigma=round(result.sigma, 4),
        tas_kt=round(result.tas_kt, 1),
        wl_eff=round(result.wl_eff, 3),
        flare_loss_pct=round(result.flare_loss_pct, 1),
        takeoff_run_increase_pct=round(result.takeoff_run_increase_pct, 1),
        engine_power_loss_pct=(
            round(result.engine_power_loss_pct, 1)
            if result.engine_power_loss_pct is not None
            else None
        ),
        risk_level=result.risk_level,
        decision_texts=list(result.decision_texts),
    )
