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


class DensityAltitudeResponse(BaseModel):
    density_altitude_ft: float
    pressure_altitude_ft: float
    sigma: float
    tas_kt: float
    wl_eff: float
    flare_loss_pct: float
    takeoff_run_increase_pct: float
    engine_power_loss_pct: float | None
    risk_level: Literal["verde", "amarillo", "naranja", "rojo"]
    decision_texts: list[str]
