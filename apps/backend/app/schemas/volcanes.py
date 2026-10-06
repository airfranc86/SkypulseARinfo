from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

# "sin_datos": la imagen de alerta de OAVV no se pudo descargar o interpretar.
# Nunca se confunde con "verde": un falso "estable" en una alerta de seguridad
# es peor que admitir que no sabemos (FRA-343).
AlertLevel = Literal["verde", "amarillo", "naranja", "rojo", "sin_datos"]

ALERT_HEX: dict[str, str] = {
    "verde":     "#3ecf7a",
    "amarillo":  "#f0a030",
    "naranja":   "#e05545",
    "rojo":      "#ff3333",
    "sin_datos": "#8b95a5",   # gris pizarra neutro, legible sobre el tema oscuro
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
    total: int               # Volcanes con dato (excluye los "sin_datos")
    has_active_alert: bool   # True si algún volcán CON DATO tiene nivel naranja o rojo
    volcanes: list[Volcan]   # Siempre el catálogo completo; los que fallaron van en "sin_datos"
    # False si la imagen de al menos un volcán no se pudo descargar o interpretar.
    # Mismo nombre que en /api/alertas-smn.
    available: bool
