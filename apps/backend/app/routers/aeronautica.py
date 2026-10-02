"""Router de herramientas aeronáuticas.

POST /api/v1/aeronautica/density-altitude
POST /api/v1/aeronautica/wind-shear
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.core.rate_limit import limiter
from app.schemas.aeronautica import (
    DensityAltitudeCalculations,
    DensityAltitudeRequest,
    DensityAltitudeResponse,
    DensityAltitudeRisk,
)
from app.schemas.wind_shear import (
    WindShearCalculations,
    WindShearLayer,
    WindShearMaxLayer,
    WindShearRequest,
    WindShearResponse,
    WindShearRisk,
    WindShearThermal,
)
from app.services.aeronautica import compute_density_altitude
from app.services.wind_shear import WindShearResult, compute_wind_shear

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
    Altitud de densidad con corrección por humedad (Magnus-Tetens) y derivadas
    operativas: σ, TAS, wing loading ajustado por densidad (índice operacional,
    no el W/S físico), pérdida de flare, incremento de carrera de despegue y
    pérdida de potencia (solo motor a pistón). Devuelve los valores intermedios
    para auditoría y un mensaje de riesgo genérico.
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
        inputs=payload,
        calculations=DensityAltitudeCalculations(
            pressure_altitude_ft=round(result.pressure_altitude_ft, 1),
            isa_temperature_c=round(result.isa_temperature_c, 2),
            station_pressure_hpa=round(result.station_pressure_hpa, 2),
            vapor_pressure_hpa=round(result.vapor_pressure_hpa, 2),
            virtual_temperature_c=round(result.virtual_temperature_c, 2),
            density_altitude_ft=round(result.density_altitude_ft, 1),
            sigma=round(result.sigma, 4),
            tas_kt=round(result.tas_kt, 1),
            density_adjusted_wing_loading=round(result.density_adjusted_wing_loading, 3),
        ),
        risk=DensityAltitudeRisk(
            level=result.risk_level,
            code=result.risk_code,
            message=result.risk_message,
        ),
        flare_loss_pct=round(result.flare_loss_pct, 1),
        takeoff_run_increase_pct=round(result.takeoff_run_increase_pct, 1),
        engine_power_loss_pct=(
            round(result.engine_power_loss_pct, 1)
            if result.engine_power_loss_pct is not None
            else None
        ),
        roc=None,
    )


def _build_wind_shear_response(payload: WindShearRequest, result: WindShearResult) -> WindShearResponse:
    # Sin redondeo propio: el servicio ya redondeó cada magnitud (a 6 decimales) donde la calcula y
    # decidió el nivel con ese mismo número. Redondear más acá serviría un valor (p. ej. 4,0) que
    # contradice el nivel (3,996 es verde).
    thermal = result.thermal
    return WindShearResponse(
        inputs=payload,
        calculations=WindShearCalculations(
            layers=[
                WindShearLayer(
                    from_ft=layer.from_ft,
                    to_ft=layer.to_ft,
                    shear_kt_per_100ft=layer.shear_kt_per_100ft,
                )
                for layer in result.layers
            ],
            max_shear_kt_per_100ft=result.max_shear_kt_per_100ft,
            max_layer=WindShearMaxLayer(from_ft=result.max_layer.from_ft, to_ft=result.max_layer.to_ft),
            gust_spread_kt=result.gust_spread_kt,
            thermal=(
                WindShearThermal(code=thermal.code, lapse_c_per_1000ft=thermal.lapse_c_per_1000ft)
                if thermal is not None
                else None
            ),
        ),
        risk=WindShearRisk(
            level=result.risk_level,
            code=result.risk_code,
            message=result.risk_message,
        ),
        drivers=list(result.drivers),
    )


@router.post(
    "/wind-shear",
    response_model=WindShearResponse,
    summary="Cizalladura del viento (LLWS) en aproximación, de superficie a 1.000 ft",
)
@limiter.limit("30/minute")
async def post_wind_shear(
    request: Request,
    payload: WindShearRequest,
) -> WindShearResponse:
    """
    Cizalladura vertical del viento por capa (0–500 ft y, si hay viento a 1.000 ft,
    500–1.000 ft) como módulo de la diferencia vectorial en kt por cada 100 ft, más la
    diferencia ráfaga–sostenido en superficie. El nivel de riesgo lo marca la capa más
    fuerte o la ráfaga; la nota térmica es solo informativa. Devuelve cada capa para
    auditoría, los drivers del nivel y un mensaje de riesgo genérico.
    """
    logger.info("POST /wind-shear")

    result = compute_wind_shear(
        surface_wind_dir_deg=payload.surface_wind_dir_deg,
        surface_wind_speed_kt=payload.surface_wind_speed_kt,
        wind_500ft_dir_deg=payload.wind_500ft_dir_deg,
        wind_500ft_speed_kt=payload.wind_500ft_speed_kt,
        surface_gust_kt=payload.surface_gust_kt,
        wind_1000ft_dir_deg=payload.wind_1000ft_dir_deg,
        wind_1000ft_speed_kt=payload.wind_1000ft_speed_kt,
        surface_temp_c=payload.surface_temp_c,
        temp_1000ft_c=payload.temp_1000ft_c,
    )

    return _build_wind_shear_response(payload, result)
