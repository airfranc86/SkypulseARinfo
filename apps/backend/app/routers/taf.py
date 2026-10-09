"""TAF decodificado por períodos (FRA-365).

GET /api/taf?icao=SACO

Datos de Aviation Weather Center (NOAA) vía `reportes_aeronauticos.fetch_taf_entry`; no usa CheckWX, así
que no necesita su clave ni gasta su cupo. Las respuestas distinguen "ese aeropuerto no publica
TAF" (404) de "no pudimos consultarlo" (503) y de "ahora no se hacen más consultas nuevas a AWC" (429
`taf_busy`, con `Retry-After`): este último solo si el tope de pedidos o la pausa ante el 429 de AWC rechazan un
pedido NUEVO y no hay un TAF en caché ni un "sin TAF" recordado con que responder.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.rate_limit import limiter
from app.schemas.taf import TafDecoded
from app.services.reportes_aeronauticos import (
    TafFetchError,
    fetch_taf_entry,
    normalize_icao,
    normalize_taf,
)
from app.services.reportes_aeronauticos.taf import TafBusyError

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=TafDecoded, summary="TAF decodificado por períodos (AWC)")
@limiter.limit("20/minute")
async def get_taf(
    request: Request,
    icao: Annotated[str, Query(min_length=4, max_length=4)],
) -> TafDecoded:
    code = normalize_icao(icao)
    if code is None:
        raise HTTPException(status_code=422, detail="invalid_icao")
    try:
        entry = await fetch_taf_entry(code)
    except TafBusyError as exc:
        # Debug on purpose: during a pause or a sweep every request lands here (the budget logs a summary a minute).
        logger.debug("GET /api/taf %s: AWC request refused, retry in %d s", code, exc.retry_after)
        raise HTTPException(
            status_code=429,
            detail={"error": "taf_busy", "retry_after": exc.retry_after},
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except TafFetchError as exc:
        logger.warning("GET /api/taf %s: AWC failed: %s", code, exc)
        raise HTTPException(status_code=503, detail="taf_unavailable") from exc

    taf = normalize_taf(entry) if entry else None
    if taf is None:
        raise HTTPException(status_code=404, detail="taf_not_found")
    return taf
