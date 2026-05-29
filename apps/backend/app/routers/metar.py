"""Router para METAR/TAF via CheckWX API.

GET /api/metar?icao=SAEZ           → METAR decodificado
GET /api/metar?icao=SAEZ&type=taf  → TAF raw
"""
from __future__ import annotations

import logging
import re
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.config import settings
from app.core.http_client import get_client
from app.core.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter()

_ICAO_RE = re.compile(r"^[A-Z0-9]{4}$")


def _validate_icao(code: str) -> str:
    upper = code.strip().upper()
    if not _ICAO_RE.match(upper):
        raise HTTPException(status_code=422, detail="invalid_icao")
    return upper


@router.get("", summary="METAR y TAF via CheckWX")
@limiter.limit("20/minute")
async def get_metar(
    request: Request,
    icao: Annotated[str, Query(min_length=4, max_length=4, description="Código ICAO de 4 letras")],
    type: Annotated[str, Query(pattern="^(metar|taf)$")] = "metar",
) -> Any:
    if not settings.checkwx_api_key:
        raise HTTPException(status_code=503, detail="checkwx_not_configured")

    code = _validate_icao(icao)

    if type == "taf":
        url = f"{settings.checkwx_base_url}/taf/{code}"
    else:
        url = f"{settings.checkwx_base_url}/metar/{code}/decoded"

    headers = {"X-API-Key": settings.checkwx_api_key}
    logger.info("GET /api/metar icao=%s type=%s", code, type)

    client = get_client()
    try:
        resp = await client.get(url, headers=headers, timeout=settings.http_timeout_seconds)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error("CheckWX request failed for %s/%s: %s", code, type, exc)
        raise HTTPException(status_code=503, detail="metar_unavailable")
