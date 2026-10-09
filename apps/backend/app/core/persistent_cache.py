"""Adaptador de persistencia del "último dato bueno" sobre Upstash Redis.

Es el colaborador opcional de ``SingleFlightCache`` (``load``/``save`` async). Guarda cada valor como un
sobre JSON ``{"v", "type", "saved_at", "data"}`` bajo una clave con prefijo propio y TTL, y lo reconstruye
con ``DataclassCodec`` (sin pickle). Seguridad y presupuesto de comandos:

- Redis no configurado (``get_redis()`` es None), caído o lento: no pasa nada, se degrada a "sin copia".
- Un valor ilegible, enorme, con NaN/Infinity, de otra versión del esquema, de un tipo no registrado o
  más viejo que el TTL se trata como ausente y se loguea el nombre de la caché y el motivo, nunca el
  contenido. ``load`` devuelve ``Persisted`` con la vida que le queda a la copia.
- Escritura: como mucho una por clave cada ``write_interval_seconds`` y, además, un tope global de
  ``max_writes_per_minute`` por proceso (balde de fichas). La ventana por clave se consume aunque el
  intento falle, para no insistir contra un Redis caído.
- Lectura: una clave sin copia (o con error) no se vuelve a consultar durante ``miss_memo_seconds``, y
  tras ``failure_threshold`` errores o demoras seguidos se dejan de consultar todas las claves durante
  ``breaker_seconds`` (disyuntor). Las memorias de claves están acotadas: se descartan primero las
  vencidas y luego las más viejas.
- La clave real es ``skypulse:om_last_good:v<N>:<cache>:<sha256 de la clave lógica>``: acotada en largo
  aunque los parámetros del pedido sean largos, y sin coordenadas legibles.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from app.core.cache import Persisted
from app.core.dataclass_codec import CodecError, DataclassCodec
from app.core.upstash import get_redis

logger = logging.getLogger(__name__)

# Versión del esquema: va en la clave y en el sobre. Subirla descarta las copias viejas tras un cambio
# de campos de las dataclasses (las claves viejas vencen solas por su TTL).
SCHEMA_VERSION = 1
_KEY_PREFIX = "skypulse:om_last_good"

# Una copia real pesa decenas de KB: por encima de esto el valor no es nuestro y ni se parsea.
MAX_RAW_VALUE_CHARS = 2_000_000
# Desfase de reloj tolerado entre procesos para un `saved_at` "del futuro".
_FUTURE_SKEW_SECONDS = 60.0


class _RedisLike(Protocol):
    async def read(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, ex: int | None = None) -> None: ...


class _Discard(Exception):
    """La copia leída no se usa; ``reason`` es lo único que se loguea."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _reject_constant(_name: str) -> Any:
    raise ValueError("NaN/Infinity no permitidos")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RedisLastGoodStore:
    """``load``/``save`` del último dato bueno de UNA caché (``name``) sobre Upstash Redis."""

    def __init__(
        self,
        *,
        name: str,
        codec: DataclassCodec,
        ttl_seconds: int,
        redis_provider: Callable[[], _RedisLike | None] = get_redis,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] = _utc_now,
        write_interval_seconds: float = 1800.0,
        miss_memo_seconds: float = 300.0,
        max_writes_per_minute: int = 60,
        max_tracked_keys: int = 1024,
        failure_threshold: int = 3,
        breaker_seconds: float = 60.0,
        redis_timeout_seconds: float = 2.0,
    ) -> None:
        self._name = name
        self._codec = codec
        self.ttl_seconds = ttl_seconds
        self._redis_provider = redis_provider
        self._clock = clock
        self._wall_clock = wall_clock
        self._write_interval = write_interval_seconds
        self._miss_memo = miss_memo_seconds
        self._max_tracked = max_tracked_keys
        self._failure_threshold = failure_threshold
        self._breaker_seconds = breaker_seconds
        self._timeout = redis_timeout_seconds
        # Balde de fichas de escrituras: capacidad = un minuto de presupuesto.
        self._bucket_capacity = float(max(0, max_writes_per_minute))
        self._bucket_rate = self._bucket_capacity / 60.0
        self._last_write: dict[str, float] = {}
        self._misses: dict[str, float] = {}
        self._tokens = self._bucket_capacity
        self._bucket_at: float | None = None
        self._consecutive_failures = 0
        self._breaker_until = 0.0

    def reset(self) -> None:
        """Olvida ventanas, misses, disyuntor y presupuesto. Lo usan los tests."""
        self._last_write.clear()
        self._misses.clear()
        self._tokens = self._bucket_capacity
        self._bucket_at = None
        self._consecutive_failures = 0
        self._breaker_until = 0.0

    def _redis_key(self, key: str) -> str:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        return f"{_KEY_PREFIX}:v{SCHEMA_VERSION}:{self._name}:{digest}"

    # -- Lectura -----------------------------------------------------------------------------

    async def load(self, key: str) -> Persisted | None:
        redis = self._redis_provider()
        if redis is None:
            return None
        now = self._clock()
        if now < self._breaker_until:
            return None  # disyuntor abierto: Redis venía fallando, no se insiste
        redis_key = self._redis_key(key)
        missed_at = self._misses.get(redis_key)
        if missed_at is not None and now - missed_at < self._miss_memo:
            return None
        try:
            raw = await asyncio.wait_for(redis.read(redis_key), timeout=self._timeout)
        except Exception as exc:  # noqa: BLE001 — error o demora de Redis: degrada a "sin copia"
            logger.warning("last_good_read_failed cache=%s exc_type=%s", self._name, type(exc).__name__)
            self._record_failure(now)
            self._remember_miss(redis_key, now)
            return None
        self._consecutive_failures = 0
        if raw is None:
            self._remember_miss(redis_key, now)
            return None
        loaded = self._decode(raw)
        if loaded is None:
            self._remember_miss(redis_key, now)
        return loaded

    def _record_failure(self, now: float) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._failure_threshold:
            self._consecutive_failures = 0
            self._breaker_until = now + self._breaker_seconds
            logger.warning(
                "last_good_breaker_open cache=%s seconds=%.0f", self._name, self._breaker_seconds
            )

    def _remember_miss(self, redis_key: str, now: float) -> None:
        self._put_bounded(self._misses, redis_key, now, self._miss_memo)

    def _put_bounded(self, memory: dict[str, float], key: str, now: float, horizon: float) -> None:
        """Anota ``key`` con su instante; a tope descarta primero lo vencido y luego lo más viejo."""
        memory.pop(key, None)  # reinsertar la deja como la más nueva (el dict conserva el orden)
        if len(memory) >= self._max_tracked:
            for stale_key in [k for k, at in memory.items() if now - at >= horizon]:
                del memory[stale_key]
            while len(memory) >= self._max_tracked:
                del memory[next(iter(memory))]
        memory[key] = now

    def _decode(self, raw: Any) -> Persisted | None:
        try:
            return self._decode_envelope(raw)
        except _Discard as discard:
            logger.warning("last_good_discarded cache=%s reason=%s", self._name, discard.reason)
        except Exception as exc:  # noqa: BLE001 — RecursionError de un JSON anidado, CodecError, etc.
            logger.warning(
                "last_good_discarded cache=%s reason=undecodable exc_type=%s",
                self._name,
                type(exc).__name__,
            )
        return None

    def _decode_envelope(self, raw: Any) -> Persisted:
        if not isinstance(raw, str):
            raise _Discard("not_text")
        if len(raw) > MAX_RAW_VALUE_CHARS:
            raise _Discard("too_large")
        envelope = json.loads(raw, parse_constant=_reject_constant)
        if not isinstance(envelope, dict):
            raise CodecError("el sobre no es un objeto")
        version = envelope.get("v")
        if isinstance(version, bool) or version != SCHEMA_VERSION:
            raise _Discard("schema_version")
        if "data" not in envelope or not isinstance(envelope.get("type"), str):
            raise CodecError("sobre incompleto")
        remaining = self._remaining_life(envelope.get("saved_at"))
        value = self._codec.decode(envelope["type"], envelope["data"])
        return Persisted(value, remaining)

    def _remaining_life(self, saved_at: Any) -> float:
        """Segundos de vida que le quedan a la copia según su ``saved_at``; descarta la vencida."""
        if not isinstance(saved_at, str):
            raise _Discard("saved_at_missing")
        try:
            saved = datetime.fromisoformat(saved_at)
        except ValueError:
            raise _Discard("saved_at_invalid") from None
        if saved.tzinfo is None:
            raise _Discard("saved_at_invalid")
        age = (self._wall_clock() - saved).total_seconds()
        if age < -_FUTURE_SKEW_SECONDS:
            raise _Discard("saved_at_future")
        remaining = self.ttl_seconds - max(age, 0.0)
        if remaining <= 0:
            raise _Discard("expired")
        return remaining

    # -- Escritura ---------------------------------------------------------------------------

    async def save(self, key: str, value: Any) -> None:
        redis = self._redis_provider()
        if redis is None:
            return
        redis_key = self._redis_key(key)
        now = self._clock()
        last = self._last_write.get(redis_key)
        if last is not None and now - last < self._write_interval:
            return
        if not self._take_token(now):
            logger.debug("last_good_write_budget_exhausted cache=%s", self._name)
            return  # sin consumir la ventana de la clave: se reintenta cuando haya presupuesto
        self._put_bounded(self._last_write, redis_key, now, self._write_interval)
        try:
            await asyncio.wait_for(
                redis.set(redis_key, self._encode(value), ex=self.ttl_seconds), timeout=self._timeout
            )
        except Exception as exc:  # noqa: BLE001 — una escritura fallida nunca rompe nada
            logger.warning("last_good_write_failed cache=%s exc_type=%s", self._name, type(exc).__name__)
            return
        self._misses.pop(redis_key, None)

    def _take_token(self, now: float) -> bool:
        if self._bucket_at is not None:
            elapsed = max(0.0, now - self._bucket_at)
            self._tokens = min(self._bucket_capacity, self._tokens + elapsed * self._bucket_rate)
        self._bucket_at = now
        if self._tokens < 1.0:
            return False
        self._tokens -= 1.0
        return True

    def _encode(self, value: Any) -> str:
        type_name, data = self._codec.encode(value)
        envelope = {
            "v": SCHEMA_VERSION,
            "type": type_name,
            "saved_at": self._wall_clock().isoformat(),
            "data": data,
        }
        # allow_nan=False: lo que no se podría leer de vuelta (NaN/Infinity) tampoco se escribe.
        return json.dumps(envelope, separators=(",", ":"), allow_nan=False)
