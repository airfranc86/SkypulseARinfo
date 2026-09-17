"""Router para alertas oficiales del SMN — endpoint no oficial, ver services/smn_alertas.py."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.core.rate_limit import limiter
from app.schemas.smn_alertas import SmnAlertasResponse
from app.services.smn_alertas import get_smn_alertas

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "",
    response_model=SmnAlertasResponse,
    summary="Alertas meteorológicas oficiales del SMN",
    description=(
        "Retorna los avisos y alertas vigentes publicados por el SMN a nivel "
        "nacional (sin filtrar por ubicación). `available=false` indica que la "
        "fuente no respondió — no que no haya alertas. Caché de 30 minutos."
    ),
)
@limiter.limit("30/minute")
async def get_alertas_smn(request: Request) -> SmnAlertasResponse:
    logger.info("GET /alertas-smn")
    return await get_smn_alertas()
