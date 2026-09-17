from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SmnAlerta(BaseModel):
    """
    Aviso oficial del SMN normalizado. `nivel` y `tipo` quedan como texto libre
    (no un Literal cerrado) porque el endpoint fuente no es oficial ni está
    documentado — no hay un catálogo confirmado de valores posibles.
    """
    model_config = ConfigDict(frozen=True)

    nivel: str
    tipo: str
    fecha_desde: datetime | None
    fecha_hasta: datetime | None
    descripcion: str


class SmnAlertasResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    alertas: list[SmnAlerta]
    # False si el endpoint de SMN no respondió o el payload no se pudo parsear —
    # el frontend debe tratar esto como "no sabemos si hay alertas", no "no hay alertas".
    available: bool
    fetched_at: datetime
