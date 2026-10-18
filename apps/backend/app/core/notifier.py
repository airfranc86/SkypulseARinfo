"""Notificador de umbrales de cuota (CheckWX y, con otro nombre y tipo, el cupo diario del asistente).

Emite alertas deduplicadas a Sentry cuando el counter cruza 80%/95%/100%.
Una sola alerta por umbral por ciclo (dedup via counter.mark_alert_sent).
"""
from __future__ import annotations

import logging
from typing import Protocol

import sentry_sdk

from app.core.counter import MemoryCounter, RedisCounter, seconds_until_next_cycle

logger = logging.getLogger(__name__)

_THRESHOLDS = (80, 95, 100)

class _ContadorDeAvisos(Protocol):
    """Lo único que el notificador le pide a un contador: saber si el aviso ya salió y marcarlo."""

    async def alert_already_sent(self, cycle: str, threshold: int) -> bool: ...

    async def mark_alert_sent(self, cycle: str, threshold: int, ttl_seconds: int) -> None: ...


# Los contadores de CheckWX cumplen el protocolo; el cupo del asistente trae el suyo (services/asistente/avisos_de_cupo.py).
_Counter = MemoryCounter | RedisCounter | _ContadorDeAvisos


def umbral_cruzado(count: int, limit: int) -> int | None:
    """El umbral más alto (80, 95 o 100 %) que `count` alcanzó sobre `limit`, o None si no llegó al primero."""
    if limit <= 0:
        return None
    percent = int(count * 100 / limit)
    return max((t for t in _THRESHOLDS if percent >= t), default=None)


async def maybe_notify(
    cycle: str, count: int, counter: _Counter, limit: int,
    *, name: str = "CheckWX", kind: str = "checkwx_quota", ttl: int | None = None,
) -> None:
    """Detecta cruces de umbral y emite alertas Sentry deduplicadas.

    `name` y `kind` dicen de qué cuota se trata (el texto del mensaje y la etiqueta `alert_kind`); `ttl` es lo que dura la marca
    de "ya avisé" (por defecto, hasta el próximo ciclo de CheckWX).
    """
    crossed = umbral_cruzado(count, limit)
    if crossed is None:
        return
    percent = int(count * 100 / limit)

    if await counter.alert_already_sent(cycle, crossed):
        return

    await counter.mark_alert_sent(cycle, crossed, seconds_until_next_cycle() if ttl is None else ttl)
    _emit_sentry(cycle=cycle, count=count, limit=limit, percent=percent, threshold=crossed, name=name, kind=kind)


def _emit_sentry(*, cycle: str, count: int, limit: int, percent: int, threshold: int, name: str, kind: str) -> None:
    level = "warning" if threshold < 95 else "error"
    message = (
        f"{name} quota {threshold}% reached "
        f"(cycle={cycle}, count={count}/{limit})"
    )
    # SDK v2: use push_scope for scoped tags + fingerprint
    with sentry_sdk.push_scope() as scope:  # noqa: deprecated — remove when SDK>=3
        scope.set_tag("alert_kind", kind)
        scope.set_tag("alert_threshold", str(threshold))
        scope.set_tag("cycle", cycle)
        scope.set_extra("count", count)
        scope.set_extra("limit", limit)
        scope.fingerprint = [kind.replace("_", "-"), cycle, str(threshold)]
        sentry_sdk.capture_message(message, level=level)

    logger.warning(
        "%s_alert_emitted threshold=%d count=%d/%d cycle=%s",
        kind.split("_")[0], threshold, count, limit, cycle,
    )
