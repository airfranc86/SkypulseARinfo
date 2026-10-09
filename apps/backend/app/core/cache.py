"""Caché single-flight async: deduplica fetches concurrentes con la misma clave.

Patrón: ``TTLCache`` (cachetools) + ``asyncio.Lock`` + un contenedor de resultado
por clave en vuelo. Si N coroutines piden la misma clave simultáneamente, solo
una ejecuta el fetch; el resto espera y recibe el mismo resultado —o la misma
excepción—. Evita el race TOCTOU de doble-fetch y nunca devuelve un ``KeyError``
espurio ante fallo del fetcher (el responsable propaga el error real a quienes
esperaban).

Stale-while-error: además del valor "fresco" (TTL corto), se guarda una copia
de larga duración (``stale_ttl``) del último resultado exitoso por clave. Si
un fetch falla (excepción o ``None``) y esa copia todavía es válida, se sirve
en vez de ``None`` — evita un 503 cuando el proveedor upstream tiene un blip
transitorio (rate limit, timeout) pero ya teníamos un dato bueno reciente.

Persistencia opcional: con un ``PersistentBackend`` (``load``/``save`` async), el último resultado exitoso
también se guarda fuera de proceso (en segundo plano, sin demorar la respuesta) y, si un fetch falla y la
memoria no tiene copia stale, se lee de allí. Sin backend (el valor por defecto) nada de esto existe.

Procedencia: ``get_or_fetch`` acepta un ``CacheOutcome`` opcional que la caché completa con
``hit=True`` cuando el valor salió de la caché (fresca o stale) y no de un fetch nuevo. El valor
cacheado se devuelve siempre tal cual (mismo objeto): la procedencia viaja aparte, por llamada.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Generic, Protocol, TypeVar

from cachetools import TTLCache

logger = logging.getLogger(__name__)

T = TypeVar("T")


class FetchRefused(Exception):
    """A fetch that was deliberately not attempted (for example a call budget said no).

    It says nothing about the data source, so unlike any other failure it is NOT remembered: no entry in the
    failure cache, no "key failed" for the next caller, and it is not counted as a real fetch. The caller that
    led the flight (and those that waited for it) get the stale or persisted copy when there is one; otherwise
    ``get_or_fetch`` re-raises it so the caller can answer "unavailable" for THIS request only.
    """


@dataclass(frozen=True)
class Persisted(Generic[T]):
    """Valor leído del almacén externo, con la vida que le queda allí (None = sin tope conocido)."""

    value: T
    remaining_seconds: float | None = None


class PersistentBackend(Protocol[T]):
    """Almacén externo del último dato bueno. Sus errores y demoras nunca llegan al llamador.

    ``load`` devuelve el valor tal cual o un ``Persisted`` si puede informar cuánto le queda de vida.
    """

    async def load(self, key: str) -> "T | Persisted[T] | None": ...

    async def save(self, key: str, value: T) -> None: ...


@dataclass
class CacheOutcome:
    """Receptor opcional de la procedencia de un ``get_or_fetch`` (una instancia por llamada).

    ``hit`` queda en True si el valor se sirvió desde la caché —incluida la copia stale ante un
    fetch fallido— y en False si lo trajo un fetch real (propio o compartido por single-flight).
    """

    hit: bool = False


@dataclass
class _InFlight(Generic[T]):
    """Resultado compartido de un fetch en vuelo.

    ``data`` o ``error`` se asignan ANTES de ``event.set()``, de modo que las
    coroutines que esperan leen un estado consistente al despertar.
    ``from_cache`` indica si ``data`` fue servido desde la copia stale (fetch fallido).
    """

    event: asyncio.Event = field(default_factory=asyncio.Event)
    data: T | None = None
    error: Exception | None = None
    from_cache: bool = False


def _report(outcome: CacheOutcome | None, hit: bool) -> None:
    """Anota la procedencia en el receptor, si el llamador pasó uno."""
    if outcome is not None:
        outcome.hit = hit


class SingleFlightCache(Generic[T]):
    """Caché async con deduplicación de fetches concurrentes (single-flight)."""

    def __init__(
        self,
        *,
        maxsize: int,
        ttl: float,
        name: str = "",
        failure_ttl: float = 15.0,
        stale_ttl: float | None = None,
        persistence: PersistentBackend[T] | None = None,
        persistence_timeout: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        # Resultados None se cachean con TTL corto para evitar hammering durante
        # una ventana de error, sin bloquear la recuperación por 600 s completos.
        self._failure_cache: TTLCache = TTLCache(maxsize=maxsize, ttl=failure_ttl)
        # Copia de larga duración del último resultado exitoso — fallback ante fetch fallido.
        self._stale_cache: TTLCache = TTLCache(maxsize=maxsize, ttl=stale_ttl or ttl * 6)
        self._lock = asyncio.Lock()
        self._inflight: dict[str, _InFlight[T]] = {}
        self._name = name or "single_flight"
        self._persistence = persistence
        self._persistence_timeout = persistence_timeout
        # Referencias fuertes a las escrituras en segundo plano: asyncio solo guarda referencias débiles.
        self._background_saves: set[asyncio.Task] = set()
        # Copias recuperadas de Redis: hasta cuándo pueden servirse desde la memoria (su vida restante allá).
        self._clock = clock
        self._recovered_until: dict[str, float] = {}
        self._maxsize = maxsize
        # Instrumentación de diagnóstico (Plan A Fase 2, Parte B) — hit-rate.
        self._hits: int = 0
        self._fetches: int = 0

    def clear(self) -> None:
        """Vacía la caché. Usado por los tests para garantizar aislamiento."""
        self._cache.clear()
        self._failure_cache.clear()
        self._stale_cache.clear()
        self._recovered_until.clear()

    def stats(self) -> dict[str, int | float]:
        """Contadores de diagnóstico: hits, fetches reales, y hit-rate resultante."""
        total = self._hits + self._fetches
        return {
            "hits": self._hits,
            "fetches": self._fetches,
            "hit_rate": self._hits / total if total > 0 else 0.0,
        }

    async def get_or_fetch(
        self,
        key: str,
        fetch: Callable[[], Awaitable[T]],
        *,
        outcome: CacheOutcome | None = None,
        persist: bool = True,
    ) -> T:
        """Devuelve el valor cacheado o ejecuta ``fetch`` una sola vez por clave.

        Args:
            key: clave canónica de la request.
            fetch: factoría de la coroutine que obtiene el dato ante un miss.
            outcome: receptor opcional de la procedencia (hit de caché o fetch real).
            persist: False excluye esta llamada de la persistencia (ni se guarda ni se lee); sirve
                para valores derivados que se recalculan a partir de otros ya persistidos.

        Raises:
            Exception: cualquier excepción que levante ``fetch`` se propaga a la
                coroutine responsable y a todas las que esperaban la misma clave.
        """
        async with self._lock:
            if key in self._cache:
                self._hits += 1
                logger.debug("%s cache hit: %s", self._name, key)
                _report(outcome, True)
                return self._cache[key]

            if key in self._failure_cache:
                self._hits += 1
                stale = self._stale_get(key)
                if stale is not None:
                    logger.debug("%s failure-cache hit — sirviendo stale: %s", self._name, key)
                    _report(outcome, True)
                    return stale
                logger.debug("%s failure-cache hit (None): %s", self._name, key)
                return None  # type: ignore[return-value]

            waiter = self._inflight.get(key)
            if waiter is None:
                # Primera en llegar: registra el slot y asume el fetch.
                self._inflight[key] = _InFlight()
                responsible_slot = self._inflight[key]
            else:
                # Otra coroutine ya hace el fetch — esperar evita OTRO fetch, cuenta como ahorro.
                responsible_slot = None
                self._hits += 1

        # --- Camino de la coroutine que espera ---
        if responsible_slot is None:
            await waiter.event.wait()  # type: ignore[union-attr]
            if waiter.error is not None:  # type: ignore[union-attr]
                raise waiter.error  # type: ignore[union-attr]
            _report(outcome, waiter.from_cache)  # type: ignore[union-attr]
            return waiter.data  # type: ignore[union-attr,return-value]

        # --- Camino de la coroutine responsable del fetch ---
        use_persistence = persist and self._persistence is not None
        try:
            result = await fetch()
            fetched_ok = result is not None
            async with self._lock:
                self._fetches += 1
                if fetched_ok:
                    self._cache[key] = result
                    self._stale_cache[key] = result
                    self._recovered_until.pop(key, None)   # dato fresco: sin vencimiento propio
                else:
                    self._failure_cache[key] = True
                    stale = self._stale_get(key)
                    if stale is not None:
                        logger.warning("%s fetch devolvió None — sirviendo stale: %s", self._name, key)
                        result = stale
                        responsible_slot.from_cache = True
            if fetched_ok and use_persistence:
                self._schedule_save(key, result)
            elif result is None and use_persistence:
                result = await self._recover_persisted(key)
                responsible_slot.from_cache = result is not None
            responsible_slot.data = result
            _report(outcome, responsible_slot.from_cache)
            return result
        except Exception as exc:
            refused = isinstance(exc, FetchRefused)
            async with self._lock:
                if not refused:  # a refusal is not a fetch and not a failure of the key
                    self._fetches += 1
                    self._failure_cache[key] = True
                stale = self._stale_get(key)
            if stale is None and use_persistence:
                stale = await self._recover_persisted(key)
            if stale is not None:
                logger.warning("%s fetch lanzó excepción — sirviendo stale: %s (%s)", self._name, key, exc)
                responsible_slot.data = stale
                responsible_slot.from_cache = True
                _report(outcome, True)
                return stale
            # El error se registra para que las coroutines que esperan lo
            # reciban en vez de un KeyError por cache vacía.
            responsible_slot.error = exc
            raise
        finally:
            async with self._lock:
                self._inflight.pop(key, None)
            responsible_slot.event.set()

    # --- Persistencia opcional del último dato bueno -----------------------------------------

    def _schedule_save(self, key: str, value: T) -> None:
        """Guarda en segundo plano: la respuesta no espera a Redis."""
        task = asyncio.create_task(self._save_safely(key, value))
        self._background_saves.add(task)
        task.add_done_callback(self._background_saves.discard)

    async def _save_safely(self, key: str, value: T) -> None:
        try:
            await asyncio.wait_for(self._persistence.save(key, value), timeout=self._persistence_timeout)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001 — sin el valor en el log: solo el tipo de error
            logger.warning("%s no pudo guardar la copia persistida (%s)", self._name, type(exc).__name__)

    async def _recover_persisted(self, key: str) -> T | None:
        """Lee la copia persistida (solo ante un fetch fallido sin copia en memoria).

        Con copia, la deja también en la caché stale de memoria para no volver a Redis, pero sin que
        pueda vivir allí más de lo que le queda de vida en Redis (``Persisted.remaining_seconds``).
        Cualquier error o demora se traduce en "no hay copia".
        """
        try:
            loaded = await asyncio.wait_for(self._persistence.load(key), timeout=self._persistence_timeout)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s no pudo leer la copia persistida (%s)", self._name, type(exc).__name__)
            return None
        if loaded is None:
            return None
        value, remaining = (loaded.value, loaded.remaining_seconds) if isinstance(loaded, Persisted) else (loaded, None)
        if value is None or (remaining is not None and remaining <= 0):
            return None
        async with self._lock:
            self._stale_cache[key] = value
            if remaining is not None:
                self._remember_recovered(key, self._clock() + remaining)
            else:
                self._recovered_until.pop(key, None)
        logger.warning("%s fetch falló — sirviendo la copia persistida: %s", self._name, key)
        return value

    def _remember_recovered(self, key: str, deadline: float) -> None:
        if len(self._recovered_until) >= self._maxsize:
            now = self._clock()
            for old_key in [k for k, d in self._recovered_until.items() if d <= now]:
                del self._recovered_until[old_key]
            while len(self._recovered_until) >= self._maxsize:
                del self._recovered_until[next(iter(self._recovered_until))]
        self._recovered_until[key] = deadline

    def _stale_get(self, key: str) -> T | None:
        """Copia stale de memoria, salvo que sea una recuperada de Redis que ya agotó su vida allá."""
        value = self._stale_cache.get(key)
        if value is None:
            return None
        deadline = self._recovered_until.get(key)
        if deadline is not None and self._clock() >= deadline:
            self._stale_cache.pop(key, None)
            del self._recovered_until[key]
            return None
        return value

    async def flush_persistence(self) -> None:
        """Espera las escrituras en segundo plano en vuelo (tests y cierre ordenado)."""
        pending = list(self._background_saves)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
