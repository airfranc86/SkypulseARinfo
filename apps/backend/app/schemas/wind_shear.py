"""Schemas Pydantic para el endpoint de Cizalladura (LLWS) en aproximación."""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.services.wind_shear import DriverCode, RiskCode, RiskLevel, ThermalCode


class WindShearRequest(BaseModel):
    """
    Viento en superficie, a 500 ft y (opcional) a 1.000 ft AGL. Dirección en grados
    meteorológicos (DESDE donde sopla), rapidez en kt. Los límites de rango también
    rechazan NaN e Infinito (no cumplen ninguna comparación).
    """

    surface_wind_dir_deg: float = Field(ge=0, le=360, description="Dirección del viento en superficie (°, desde)")
    surface_wind_speed_kt: float = Field(ge=0, le=100, description="Viento sostenido en superficie (kt)")
    surface_gust_kt: float | None = Field(
        default=None, ge=0, le=150, description="Ráfaga en superficie (kt); no puede ser menor que el sostenido"
    )
    wind_500ft_dir_deg: float = Field(ge=0, le=360, description="Dirección del viento a 500 ft (°, desde)")
    wind_500ft_speed_kt: float = Field(ge=0, le=150, description="Rapidez del viento a 500 ft (kt)")
    wind_1000ft_dir_deg: float | None = Field(
        default=None, ge=0, le=360, description="Dirección del viento a 1.000 ft (°, desde); va con la rapidez"
    )
    wind_1000ft_speed_kt: float | None = Field(
        default=None, ge=0, le=150, description="Rapidez del viento a 1.000 ft (kt); va con la dirección"
    )
    surface_temp_c: float | None = Field(
        default=None, ge=-60, le=60, description="Temperatura en superficie (°C); va con la de 1.000 ft"
    )
    temp_1000ft_c: float | None = Field(
        default=None, ge=-60, le=60, description="Temperatura a 1.000 ft (°C); va con la de superficie"
    )

    @model_validator(mode="after")
    def _gust_not_below_sustained(self) -> "WindShearRequest":
        if self.surface_gust_kt is not None and self.surface_gust_kt < self.surface_wind_speed_kt:
            raise ValueError("surface_gust_kt no puede ser menor que surface_wind_speed_kt")
        return self

    @model_validator(mode="after")
    def _wind_1000ft_is_all_or_nothing(self) -> "WindShearRequest":
        if (self.wind_1000ft_dir_deg is None) != (self.wind_1000ft_speed_kt is None):
            raise ValueError("wind_1000ft_dir_deg y wind_1000ft_speed_kt van juntos o ninguno")
        return self

    @model_validator(mode="after")
    def _temperatures_are_all_or_nothing(self) -> "WindShearRequest":
        if (self.surface_temp_c is None) != (self.temp_1000ft_c is None):
            raise ValueError("surface_temp_c y temp_1000ft_c van juntas o ninguna")
        return self


class WindShearLayer(BaseModel):
    from_ft: int
    to_ft: int
    shear_kt_per_100ft: float = Field(description="|V_top − V_bottom| (módulo vectorial) por cada 100 ft")


class WindShearMaxLayer(BaseModel):
    from_ft: int
    to_ft: int


class WindShearThermal(BaseModel):
    """Nota informativa sobre la capa 0–1.000 ft. No modifica el nivel de riesgo."""

    code: ThermalCode
    lapse_c_per_1000ft: float = Field(description="Temperatura de superficie menos la de 1.000 ft (°C por 1.000 ft)")


class WindShearCalculations(BaseModel):
    """Valores intermedios y derivados, expuestos para poder auditar el cálculo."""

    layers: list[WindShearLayer]
    max_shear_kt_per_100ft: float
    max_layer: WindShearMaxLayer
    gust_spread_kt: float = Field(description="Ráfaga menos viento sostenido en superficie; 0 sin ráfaga")
    thermal: WindShearThermal | None = Field(description="null si no se enviaron las dos temperaturas")


class WindShearRisk(BaseModel):
    """
    Nivel de riesgo (hipótesis de partida de Linear FRA-119, no validadas con eventos observados).
    Gana la condición más severa; S = cizalladura de la capa más fuerte (kt/100 ft),
    G = ráfaga menos sostenido en superficie (kt):

    - rojo: S > 12, o G > 15
    - naranja: 9 <= S <= 12
    - amarillo: 4 <= S < 9
    - verde: cualquier otro caso

    Bordes: S = 12 es naranja (rojo es estrictamente mayor), G = 15 no es rojo por sí solo,
    S = 4 es amarillo y S = 9 es naranja (el ticket dejaba un hueco entre 8 y 9).
    """

    level: RiskLevel
    code: RiskCode
    message: str


class WindShearResponse(BaseModel):
    inputs: WindShearRequest
    calculations: WindShearCalculations
    risk: WindShearRisk
    drivers: list[DriverCode] = Field(
        description="Condiciones que alcanzan el umbral del nivel elegido; vacío en verde"
    )
