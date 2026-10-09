"""Cliente REST minimalista para Upstash Redis.

Usa el singleton httpx de get_client() — sin dependencias adicionales.

Dos formas de mandar un comando:
- `_call`: `POST {url}/CMD/arg1/arg2`, argumentos en la URL. Sirve para claves cortas (counter de
  cuota CheckWX), pero un valor quedaría en la URL y en el texto de las excepciones de httpx.
- `_call_body`: `POST {url}/` con el comando como arreglo JSON en el cuerpo. Es la que usan los
  comandos que llevan valores (alertas push, FRA-353): la URL queda en la raíz y nada del contenido
  llega a un log ni a un mensaje de error.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.http_client import get_client

logger = logging.getLogger(__name__)

_TIMEOUT = 5.0


class UpstashUnavailableError(Exception):
    """Upstash REST no respondió (DNS, timeout, red) — no es un error de datos."""


class UpstashRedis:
    def __init__(self, url: str, token: str) -> None:
        self._url = url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}

    async def _call(self, *command: str) -> Any:
        path = "/" + "/".join(command)
        client = get_client()
        try:
            resp = await client.post(
                f"{self._url}{path}",
                headers=self._headers,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("upstash_call_failed command=%s exc=%s", command[0], exc)
            raise UpstashUnavailableError(str(exc)) from exc
        return resp.json().get("result")

    async def get(self, key: str) -> str | None:
        return await self._call("GET", key)

    async def incr(self, key: str) -> int:
        return int(await self._call("INCR", key))

    async def decr(self, key: str) -> int:
        """DECR key. The result can be negative when the key did not exist (Redis creates it at -1)."""
        return int(await self._call("DECR", key))

    async def expire(self, key: str, seconds: int) -> None:
        await self._call("EXPIRE", key, str(seconds))

    async def setnx_ex(self, key: str, ttl_seconds: int) -> bool:
        """SET key 1 NX EX ttl. Returns True if key was created."""
        result = await self._call("SET", key, "1", "NX", "EX", str(ttl_seconds))
        return result == "OK"

    # -- Comandos con el valor en el cuerpo JSON (alertas push, FRA-353) ---------------------------

    async def _call_body(self, *command: str) -> Any:
        try:
            resp = await get_client().post(
                f"{self._url}/",
                headers=self._headers,
                json=list(command),
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict):
                raise TypeError("respuesta de Upstash inesperada")
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            # Solo el nombre del comando y el tipo de error: el texto de la excepción y los
            # argumentos pueden traer el endpoint push o las claves.
            logger.warning(
                "upstash_call_failed command=%s exc_type=%s status=%s",
                command[0],
                type(exc).__name__,
                getattr(getattr(exc, "response", None), "status_code", None),
            )
            raise UpstashUnavailableError(type(exc).__name__) from None
        return data.get("result")

    async def _call_int(self, *command: str) -> int:
        result = await self._call_body(*command)
        if isinstance(result, bool) or not isinstance(result, int):
            logger.warning("upstash_call_failed command=%s exc_type=resultado_no_entero", command[0])
            raise UpstashUnavailableError("resultado_no_entero")
        return result

    async def read(self, key: str) -> str | None:
        """GET con el comando en el cuerpo: lo guardado puede ser un valor sensible."""
        return await self._call_body("GET", key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        """SET key value [EX ex]."""
        command = ["SET", key, value]
        if ex is not None:
            command += ["EX", str(ex)]
        await self._call_body(*command)

    async def sadd(self, key: str, *members: str) -> int:
        return await self._call_int("SADD", key, *members)

    async def srem(self, key: str, *members: str) -> int:
        return await self._call_int("SREM", key, *members)

    async def scard(self, key: str) -> int:
        return await self._call_int("SCARD", key)

    async def delete(self, key: str) -> int:
        return await self._call_int("DEL", key)


# Handle compartido para los endpoints de alertas: lo deja listo el lifespan de main.py.
_redis: UpstashRedis | None = None


def configure_redis(redis: UpstashRedis | None) -> None:
    """Fija (o borra, con None) el handle que devuelve `get_redis()`."""
    global _redis
    _redis = redis


def get_redis() -> UpstashRedis | None:
    """El `UpstashRedis` configurado en el arranque; None si Upstash no está configurado."""
    return _redis
