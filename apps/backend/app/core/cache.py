"""Caché single-flight async: deduplica fetches concurrentes con la misma clave.

Patrón: ``TTLCache`` (cachetools) + ``asyncio.Lock`` + un contenedor de resultado
por clave en vuelo. Si N coroutines piden la misma clave simultáneamente, solo
una ejecuta el fetch; el resto espera y recibe el mismo resultado —o la misma
excepción—. Evita el race TOCTOU de doble-fetch y nunca devuelve un ``KeyError``
espurio ante fallo del fetcher (el responsable propaga el error real a quienes
esperaban).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Generic, TypeVar

from cachetools import TTLCache

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class _InFlight(Generic[T]):
    """Resultado compartido de un fetch en vuelo.

    ``data`` o ``error`` se asignan ANTES de ``event.set()``, de modo que las
    coroutines que esperan leen un estado consistente al despertar.
    """

    event: asyncio.Event = field(default_factory=asyncio.Event)
    data: T | None = None
    error: Exception | None = None


class SingleFlightCache(Generic[T]):
    """Caché async con deduplicación de fetches concurrentes (single-flight)."""

    def __init__(
        self,
        *,
        maxsize: int,
        ttl: float,
        name: str = "",
        failure_ttl: float = 15.0,
    ) -> None:
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        # Resultados None se cachean con TTL corto para evitar hammering durante
        # una ventana de error, sin bloquear la recuperación por 600 s completos.
        self._failure_cache: TTLCache = TTLCache(maxsize=maxsize, ttl=failure_ttl)
        self._lock = asyncio.Lock()
        self._inflight: dict[str, _InFlight[T]] = {}
        self._name = name or "single_flight"

    def clear(self) -> None:
        """Vacía la caché. Usado por los tests para garantizar aislamiento."""
        self._cache.clear()
        self._failure_cache.clear()

    async def get_or_fetch(self, key: str, fetch: Callable[[], Awaitable[T]]) -> T:
        """Devuelve el valor cacheado o ejecuta ``fetch`` una sola vez por clave.

        Args:
            key: clave canónica de la request.
            fetch: factoría de la coroutine que obtiene el dato ante un miss.

        Raises:
            Exception: cualquier excepción que levante ``fetch`` se propaga a la
                coroutine responsable y a todas las que esperaban la misma clave.
        """
        async with self._lock:
            if key in self._cache:
                logger.debug("%s cache hit: %s", self._name, key)
                return self._cache[key]

            if key in self._failure_cache:
                logger.debug("%s failure-cache hit (None): %s", self._name, key)
                return None  # type: ignore[return-value]

            waiter = self._inflight.get(key)
            if waiter is None:
                # Primera en llegar: registra el slot y asume el fetch.
                self._inflight[key] = _InFlight()
                responsible_slot = self._inflight[key]
            else:
                responsible_slot = None  # otra coroutine ya hace el fetch

        # --- Camino de la coroutine que espera ---
        if responsible_slot is None:
            await waiter.event.wait()  # type: ignore[union-attr]
            if waiter.error is not None:  # type: ignore[union-attr]
                raise waiter.error  # type: ignore[union-attr]
            return waiter.data  # type: ignore[union-attr,return-value]

        # --- Camino de la coroutine responsable del fetch ---
        try:
            result = await fetch()
            async with self._lock:
                if result is not None:
                    self._cache[key] = result
                else:
                    self._failure_cache[key] = True
            responsible_slot.data = result
            return result
        except Exception as exc:
            # El error se registra para que las coroutines que esperan lo
            # reciban en vez de un KeyError por cache vacía.
            responsible_slot.error = exc
            raise
        finally:
            async with self._lock:
                self._inflight.pop(key, None)
            responsible_slot.event.set()
