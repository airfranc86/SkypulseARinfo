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
        """SET key 1 NX EX ttl. Returns True if key was created.

        Sends the command in the URL (``_call``) with a fixed value: only for short keys that carry nothing
        sensitive (the CheckWX quota counter). For a value that varies or that can be sensitive use ``set_nx``,
        which sends it in the body. The two are NOT interchangeable.
        """
        result = await self._call("SET", key, "1", "NX", "EX", str(ttl_seconds))
        return result == "OK"

    # -- Comandos con el valor en el cuerpo JSON (alertas push, FRA-353) ---------------------------

    async def _call_body(self, *command: str, require_result: bool = False) -> Any:
        """Manda el comando en el cuerpo. Con `require_result`, una respuesta 200 sin campo `result` (por ejemplo
        `{}` o `{"error": ...}`) es `UpstashUnavailableError`, no `None`: el llamador distingue así "la clave
        no existe" (`{"result": null}`) de "no sé qué contestó Upstash"."""
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
            if require_result and "result" not in data:
                raise ValueError("respuesta de Upstash sin result")
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

    async def read_strict(self, key: str) -> str | None:
        """GET que solo devuelve `None` si Upstash contestó `{"result": null}` (la clave no existe).

        Una respuesta sin `result`, o con un `result` que no es texto ni null, es `UpstashUnavailableError`.
        Para los interruptores de apagado, donde "no sé" tiene que contar como "apagado".
        """
        result = await self._call_body("GET", key, require_result=True)
        if result is not None and not isinstance(result, str):
            logger.warning("upstash_call_failed command=GET exc_type=resultado_no_es_texto")
            raise UpstashUnavailableError("resultado_no_es_texto")
        return result

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        """SET key value [EX ex]."""
        command = ["SET", key, value]
        if ex is not None:
            command += ["EX", str(ex)]
        await self._call_body(*command)

    async def set_nx(self, key: str, value: str, ex: int) -> bool:
        """SET key value NX EX ex, con el valor en el cuerpo. True si la clave se creó; False si ya existía.

        Sirve de lock o de marca de "ya visto": el vencimiento es obligatorio (sin él, un lock quedaría tomado
        para siempre si el proceso muere). Lo normal es DEJAR QUE VENZA: un `delete` simple puede liberar el
        lock de OTRO dueño si el propio ya venció y alguien más lo tomó. Liberarlo de forma segura (solo si el
        valor sigue siendo el propio) necesita un script (`EVAL`), que llega con la 5b.

        Manda el comando en el cuerpo (`_call_body`): usalo para valores que varían o pueden ser sensibles. Para
        una clave corta con un valor fijo y nada sensible, `setnx_ex` lo manda en la URL; no son intercambiables.
        """
        if ex < 1:
            raise ValueError("set_nx necesita un vencimiento positivo")
        result = await self._call_body("SET", key, value, "NX", "EX", str(ex))
        return result == "OK"

    async def smembers(self, key: str) -> frozenset[str]:
        """SMEMBERS key. Un conjunto que no existe es vacío; un resultado que no es una lista de textos, un error.

        Devuelve el conjunto ENTERO en una respuesta (no hay `SSCAN`): lo que acota su tamaño es el tope de
        5.000 ids de suscripción (`alertas:ids`). Con conjuntos sin tope, paginar con `SSCAN`.
        """
        result = await self._call_body("SMEMBERS", key)
        if not isinstance(result, list) or not all(isinstance(member, str) for member in result):
            logger.warning("upstash_call_failed command=SMEMBERS exc_type=resultado_no_es_lista_de_textos")
            raise UpstashUnavailableError("resultado_no_es_lista_de_textos")
        return frozenset(result)

    async def sadd(self, key: str, *members: str) -> int:
        return await self._call_int("SADD", key, *members)

    async def expire_si_falta(self, key: str, seconds: int) -> int:
        """EXPIRE key seconds NX, con el comando en el cuerpo: pone el vencimiento solo si la clave todavía no tiene uno (1 si
        lo puso, 0 si ya tenía o la clave no existe). Sirve para un conjunto que se llena de a tandas: el vencimiento corre
        desde la primera, y las siguientes no lo estiran."""
        if seconds < 1:
            raise ValueError("expire_si_falta necesita un vencimiento positivo")
        return await self._call_int("EXPIRE", key, str(seconds), "NX")

    async def srem(self, key: str, *members: str) -> int:
        return await self._call_int("SREM", key, *members)

    async def scard(self, key: str) -> int:
        return await self._call_int("SCARD", key)

    async def delete(self, key: str) -> int:
        return await self._call_int("DEL", key)

    # -- Hashes (los contadores diarios de las alertas, FRA-360) ---------------------------------

    async def hincrby(self, key: str, field: str, delta: int) -> int:
        """HINCRBY key field delta, con el comando en el cuerpo. Atómico en el servidor: dos corridas que suman a la
        vez no pierden cuentas. Devuelve el valor nuevo del campo."""
        return await self._call_int("HINCRBY", key, field, str(delta))

    async def hgetall(self, key: str) -> dict[str, str]:
        """HGETALL key. Upstash contesta una lista plana `[campo, valor, campo, valor, ...]` (vacía si la clave no
        existe); se devuelve como dict. Otra forma de respuesta es `UpstashUnavailableError`, nunca un dict a medias."""
        result = await self._call_body("HGETALL", key)
        if (
            not isinstance(result, list)
            or len(result) % 2
            or not all(isinstance(parte, str) for parte in result)
        ):
            logger.warning("upstash_call_failed command=HGETALL exc_type=resultado_no_es_lista_plana_de_textos")
            raise UpstashUnavailableError("resultado_no_es_lista_plana_de_textos")
        return dict(zip(result[::2], result[1::2]))


# Handle compartido para los endpoints de alertas: lo deja listo el lifespan de main.py.
_redis: UpstashRedis | None = None


def configure_redis(redis: UpstashRedis | None) -> None:
    """Fija (o borra, con None) el handle que devuelve `get_redis()`."""
    global _redis
    _redis = redis


def get_redis() -> UpstashRedis | None:
    """El `UpstashRedis` configurado en el arranque; None si Upstash no está configurado."""
    return _redis
