"""Esquemas del TAF decodificado por períodos (FRA-365)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TafWind(BaseModel):
    direction_deg: int | None = Field(
        default=None, description="Dirección en grados; None si el viento es variable (VRB) o no se informa."
    )
    variable: bool = Field(default=False, description="True si el TAF dice VRB.")
    speed_kt: int | None = Field(default=None, ge=0, description="Velocidad en nudos.")
    gust_kt: int | None = Field(default=None, ge=0, description="Ráfaga en nudos.")


class TafCloud(BaseModel):
    cover: str = Field(description="FEW, SCT, BKN, OVC, VV, NSC, CLR, SKC...")
    base_ft: int | None = Field(default=None, ge=0, description="Base de la capa en pies sobre el terreno.")
    kind: str | None = Field(default=None, description="CB o TCU si el TAF lo indica.")


class TafTemperature(BaseModel):
    kind: str = Field(description="'max' (TX) o 'min' (TN).")
    celsius: float
    valid_at: datetime = Field(description="Momento previsto, en UTC.")


class TafPeriod(BaseModel):
    change: str = Field(
        description="initial (base), from (FM), becoming (BECMG), tempo (TEMPO) o prob (PROBxx solo)."
    )
    probability: int | None = Field(default=None, description="30 o 40 en PROB30 / PROB40.")
    valid_from: datetime = Field(description="Inicio de la ventana, en UTC.")
    valid_to: datetime = Field(description="Fin de la ventana, en UTC.")
    becoming_by: datetime | None = Field(
        default=None, description="En BECMG, momento en que el cambio ya se completó, en UTC."
    )
    wind: TafWind | None = None
    visibility_m: int | None = Field(default=None, ge=0, description="Visibilidad en metros (a 100 m, tope 10.000).")
    visibility_over: bool = Field(default=False, description="True si el TAF dice 6 millas o más (P6SM / 6+).")
    clouds: list[TafCloud] = Field(default_factory=list)
    weather: list[str] = Field(default_factory=list, description="Fenómenos como están escritos: '+TSRA', 'BR'...")
    flight_category: str | None = Field(
        default=None, description="VFR, MVFR, IFR o LIFR (umbrales FAA), con visibilidad y techo del período."
    )
    inherited: list[str] = Field(
        default_factory=list,
        description="Campos que el grupo no declara y se completaron con lo vigente: wind, visibility, clouds.",
    )


class TafDecoded(BaseModel):
    icao: str
    name: str | None = None
    issued_at: datetime | None = Field(default=None, description="Emisión, en UTC.")
    valid_from: datetime | None = Field(default=None, description="Inicio de la vigencia, en UTC.")
    valid_to: datetime | None = Field(default=None, description="Fin de la vigencia, en UTC.")
    raw: str = Field(description="El TAF tal cual lo emitió el servicio meteorológico.")
    periods: list[TafPeriod]
    temperatures: list[TafTemperature] = Field(default_factory=list)
    source: str = "aviationweather.gov (NOAA)"
