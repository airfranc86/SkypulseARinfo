"""
Cliente para el endpoint de alertas del SMN (Servicio Meteorológico Nacional).

Endpoint NO OFICIAL: `ws.smn.gob.ar/alerts/type/{AL,AC}` no está documentado por
el SMN — su existencia y forma general (JSON, timestamps probablemente UNIX)
vienen de reportes de la comunidad (foro gustfront.com.ar), no de una spec
confirmada. Al momento de escribir este servicio el dominio completo
`ws.smn.gob.ar` estaba caído (503), así que el parsing de abajo NO pudo
validarse contra una respuesta real.

Por eso el parser es deliberadamente tolerante: busca cada campo bajo varios
nombres candidatos plausibles y nunca hace fallar el request completo por un
item con forma inesperada — lo descarta y loggea. Cuando el endpoint vuelva a
responder, revisar `logger.warning` de parseo y ajustar `_FIELD_CANDIDATES`
con los nombres reales.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Final

from cachetools import TTLCache

from app.core import usage_counter
from app.core.config import settings
from app.core.http_client import get_client
from app.schemas.smn_alertas import SmnAlerta, SmnAlertasResponse

logger = logging.getLogger(__name__)

_ALERT_TYPES: Final = ("AL", "AC")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

_cache: TTLCache = TTLCache(maxsize=1, ttl=settings.cache_ttl_smn_alertas_seconds)
_CACHE_KEY: Final = "alertas"
_cache_lock = asyncio.Lock()

# Nombres de campo candidatos por cada valor normalizado — ver docstring del
# módulo sobre por qué esto es una lista de suposiciones, no una spec confirmada.
_FIELD_CANDIDATES: Final[dict[str, tuple[str, ...]]] = {
    "nivel": ("level", "nivel", "severity", "alert_level", "color"),
    "tipo": ("phenomenon", "fenomeno", "tipo", "category", "type", "titulo", "title"),
    "descripcion": ("description", "descripcion", "detail", "detalle", "text", "texto", "body", "message"),
    "fecha_desde": ("from", "start", "desde", "fecha_desde", "valid_from", "date_from", "start_date"),
    "fecha_hasta": ("to", "end", "hasta", "fecha_hasta", "valid_to", "date_to", "end_date"),
}


def _find_field(item: dict, candidates: tuple[str, ...]) -> object | None:
    for key in candidates:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def _parse_alert_datetime(value: object) -> datetime | None:
    """Intenta parsear timestamp UNIX (int/float/str numérico) o ISO 8601."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.isdigit():
            try:
                return datetime.fromtimestamp(int(stripped), tz=timezone.utc)
            except (ValueError, OSError, OverflowError):
                return None
        try:
            return datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _parse_alert_item(item: dict) -> SmnAlerta | None:
    if not isinstance(item, dict):
        return None
    try:
        descripcion = _find_field(item, _FIELD_CANDIDATES["descripcion"])
        if not descripcion:
            return None
        return SmnAlerta(
            nivel=str(_find_field(item, _FIELD_CANDIDATES["nivel"]) or "sin especificar"),
            tipo=str(_find_field(item, _FIELD_CANDIDATES["tipo"]) or "sin especificar"),
            fecha_desde=_parse_alert_datetime(_find_field(item, _FIELD_CANDIDATES["fecha_desde"])),
            fecha_hasta=_parse_alert_datetime(_find_field(item, _FIELD_CANDIDATES["fecha_hasta"])),
            descripcion=str(descripcion),
        )
    except Exception as exc:
        logger.warning("smn_alertas: item con forma inesperada, se descarta: %s (item=%r)", exc, item)
        return None


async def _fetch_alert_type(alert_type: str) -> list[dict]:
    client = get_client()
    usage_counter.record("smn_alertas")
    url = f"{settings.smn_alerts_base_url}/type/{alert_type}"
    response = await client.get(url, headers=_HEADERS, timeout=settings.http_timeout_seconds)
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, list) else []


async def get_smn_alertas() -> SmnAlertasResponse:
    """
    Devuelve las alertas activas del SMN (tipos AL + AC combinados).
    Ante cualquier falla de red/parseo de la fuente completa, devuelve
    available=False con lista vacía — nunca lanza ni rompe el caller.
    """
    now = datetime.now(timezone.utc)

    async with _cache_lock:
        if _CACHE_KEY in _cache:
            return SmnAlertasResponse(alertas=_cache[_CACHE_KEY], available=True, fetched_at=now)

        results = await asyncio.gather(
            *(_fetch_alert_type(t) for t in _ALERT_TYPES),
            return_exceptions=True,
        )

        raw_items: list[dict] = []
        any_success = False
        for alert_type, result in zip(_ALERT_TYPES, results):
            if isinstance(result, Exception):
                logger.warning("smn_alertas: fetch tipo %s falló: %s", alert_type, result)
                continue
            any_success = True
            raw_items.extend(result)

        if not any_success:
            # Ninguna de las dos fuentes respondió — no cachear un fallo total.
            return SmnAlertasResponse(alertas=[], available=False, fetched_at=now)

        alertas = [a for a in (_parse_alert_item(item) for item in raw_items) if a is not None]
        _cache[_CACHE_KEY] = alertas
        return SmnAlertasResponse(alertas=alertas, available=True, fetched_at=now)
