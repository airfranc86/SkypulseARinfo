from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

AlertLevel = Literal["verde", "amarillo", "naranja", "rojo"]

ALERT_HEX: dict[str, str] = {
    "verde":    "#3ecf7a",
    "amarillo": "#f0a030",
    "naranja":  "#e05545",
    "rojo":     "#ff3333",
}


class Volcan(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: int
    name: str
    province: str
    alert_level: AlertLevel
    alert_color_hex: str
    lat: float
    lon: float
    segemar_url: str
    ranking: int | None


class VolcanesResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    total: int
    has_active_alert: bool   # True si cualquier volcán tiene nivel naranja o rojo
    volcanes: list[Volcan]
