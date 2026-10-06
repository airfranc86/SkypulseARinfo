from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SmnAlerta(BaseModel):
    """
    Official SMN alert, normalized from the SMN open CAP feed (CC BY 4.0).

    `nivel` is the colour derived from the CAP severity (rojo, naranja, amarillo or
    "otro" for anything we do not map); it stays free text, not a closed Literal, so a
    new severity never breaks the response. The raw CAP severity is kept in `severidad`.
    The polygon of the alert is used to filter by location and is not returned.
    """

    model_config = ConfigDict(frozen=True)

    nivel: str
    tipo: str  # CAP `event` (Tormentas, Lluvias, Viento, Nevadas, Viento Zonda, ...)
    fecha_desde: datetime | None  # CAP `onset`
    fecha_hasta: datetime | None  # CAP `expires`
    descripcion: str  # CAP `description`
    severidad: str | None = None  # raw CAP `severity` (Extreme, Severe, Moderate, ...)
    instruccion: str | None = None  # CAP `instruction`; the feed may omit it


class SmnAlertasResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    alertas: list[SmnAlerta]
    # False if we could not verify the SMN feed (it did not answer, or some alert document
    # failed to download or parse): the list is empty and the frontend must read it as
    # "we do not know whether there are alerts", never as "there are none".
    available: bool
    fetched_at: datetime
