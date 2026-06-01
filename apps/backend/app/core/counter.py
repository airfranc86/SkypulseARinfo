"""Counter de cuota mensual para CheckWX API.

Implementaciones:
- RedisCounter: usa Upstash Redis REST (persistente entre reinicios)
- MemoryCounter: in-memory con asyncio.Lock (tests y modo degradado)

Helpers de ciclo exportados para evitar imports circulares:
- current_cycle() → "YYYY-MM" en UTC
- seconds_until_next_cycle() → segundos hasta el 1 del próximo mes UTC
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.upstash import UpstashRedis

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers de ciclo
# ---------------------------------------------------------------------------

def current_cycle() -> str:
    """Retorna 'YYYY-MM' en UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


def seconds_until_next_cycle() -> int:
    """Segundos hasta el día 1 del próximo mes UTC a las 00:00."""
    now = datetime.now(timezone.utc)
    if now.month == 12:
        nxt = now.replace(year=now.year + 1, month=1, day=1,
                          hour=0, minute=0, second=0, microsecond=0)
    else:
        nxt = now.replace(month=now.month + 1, day=1,
                          hour=0, minute=0, second=0, microsecond=0)
    return max(int((nxt - now).total_seconds()), 1)


# ---------------------------------------------------------------------------
# Implementaciones
# ---------------------------------------------------------------------------

class MemoryCounter:
    """In-memory counter — para tests y modo degradado sin Upstash."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._alerts: set[tuple[str, int]] = set()
        self._lock = asyncio.Lock()

    async def get(self, cycle: str) -> int:
        async with self._lock:
            return self._counters.get(cycle, 0)

    async def incr(self, cycle: str) -> int:
        async with self._lock:
            self._counters[cycle] = self._counters.get(cycle, 0) + 1
            return self._counters[cycle]

    async def alert_already_sent(self, cycle: str, threshold: int) -> bool:
        async with self._lock:
            return (cycle, threshold) in self._alerts

    async def mark_alert_sent(self, cycle: str, threshold: int, ttl_seconds: int) -> None:
        async with self._lock:
            self._alerts.add((cycle, threshold))


class RedisCounter:
    """Counter respaldado por Upstash Redis REST — sobrevive cold starts."""

    def __init__(self, redis: UpstashRedis) -> None:
        self._r = redis

    def _counter_key(self, cycle: str) -> str:
        return f"skypulse:checkwx:counter:{cycle}"

    def _alert_key(self, cycle: str, threshold: int) -> str:
        return f"skypulse:checkwx:alert:{cycle}:{threshold}"

    async def get(self, cycle: str) -> int:
        v = await self._r.get(self._counter_key(cycle))
        return int(v) if v is not None else 0

    async def incr(self, cycle: str) -> int:
        key = self._counter_key(cycle)
        new_val = await self._r.incr(key)
        if new_val == 1:
            await self._r.expire(key, seconds_until_next_cycle())
        return new_val

    async def alert_already_sent(self, cycle: str, threshold: int) -> bool:
        v = await self._r.get(self._alert_key(cycle, threshold))
        return v is not None

    async def mark_alert_sent(self, cycle: str, threshold: int, ttl_seconds: int) -> None:
        await self._r.setnx_ex(self._alert_key(cycle, threshold), ttl_seconds)
