"""Schemas Pydantic para el endpoint de Altitud de Densidad."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class DensityAltitudeRequest(BaseModel):
    elev_ft: float = Field(ge=-1000, le=20000, description="Elevación del aeródromo (ft)")
    qnh_hpa: float = Field(ge=850, le=1085, description="QNH (hPa)")
    oat_c: float = Field(ge=-60, le=60, description="Temperatura exterior (°C)")
    td_c: float = Field(ge=-80, le=40, description="Punto de rocío (°C)")
    wl_nom: float = Field(gt=0, le=10, description="Wing loading nominal (la respuesta usa la misma unidad)")
    ias_kt: float = Field(gt=0, le=250, description="Velocidad indicada (kt)")
    aircraft_model: Literal["piston", "turboprop"]

    @model_validator(mode="after")
    def _dew_point_not_above_temperature(self) -> "DensityAltitudeRequest":
        if self.td_c > self.oat_c:
            raise ValueError("td_c no puede superar oat_c")
        return self


class DensityAltitudeCalculations(BaseModel):
    """Valores intermedios y derivados, expuestos para poder auditar el cálculo."""

    pressure_altitude_ft: float
    isa_temperature_c: float = Field(description="Temperatura ISA a la altitud de presión")
    station_pressure_hpa: float = Field(description="Presión de estación aproximada (QNH + elevación)")
    vapor_pressure_hpa: float = Field(description="Presión parcial de vapor (Magnus-Tetens sobre el punto de rocío)")
    virtual_temperature_c: float = Field(description="Temperatura virtual: corrige la temperatura por humedad")
    density_altitude_ft: float
    sigma: float = Field(description="Factor de densidad (relación con la densidad ISA a nivel del mar)")
    tas_kt: float
    density_adjusted_wing_loading: float = Field(
        description=(
            "Índice operacional wl_nom / sigma. NO es el wing loading físico (W/S), que no cambia con "
            "la densidad: indica cuánto se degrada la performance respecto de condiciones estándar."
        )
    )


class DensityAltitudeRisk(BaseModel):
    """
    Nivel de riesgo. Precedencia (gana la primera que aplica; DA = altitud de densidad):

    - rojo: índice > 1.35 x nominal, o DA > 9.000 ft
    - naranja: índice > 1.25 x nominal, o 6.000 ft <= DA <= 9.000 ft
    - amarillo: índice > 1.10 x nominal, o 3.000 ft <= DA < 6.000 ft
    - verde: cualquier otro caso

    Bordes: DA = 6.000 ft es naranja (el ticket lo incluye en amarillo y naranja; se escala a la
    categoría más severa) y DA = 9.000 ft es naranja (rojo empieza estrictamente por encima).
    """

    level: Literal["verde", "amarillo", "naranja", "rojo"]
    code: Literal[
        "NORMAL",
        "REDUCED_PERFORMANCE_MARGIN",
        "UNFAVORABLE_PERFORMANCE",
        "SPECIFIC_EVALUATION_REQUIRED",
    ]
    message: str


class DensityAltitudeResponse(BaseModel):
    inputs: DensityAltitudeRequest
    calculations: DensityAltitudeCalculations
    risk: DensityAltitudeRisk
    flare_loss_pct: float
    takeoff_run_increase_pct: float
    engine_power_loss_pct: float | None = Field(description="Solo motor a pistón; null en turbohélice")
    roc: None = Field(
        default=None,
        description="Tasa de ascenso: null hasta que exista una fórmula aprobada y específica por aeronave/motor",
    )
