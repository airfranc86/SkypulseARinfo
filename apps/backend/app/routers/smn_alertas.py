"""Router for the official SMN alerts (open CAP feed, CC BY 4.0) — see services/smn_alertas.py."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

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
        "Retorna los avisos y alertas vigentes publicados por el SMN en su feed CAP "
        "oficial (datos abiertos, CC BY 4.0). Con `lat` y `lon` devuelve solo los avisos "
        "cuya área contiene ese punto; sin ellos, todos los avisos del país. Los avisos "
        "vencidos se descartan y los que empiezan más tarde se incluyen. "
        "`available=false` indica que no se pudo verificar el feed del SMN — no que no "
        "haya alertas — y viene con la lista vacía. Caché de 30 minutos."
    ),
)
@limiter.limit("30/minute")
async def get_alertas_smn(
    request: Request,
    lat: Annotated[
        float | None, Query(ge=-90, le=90, description="Latitud del punto a consultar")
    ] = None,
    lon: Annotated[
        float | None,
        Query(ge=-180, le=180, description="Longitud del punto a consultar"),
    ] = None,
) -> SmnAlertasResponse:
    if (lat is None) != (lon is None):
        raise HTTPException(
            status_code=422, detail="lat_and_lon_must_be_given_together"
        )
    logger.info("GET /alertas-smn located=%s", lat is not None)
    return await get_smn_alertas(lat=lat, lon=lon)
