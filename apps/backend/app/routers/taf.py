"""TAF decodificado por períodos (FRA-365).

GET /api/taf?icao=SACO

Datos de Aviation Weather Center (NOAA) vía `services/metar.fetch_taf_entry`; no usa CheckWX, así
que no necesita su clave ni gasta su cupo. Las respuestas distinguen "ese aeropuerto no publica
TAF" (404) de "no pudimos consultarlo" (503).
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.rate_limit import limiter
from app.schemas.taf import TafDecoded
from app.services.metar import TafFetchError, fetch_taf_entry
from app.services.reportes_aeronauticos.aeropuertos import normalize_icao
from app.services.taf_decoded import normalize_taf

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
    except TafFetchError as exc:
        logger.warning("GET /api/taf %s: AWC failed: %s", code, exc)
        raise HTTPException(status_code=503, detail="taf_unavailable") from exc

    taf = normalize_taf(entry) if entry else None
    if taf is None:
        raise HTTPException(status_code=404, detail="taf_not_found")
    return taf
