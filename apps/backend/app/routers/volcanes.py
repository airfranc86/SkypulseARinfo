"""Router para el monitor de volcanes — datos OAVV SEGEMAR."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.core.rate_limit import limiter
from app.schemas.volcanes import VolcanesResponse
from app.services.oavv import get_volcanes

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "",
    response_model=VolcanesResponse,
    summary="Estado de alerta volcánica en Argentina",
    description=(
        "Retorna el nivel de alerta actual (verde/amarillo/naranja/rojo) de los "
        "10 volcanes monitoreados por el OAVV-SEGEMAR, con coordenadas y link "
        "al portal oficial. Caché de 2 horas."
    ),
)
@limiter.limit("10/minute")
async def get_volcanes_status(request: Request) -> VolcanesResponse:
    logger.info("GET /volcanes")
    return await get_volcanes()
