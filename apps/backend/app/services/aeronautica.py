"""Altitud de Densidad y degradación de performance — cálculo puro, sin I/O.

Pipeline: QNH + elevación → altitud de presión → temperatura virtual (humedad)
→ altitud de densidad → σ, TAS, wing loading ajustado por densidad → reglas
operacionales → matriz de riesgo + mensaje.

Sobre el "wing loading ajustado por densidad": el wing loading físico (W/S) NO
cambia con la densidad del aire. Lo que devuelve esta herramienta es el índice
operacional WL_nominal / σ definido en FRA-118 — un indicador de cuánto se
degrada la performance respecto de condiciones estándar, no una modificación
del peso por superficie.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

AircraftModel = Literal["piston", "turboprop"]
RiskLevel = Literal["verde", "amarillo", "naranja", "rojo"]
RiskCode = Literal[
    "NORMAL",
    "REDUCED_PERFORMANCE_MARGIN",
    "UNFAVORABLE_PERFORMANCE",
    "SPECIFIC_EVALUATION_REQUIRED",
]

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

# Mensajes deliberadamente genéricos: no prescriben cifras ni maniobras, porque la
# herramienta no conoce la aeronave, el velamen ni los procedimientos aplicables.
_RISK_INFO: dict[RiskLevel, tuple[RiskCode, str]] = {
    "verde": (
        "NORMAL",
        "Condiciones normales según los parámetros ingresados.",
    ),
    "amarillo": (
        "REDUCED_PERFORMANCE_MARGIN",
        "La densidad del aire reduce el margen de performance. "
        "Verificá distancias, velocidad y limitaciones del manual de vuelo.",
    ),
    "naranja": (
        "UNFAVORABLE_PERFORMANCE",
        "Condiciones desfavorables para la performance. "
        "Recalculá con datos actualizados y considerá demorar o reevaluar la operación.",
    ),
    "rojo": (
        "SPECIFIC_EVALUATION_REQUIRED",
        "No iniciar la operación sin una evaluación específica de performance "
        "y autorización conforme a los procedimientos aplicables.",
    ),
}


@dataclass(frozen=True)
class DensityAltitudeResult:
    pressure_altitude_ft: float
    isa_temperature_c: float
    station_pressure_hpa: float
    vapor_pressure_hpa: float
    virtual_temperature_c: float
    density_altitude_ft: float
    sigma: float
    tas_kt: float
    density_adjusted_wing_loading: float
    flare_loss_pct: float
    takeoff_run_increase_pct: float
    engine_power_loss_pct: float | None
    risk_level: RiskLevel
    risk_code: RiskCode
    risk_message: str


def _vapor_pressure_hpa(temp_c: float) -> float:
    """Magnus-Tetens. Con temp_c = punto de rocío devuelve la presión parcial de vapor real."""
    return 6.1094 * math.exp((17.625 * temp_c) / (temp_c + 243.04))


def _station_pressure_hpa(qnh_hpa: float, elev_ft: float) -> float:
    """Presión de estación aproximada con la relación barométrica ISA."""
    return qnh_hpa * (1.0 - 2.25577e-5 * elev_ft * _FT_TO_M) ** 5.25588


def classify_risk(adjusted_wl: float, wl_nom: float, da_ft: float) -> RiskLevel:
    """
    Matriz de riesgo de FRA-118 (dos ejes: altitud de densidad e índice de wing
    loading ajustado / nominal). Se evalúa de la categoría más severa a la menos
    severa y gana la primera que aplica:

        rojo      índice > 1.35 × nominal   o   DA > 9.000 ft
        naranja   índice > 1.25 × nominal   o   6.000 ft <= DA <= 9.000 ft
        amarillo  índice > 1.10 × nominal   o   3.000 ft <= DA <  6.000 ft
        verde     cualquier otro caso (índice <= 1.10 × nominal y DA < 3.000 ft)

    Bordes: 3.000 ft → amarillo; 9.000 ft → naranja (rojo empieza estrictamente
    por encima). 6.000 ft → naranja: el ticket define amarillo como [3.000, 6.000]
    y naranja como [6.000, 9.000], o sea que 6.000 pertenece a ambos intervalos;
    ante un borde compartido se escala a la categoría más severa.
    """
    if adjusted_wl > 1.35 * wl_nom or da_ft > 9000.0:
        return "rojo"
    if adjusted_wl > 1.25 * wl_nom or da_ft >= 6000.0:
        return "naranja"
    if adjusted_wl > 1.10 * wl_nom or da_ft >= 3000.0:
        return "amarillo"
    return "verde"


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
    adjusted_wl = wl_nom / sigma

    # Sin "crédito" de performance por DA negativa: es la lectura conservadora.
    da_k = max(0.0, density_altitude_ft / 1000.0)
    engine_power_loss_pct = (
        _PISTON_POWER_LOSS_PCT_PER_1000_FT * da_k if aircraft_model == "piston" else None
    )

    risk_level = classify_risk(adjusted_wl=adjusted_wl, wl_nom=wl_nom, da_ft=density_altitude_ft)
    risk_code, risk_message = _RISK_INFO[risk_level]

    return DensityAltitudeResult(
        pressure_altitude_ft=pressure_altitude_ft,
        isa_temperature_c=isa_temp_c,
        station_pressure_hpa=station_hpa,
        vapor_pressure_hpa=vapor_hpa,
        virtual_temperature_c=virtual_temp_c,
        density_altitude_ft=density_altitude_ft,
        sigma=sigma,
        tas_kt=tas_kt,
        density_adjusted_wing_loading=adjusted_wl,
        flare_loss_pct=_FLARE_LOSS_PCT_PER_1000_FT * da_k,
        takeoff_run_increase_pct=_TAKEOFF_RUN_INCREASE_PCT_PER_1000_FT * da_k,
        engine_power_loss_pct=engine_power_loss_pct,
        risk_level=risk_level,
        risk_code=risk_code,
        risk_message=risk_message,
    )
