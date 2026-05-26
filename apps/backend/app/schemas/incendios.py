"""Schemas Pydantic para el endpoint /api/incendios."""
from __future__ import annotations

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Color map por etiqueta de riesgo
# ---------------------------------------------------------------------------

RISK_COLOR_MAP: dict[str, str] = {
    "Muy bajo": "#3ecf7a",
    "Bajo":     "#7ec855",
    "Moderado": "#f0a030",
    "Alto":     "#e05545",
    "Muy alto": "#e03535",
    "Extremo":  "#ff3333",
}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class FireDangerSlot(BaseModel, frozen=True):
    """Un slot horario del pronóstico de riesgo de incendio."""
    date: str
    hour_label: str
    fwi: float | None
    fire_risk_score: float
    fire_risk_label: str
    temp_c: float | None
    humidity: float | None
    wind_kmh: float | None
    precip_mm: float | None
    is_estimated: bool


class FireDangerResponse(BaseModel, frozen=True):
    """Respuesta completa del endpoint /api/incendios."""
    slots: list[FireDangerSlot]
    current_score: float
    current_label: str
    current_color: str          # hex color del label actual
    peak_score: float
    peak_label: str
    peak_hour_label: str
    source: str                 # "windy_firedanger" | "windy_gfs_estimated"
    is_estimated: bool
