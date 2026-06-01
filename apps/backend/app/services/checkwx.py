"""Servicio único de acceso a CheckWX API.

⚠ NUNCA llamar CheckWX fuera de este módulo — bypasea el gate de cuota.

Proveedor: CheckWX (https://www.checkwxapi.com)
Cuota: 198 requests/mes en plan Free (ver settings.checkwx_monthly_limit)
Distinto de: services/metar.py (usa AWC/NOAA — sin cuota)
"""
from __future__ import annotations

import logging
from typing import Any, Literal

from cachetools import TTLCache

from app.core.config import settings
from app.core.counter import (
    MemoryCounter,
    RedisCounter,
    current_cycle,
    seconds_until_next_cycle,
)
from app.core.http_client import get_client
from app.core.notifier import maybe_notify

logger = logging.getLogger(__name__)

_Counter = MemoryCounter | RedisCounter


# ---------------------------------------------------------------------------
# Excepciones públicas
# ---------------------------------------------------------------------------

class CheckWXQuotaExceededError(Exception):
    def __init__(self, cycle: str, count: int) -> None:
        super().__init__(f"CheckWX quota exceeded: cycle={cycle} count={count}")
        self.cycle = cycle
        self.count = count


class CheckWXUnavailableError(Exception):
    pass


# ---------------------------------------------------------------------------
# Cache de respuestas — TTL por tipo
# ---------------------------------------------------------------------------

_metar_cache: TTLCache[str, dict] = TTLCache(
    maxsize=64,
    ttl=settings.cache_ttl_metar_seconds,
)
_taf_cache: TTLCache[str, dict] = TTLCache(
    maxsize=32,
    ttl=settings.cache_ttl_taf_seconds,
)


def _get_cache(kind: str) -> TTLCache:
    return _taf_cache if kind == "taf" else _metar_cache


# ---------------------------------------------------------------------------
# Counter — inyectado desde main.py lifespan
# ---------------------------------------------------------------------------

_counter: _Counter | None = None


def set_counter(counter: _Counter) -> None:
    global _counter
    _counter = counter


def get_counter() -> _Counter | None:
    return _counter


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

async def fetch_metar(icao: str, kind: Literal["metar", "taf"]) -> dict[str, Any]:
    """Punto único de acceso a CheckWX. Aplica gate de cuota y caché TTL."""
    if _counter is None:
        raise RuntimeError("checkwx counter not initialized — call set_counter() at startup")

    cache = _get_cache(kind)
    cache_key = icao

    cached = cache.get(cache_key)
    if cached is not None:
        logger.info("checkwx_cache_hit kind=%s icao=%s", kind, icao)
        return cached

    cycle = current_cycle()
    current_count = await _counter.get(cycle)

    if current_count >= settings.checkwx_monthly_limit:
        logger.warning(
            "checkwx_quota_exhausted cycle=%s count=%d limit=%d",
            cycle, current_count, settings.checkwx_monthly_limit,
        )
        await maybe_notify(cycle, current_count, _counter, settings.checkwx_monthly_limit)
        raise CheckWXQuotaExceededError(cycle=cycle, count=current_count)

    response = await _do_http_fetch(icao, kind)

    new_count = await _counter.incr(cycle)
    cache[cache_key] = response

    logger.info(
        "checkwx_fetch_ok cycle=%s count=%d/%d icao=%s kind=%s",
        cycle, new_count, settings.checkwx_monthly_limit, icao, kind,
    )

    await maybe_notify(cycle, new_count, _counter, settings.checkwx_monthly_limit)
    return response


async def _do_http_fetch(icao: str, kind: str) -> dict[str, Any]:
    url = _build_url(icao, kind)
    headers = {"X-API-Key": settings.checkwx_api_key}
    client = get_client()
    try:
        resp = await client.get(url, headers=headers, timeout=settings.metar_timeout_seconds)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error("checkwx_http_error url=%s exc=%s", url, exc)
        raise CheckWXUnavailableError(str(exc)) from exc


def _build_url(icao: str, kind: str) -> str:
    base = settings.checkwx_base_url.rstrip("/")
    if kind == "taf":
        return f"{base}/taf/{icao}"
    return f"{base}/metar/{icao}/decoded"
