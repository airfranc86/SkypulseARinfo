"""Notificador de umbrales de cuota CheckWX.

Emite alertas deduplicadas a Sentry cuando el counter cruza 80%/95%/100%.
Una sola alerta por umbral por ciclo (dedup via counter.mark_alert_sent).
"""
from __future__ import annotations

import logging

import sentry_sdk

from app.core.counter import MemoryCounter, RedisCounter, seconds_until_next_cycle

logger = logging.getLogger(__name__)

_THRESHOLDS = (80, 95, 100)

# Type alias — evita importar Protocol completo en runtime
_Counter = MemoryCounter | RedisCounter


async def maybe_notify(cycle: str, count: int, counter: _Counter, limit: int) -> None:
    """Detecta cruces de umbral y emite alertas Sentry deduplicadas."""
    if limit <= 0:
        return
    percent = int(count * 100 / limit)
    crossed = max((t for t in _THRESHOLDS if percent >= t), default=None)
    if crossed is None:
        return

    if await counter.alert_already_sent(cycle, crossed):
        return

    ttl = seconds_until_next_cycle()
    await counter.mark_alert_sent(cycle, crossed, ttl)
    _emit_sentry(cycle=cycle, count=count, limit=limit, percent=percent, threshold=crossed)


def _emit_sentry(*, cycle: str, count: int, limit: int, percent: int, threshold: int) -> None:
    level = "warning" if threshold < 95 else "error"
    message = (
        f"CheckWX quota {threshold}% reached "
        f"(cycle={cycle}, count={count}/{limit})"
    )
    # SDK v2: use push_scope for scoped tags + fingerprint
    with sentry_sdk.push_scope() as scope:  # noqa: deprecated — remove when SDK>=3
        scope.set_tag("alert_kind", "checkwx_quota")
        scope.set_tag("alert_threshold", str(threshold))
        scope.set_tag("cycle", cycle)
        scope.set_extra("count", count)
        scope.set_extra("limit", limit)
        scope.fingerprint = ["checkwx-quota", cycle, str(threshold)]
        sentry_sdk.capture_message(message, level=level)

    logger.warning(
        "checkwx_alert_emitted threshold=%d count=%d/%d cycle=%s",
        threshold, count, limit, cycle,
    )
