"""Adapter SIGMET (FRA-368 / Línea S — S2/S3). Entra al seam Fase 1, sin fetch nuevo.
Usa el cliente existente (compartido con metar/openmeteo); el endpoint real está atrás de SIGMET_ENABLED.
"""
from pydantic import BaseModel
from typing import Literal

class SigmetSchema(BaseModel):
    icaoId: str | None = None
    firId: str | None = None
    firName: str | None = None
    seriesId: int | None = None
    hazard: Literal["TS","TURB","ICE","VA","TC"] | None = None
    validTimeFrom: int | None = None
    validTimeTo: int | None = None
    base: int | None = None
    top: int | None = None
    geom: Literal["AREA"] | None = "AREA"

class SigmetResponse(BaseModel):
    data: list[SigmetSchema] = []
    source: Literal["sigmet_awc"] = "sigmet_awc"
