"""Router para METAR/TAF via CheckWX API.

GET /api/metar?icao=SAEZ           → METAR decodificado
GET /api/metar?icao=SAEZ&type=taf  → TAF raw

⚠ No llamar CheckWX directamente desde aquí — usar services/checkwx.py.
"""
from __future__ import annotations

import logging
import re
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.config import settings
from app.core.counter import seconds_until_next_cycle
from app.core.rate_limit import limiter
from app.services import checkwx as checkwx_svc

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

    try:
        return await checkwx_svc.fetch_metar(code, kind=type)
    except checkwx_svc.CheckWXQuotaExceededError as exc:
        retry_after = seconds_until_next_cycle()
        raise HTTPException(
            status_code=429,
            detail={
                "error": "metar_quota_exceeded",
                "message": "Cuota diaria de METAR agotada",
                "cycle": exc.cycle,
                "limit": settings.checkwx_daily_limit,
                "retry_after": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )
    except checkwx_svc.CheckWXUnavailableError:
        raise HTTPException(status_code=503, detail="metar_unavailable")
