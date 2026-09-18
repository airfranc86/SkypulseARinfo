"""Altitud de Densidad y degradación de performance — cálculo puro, sin I/O.

Pipeline: QNH + elevación → altitud de presión → temperatura virtual (humedad)
→ altitud de densidad → σ, TAS, wing loading efectivo → reglas operacionales
→ matriz de riesgo + textos de decisión.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

AircraftModel = Literal["piston", "turboprop"]
RiskLevel = Literal["verde", "amarillo", "naranja", "rojo"]

_ISA_SEA_LEVEL_HPA = 1013.25
_FT_PER_HPA = 30.0
_ISA_SEA_LEVEL_TEMP_C = 15.0
_ISA_LAPSE_C_PER_1000_FT = 1.98
_FT_PER_DEG_C = 118.8
_FT_TO_M = 0.3048

# Reglas operacionales por cada 1.000 ft de altitud de densidad (definidas en FRA-118).
_FLARE_LOSS_PCT_PER_1000_FT = 4.0
_TAKEOFF_RUN_INCREASE_PCT_PER_1000_FT = 10.0
_PISTON_POWER_LOSS_PCT_PER_1000_FT = 3.5


@dataclass(frozen=True)
class DensityAltitudeResult:
    pressure_altitude_ft: float
    density_altitude_ft: float
    sigma: float
    tas_kt: float
    wl_eff: float
    flare_loss_pct: float
    takeoff_run_increase_pct: float
    engine_power_loss_pct: float | None
    risk_level: RiskLevel
    decision_texts: tuple[str, ...]


def _vapor_pressure_hpa(temp_c: float) -> float:
    """Magnus-Tetens. Con temp_c = punto de rocío devuelve la presión parcial de vapor real."""
    return 6.1094 * math.exp((17.625 * temp_c) / (temp_c + 243.04))


def _station_pressure_hpa(qnh_hpa: float, elev_ft: float) -> float:
    """Presión de estación aproximada con la relación barométrica ISA."""
    return qnh_hpa * (1.0 - 2.25577e-5 * elev_ft * _FT_TO_M) ** 5.25588


def classify_risk(wl_eff: float, wl_nom: float, da_ft: float) -> RiskLevel:
    """
    Umbrales de FRA-118. Se evalúa de la categoría más severa a la menos severa:
    el ticket define DA ∈ [3000, 6000] y [6000, 9000] con borde compartido en 6000,
    y en un borde ambiguo se escala a la categoría más severa.
    """
    if wl_eff > 1.35 * wl_nom or da_ft > 9000.0:
        return "rojo"
    if wl_eff > 1.25 * wl_nom or da_ft >= 6000.0:
        return "naranja"
    if wl_eff > 1.10 * wl_nom or da_ft >= 3000.0:
        return "amarillo"
    return "verde"


def _decision_texts(risk: RiskLevel, aircraft_model: AircraftModel) -> tuple[str, ...]:
    if risk == "verde":
        return ("Condiciones dentro del rango operativo normal. Sin ajustes requeridos.",)

    texts: list[str] = []
    if risk == "amarillo":
        texts.append("Subir la altura de iniciación de giro respecto a tu referencia habitual.")
        texts.append("Verificar el margen de pista disponible antes del despegue.")
    elif risk == "naranja":
        texts.append("Subir altura de iniciación de giro 45 metros.")
        texts.append("Aumentar el margen de pista: la carrera de despegue crece de forma sensible.")
    else:
        texts.append("Considerar no realizar swooping: la autoridad de flare está muy degradada.")
        texts.append("Subir altura de iniciación de giro 45 metros como mínimo si se decide saltar.")
        texts.append("Revisar la performance de despegue y de ascenso antes de operar la aeronave.")

    if aircraft_model == "piston":
        texts.append("Empobrecer mezcla antes del despegue.")
    else:
        texts.append("Verificar la performance de despegue con la tabla del fabricante.")
    return tuple(texts)


def compute_density_altitude(
    elev_ft: float,
    qnh_hpa: float,
    oat_c: float,
    td_c: float,
    wl_nom: float,
    ias_kt: float,
    aircraft_model: AircraftModel,
) -> DensityAltitudeResult:
    pressure_altitude_ft = elev_ft + _FT_PER_HPA * (_ISA_SEA_LEVEL_HPA - qnh_hpa)
    isa_temp_c = _ISA_SEA_LEVEL_TEMP_C - _ISA_LAPSE_C_PER_1000_FT * (pressure_altitude_ft / 1000.0)

    # Aire húmedo = menos denso: se usa la temperatura virtual en lugar de la temperatura seca.
    vapor_hpa = _vapor_pressure_hpa(td_c)
    station_hpa = _station_pressure_hpa(qnh_hpa, elev_ft)
    virtual_temp_k = (oat_c + 273.15) / (1.0 - 0.379 * (vapor_hpa / station_hpa))
    virtual_temp_c = virtual_temp_k - 273.15

    density_altitude_ft = pressure_altitude_ft + _FT_PER_DEG_C * (virtual_temp_c - isa_temp_c)

    sigma = (1.0 - 6.8756e-6 * density_altitude_ft) ** 4.2561
    tas_kt = ias_kt / math.sqrt(sigma)
    wl_eff = wl_nom / sigma

    # Sin "crédito" de performance por DA negativa: es la lectura conservadora.
    da_k = max(0.0, density_altitude_ft / 1000.0)
    engine_power_loss_pct = (
        _PISTON_POWER_LOSS_PCT_PER_1000_FT * da_k if aircraft_model == "piston" else None
    )

    risk_level = classify_risk(wl_eff=wl_eff, wl_nom=wl_nom, da_ft=density_altitude_ft)

    return DensityAltitudeResult(
        pressure_altitude_ft=pressure_altitude_ft,
        density_altitude_ft=density_altitude_ft,
        sigma=sigma,
        tas_kt=tas_kt,
        wl_eff=wl_eff,
        flare_loss_pct=_FLARE_LOSS_PCT_PER_1000_FT * da_k,
        takeoff_run_increase_pct=_TAKEOFF_RUN_INCREASE_PCT_PER_1000_FT * da_k,
        engine_power_loss_pct=engine_power_loss_pct,
        risk_level=risk_level,
        decision_texts=_decision_texts(risk_level, aircraft_model),
    )
