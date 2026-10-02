"""Cizalladura vertical del viento (LLWS) en aproximación — cálculo puro, sin I/O.

Pipeline: viento en superficie, a 500 ft y (opcional) a 1.000 ft AGL → componentes
u/v → cizalladura vectorial por capa (kt por cada 100 ft) → diferencia ráfaga–sostenido
→ matriz de riesgo + drivers + mensaje. La temperatura (opcional) solo agrega una nota
térmica informativa: no participa del nivel.

Convención meteorológica: la dirección es DESDE donde sopla el viento. Con d en radianes,
u = -s·sin(d) (hacia el este) y v = -s·cos(d) (hacia el norte).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

RiskLevel = Literal["verde", "amarillo", "naranja", "rojo"]
RiskCode = Literal["SHEAR_LIGHT", "SHEAR_MODERATE", "SHEAR_SEVERE", "SHEAR_EXTREME"]
DriverCode = Literal["shear", "gust_spread"]
ThermalCode = Literal["inversion", "unstable", "neutral"]

# Alturas de referencia (ft AGL) de los tres niveles de viento.
SURFACE_FT = 0
LEVEL_500_FT = 500
LEVEL_1000_FT = 1000

_FT_PER_SHEAR_UNIT = 100.0  # la cizalladura se expresa en kt por cada 100 ft
_FT_PER_LAPSE_UNIT = 1000.0  # el gradiente térmico se expresa en °C por cada 1.000 ft

# Cada magnitud (cizalladura por capa, ráfaga–sostenido, gradiente térmico) se redondea a esta
# cantidad de decimales UNA vez, donde se calcula. Sin esto, el ruido de coma flotante cae sobre los
# umbrales (10 → 30 kt rumbo 7 da 3.999999999999999 y no 4,0; 25,1 − 10,1 da 15.000000000000002) y
# la implementación del frontend (otra libm) decide distinto. El nivel, los drivers y el valor que se
# informa usan siempre el mismo número ya redondeado. Debe coincidir con MEASURE_DECIMALS del frontend.
_MEASURE_DECIMALS = 6

# Umbrales de la matriz de riesgo: son las hipótesis de partida de Linear FRA-119, NO están
# validados contra eventos observados. Única fuente de verdad de los umbrales en el backend.
# El ticket dejaba un hueco entre 8 y 9 kt/100 ft; se resolvió así:
#   verde    < 4          amarillo  [4, 9)          naranja  [9, 12]
#   rojo     > 12 kt/100 ft  o  ráfaga–sostenido > 15 kt
_SHEAR_YELLOW_KT_PER_100FT = 4.0  # desde este valor (inclusive): amarillo
_SHEAR_ORANGE_KT_PER_100FT = 9.0  # desde este valor (inclusive): naranja
_SHEAR_RED_KT_PER_100FT = 12.0  # estrictamente por encima: rojo (exactamente 12 sigue siendo naranja)
_GUST_SPREAD_RED_KT = 15.0  # estrictamente por encima: rojo (exactamente 15 NO lo es por sí solo)

# Adiabático seco ≈ 9,8 °C/km ≈ 2,99 °C por cada 1.000 ft. Solo para la nota informativa.
_DRY_ADIABATIC_LAPSE_C_PER_1000_FT = 2.99

_SEVERITY: dict[RiskLevel, int] = {"verde": 0, "amarillo": 1, "naranja": 2, "rojo": 3}

# Mensajes deliberadamente genéricos y sin cifras: la herramienta no conoce el velamen, la
# aeronave ni los procedimientos aplicables. Espejados en
# apps/frontend/src/lib/windShearMessages.json (un test verifica que no diverjan).
_RISK_INFO: dict[RiskLevel, tuple[RiskCode, str]] = {
    "verde": (
        "SHEAR_LIGHT",
        "Cizalladura leve según los parámetros ingresados. "
        "No garantiza condiciones seguras: seguí monitoreando el viento.",
    ),
    "amarillo": (
        "SHEAR_MODERATE",
        "Riesgo de pérdida repentina de sustentación en final. Mantené margen de altura.",
    ),
    "naranja": (
        "SHEAR_SEVERE",
        "Riesgo alto de colapso del velamen y pérdida de control direccional. "
        "Evitá la aproximación si podés.",
    ),
    "rojo": (
        "SHEAR_EXTREME",
        "Cizalladura extrema. No aterrizar en estas condiciones (No-Go).",
    ),
}

_DRIVER_MESSAGES: dict[DriverCode, str] = {
    "shear": "La cizalladura vertical del viento en la capa más fuerte explica este nivel.",
    "gust_spread": "La diferencia entre la ráfaga y el viento sostenido en superficie explica este nivel.",
}

_THERMAL_MESSAGES: dict[ThermalCode, str] = {
    "inversion": (
        "Inversión térmica en la capa baja: el viento en altura puede estar desacoplado del de "
        "superficie. Dato informativo: no modifica el nivel."
    ),
    "unstable": (
        "Capa baja inestable: esperá turbulencia térmica y ráfagas. "
        "Dato informativo: no modifica el nivel."
    ),
    "neutral": (
        "Gradiente térmico sin señal de inversión ni de inestabilidad. "
        "Dato informativo: no modifica el nivel."
    ),
}


def _round_measure(value: float) -> float:
    return round(value, _MEASURE_DECIMALS)


@dataclass(frozen=True)
class ShearLayer:
    from_ft: int
    to_ft: int
    shear_kt_per_100ft: float


@dataclass(frozen=True)
class ThermalNote:
    code: ThermalCode
    lapse_c_per_1000ft: float


@dataclass(frozen=True)
class WindShearResult:
    layers: tuple[ShearLayer, ...]
    max_shear_kt_per_100ft: float
    max_layer: ShearLayer
    gust_spread_kt: float
    thermal: ThermalNote | None
    risk_level: RiskLevel
    risk_code: RiskCode
    risk_message: str
    drivers: tuple[DriverCode, ...]


@dataclass(frozen=True)
class _WindLevel:
    height_ft: int
    u_kt: float
    v_kt: float


def _wind_level(height_ft: int, dir_deg: float, speed_kt: float) -> _WindLevel:
    """Convierte (dirección DESDE, rapidez) a componentes u/v en kt."""
    rad = math.radians(dir_deg)
    return _WindLevel(
        height_ft=height_ft,
        u_kt=-speed_kt * math.sin(rad),
        v_kt=-speed_kt * math.cos(rad),
    )


def _layer_shear(bottom: _WindLevel, top: _WindLevel) -> ShearLayer:
    """Cizalladura de la capa: |V_top − V_bottom| (módulo vectorial) por cada 100 ft, ya redondeada."""
    delta_kt = math.hypot(top.u_kt - bottom.u_kt, top.v_kt - bottom.v_kt)
    hundreds_of_ft = (top.height_ft - bottom.height_ft) / _FT_PER_SHEAR_UNIT
    return ShearLayer(
        from_ft=bottom.height_ft,
        to_ft=top.height_ft,
        shear_kt_per_100ft=_round_measure(delta_kt / hundreds_of_ft),
    )


def _shear_level(max_shear_kt_per_100ft: float) -> RiskLevel:
    if max_shear_kt_per_100ft > _SHEAR_RED_KT_PER_100FT:
        return "rojo"
    if max_shear_kt_per_100ft >= _SHEAR_ORANGE_KT_PER_100FT:
        return "naranja"
    if max_shear_kt_per_100ft >= _SHEAR_YELLOW_KT_PER_100FT:
        return "amarillo"
    return "verde"


def _gust_level(gust_spread_kt: float) -> RiskLevel:
    return "rojo" if gust_spread_kt > _GUST_SPREAD_RED_KT else "verde"


def classify_risk(max_shear_kt_per_100ft: float, gust_spread_kt: float) -> RiskLevel:
    """
    Nivel de riesgo: gana la condición más severa entre la cizalladura de la capa más fuerte
    y la diferencia ráfaga–sostenido (esta última solo puede producir rojo).

        rojo      cizalladura > 12 kt/100 ft   o   ráfaga–sostenido > 15 kt
        naranja   9 <= cizalladura <= 12
        amarillo  4 <= cizalladura < 9
        verde     cualquier otro caso

    Bordes: 4 → amarillo; 9 → naranja; 12 → naranja (rojo es estrictamente mayor); ráfaga–sostenido
    de exactamente 15 no es rojo por sí solo. Recibe magnitudes ya redondeadas con `_round_measure`:
    comparar flotantes crudos haría caer el ruido de coma flotante del lado equivocado del umbral.
    """
    shear_level = _shear_level(max_shear_kt_per_100ft)
    gust_level = _gust_level(gust_spread_kt)
    return max(shear_level, gust_level, key=_SEVERITY.__getitem__)


def _drivers(level: RiskLevel, max_shear_kt_per_100ft: float, gust_spread_kt: float) -> tuple[DriverCode, ...]:
    """Qué condiciones alcanzan el umbral del nivel elegido (o uno superior). Verde no tiene drivers."""
    if level == "verde":
        return ()
    drivers: list[DriverCode] = []
    if _SEVERITY[_shear_level(max_shear_kt_per_100ft)] >= _SEVERITY[level]:
        drivers.append("shear")
    if _SEVERITY[_gust_level(gust_spread_kt)] >= _SEVERITY[level]:
        drivers.append("gust_spread")
    return tuple(drivers)


def _thermal_note(surface_temp_c: float | None, temp_1000ft_c: float | None) -> ThermalNote | None:
    """Nota térmica informativa sobre la capa 0–1.000 ft. NO participa del nivel de riesgo."""
    if surface_temp_c is None or temp_1000ft_c is None:
        return None
    lapse = _round_measure((surface_temp_c - temp_1000ft_c) * _FT_PER_LAPSE_UNIT / (LEVEL_1000_FT - SURFACE_FT))
    code: ThermalCode
    if temp_1000ft_c > surface_temp_c:
        code = "inversion"
    elif lapse > _DRY_ADIABATIC_LAPSE_C_PER_1000_FT:
        code = "unstable"
    else:
        code = "neutral"
    return ThermalNote(code=code, lapse_c_per_1000ft=lapse)


def compute_wind_shear(
    surface_wind_dir_deg: float,
    surface_wind_speed_kt: float,
    wind_500ft_dir_deg: float,
    wind_500ft_speed_kt: float,
    *,
    surface_gust_kt: float | None = None,
    wind_1000ft_dir_deg: float | None = None,
    wind_1000ft_speed_kt: float | None = None,
    surface_temp_c: float | None = None,
    temp_1000ft_c: float | None = None,
) -> WindShearResult:
    levels = [
        _wind_level(SURFACE_FT, surface_wind_dir_deg, surface_wind_speed_kt),
        _wind_level(LEVEL_500_FT, wind_500ft_dir_deg, wind_500ft_speed_kt),
    ]
    if wind_1000ft_dir_deg is not None and wind_1000ft_speed_kt is not None:
        levels.append(_wind_level(LEVEL_1000_FT, wind_1000ft_dir_deg, wind_1000ft_speed_kt))

    layers = tuple(_layer_shear(bottom, top) for bottom, top in zip(levels, levels[1:]))
    # En un empate gana la capa más baja (la primera): es la que más pesa en la toma de contacto.
    max_layer = max(layers, key=lambda layer: layer.shear_kt_per_100ft)
    gust_spread_kt = 0.0 if surface_gust_kt is None else _round_measure(surface_gust_kt - surface_wind_speed_kt)

    risk_level = classify_risk(max_layer.shear_kt_per_100ft, gust_spread_kt)
    risk_code, risk_message = _RISK_INFO[risk_level]

    return WindShearResult(
        layers=layers,
        max_shear_kt_per_100ft=max_layer.shear_kt_per_100ft,
        max_layer=max_layer,
        gust_spread_kt=gust_spread_kt,
        thermal=_thermal_note(surface_temp_c, temp_1000ft_c),
        risk_level=risk_level,
        risk_code=risk_code,
        risk_message=risk_message,
        drivers=_drivers(risk_level, max_layer.shear_kt_per_100ft, gust_spread_kt),
    )
