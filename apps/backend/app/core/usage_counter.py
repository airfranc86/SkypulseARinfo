"""Contador de llamadas upstream por proveedor — instrumentación mínima (Plan A Fase 2).

A diferencia del counter de CheckWX (app/core/counter.py), esto NO es un gate de
cuota: solo cuenta, nunca bloquea una request. El incremento es fire-and-forget
(asyncio.create_task) para no agregar latencia de Upstash al camino de respuesta
de cada fetch upstream. Es seguro porque RedisCounter.incr() ya es fail-open ante
fallos de Upstash (core/counter.py) — la tarea nunca levanta una excepción no
manejada.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Literal

from app.core.counter import MemoryCounter, RedisCounter, current_cycle

if TYPE_CHECKING:
    from app.core.upstash import UpstashRedis

logger = logging.getLogger(__name__)

_Counter = MemoryCounter | RedisCounter

# ---------------------------------------------------------------------------
# Estado a nivel de módulo — inyectado desde main.py lifespan (ver checkwx.py)
# ---------------------------------------------------------------------------

_redis: "UpstashRedis | None" = None
_mode: Literal["redis", "memory", "unconfigured"] = "unconfigured"
_counters: dict[str, _Counter] = {}

# Referencias fuertes a las tasks fire-and-forget en vuelo — evita que asyncio
# las recolecte a mitad de ejecución (gotcha conocido de create_task sin await).
_background_tasks: set[asyncio.Task] = set()


def configure_redis(redis: "UpstashRedis") -> None:
    global _redis, _mode
    _redis = redis
    _mode = "redis"


def configure_memory() -> None:
    global _mode
    _mode = "memory"


def _get_counter(provider: str) -> _Counter:
    """Lazy-crea y cachea el counter de un proveedor."""
    existing = _counters.get(provider)
    if existing is not None:
        return existing

    if _mode == "redis":
        assert _redis is not None
        counter: _Counter = RedisCounter(_redis, namespace=provider)
    elif _mode == "memory":
        counter = MemoryCounter()
    else:
        raise RuntimeError(
            "usage counter not initialized — call configure_redis()/configure_memory() at startup"
        )

    _counters[provider] = counter
    return counter


def record(provider: str) -> None:
    """Registra una llamada upstream a `provider`. Fire-and-forget, nunca bloquea."""
    task = asyncio.create_task(_record_async(provider))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _record_async(provider: str) -> None:
    try:
        counter = _get_counter(provider)
        await counter.incr(current_cycle())
    except Exception as exc:
        # Diagnóstico, no puede romper nada aguas arriba.
        logger.warning("usage_counter_record_failed provider=%s exc=%s", provider, exc)


async def get_usage(provider: str, cycle: str | None = None) -> int:
    """Lee el valor actual del contador de `provider`. Usado por tests/diagnóstico."""
    counter = _get_counter(provider)
    return await counter.get(cycle or current_cycle())


# ---------------------------------------------------------------------------
# Helpers de test
# ---------------------------------------------------------------------------

def _reset_for_tests() -> None:
    global _redis, _mode
    _counters.clear()
    _redis = None
    _mode = "unconfigured"


async def _wait_pending_for_tests() -> None:
    """Espera a que terminen las tasks fire-and-forget en vuelo. Solo para tests."""
    pending = list(_background_tasks)
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
