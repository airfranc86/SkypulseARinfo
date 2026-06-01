"""Cliente REST minimalista para Upstash Redis.

Usa el singleton httpx de get_client() — sin dependencias adicionales.
Solo comandos necesarios para el counter de cuota CheckWX.
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.http_client import get_client

logger = logging.getLogger(__name__)

_TIMEOUT = 5.0


class UpstashRedis:
    def __init__(self, url: str, token: str) -> None:
        self._url = url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}

    async def _call(self, *command: str) -> Any:
        path = "/" + "/".join(command)
        client = get_client()
        resp = await client.post(
            f"{self._url}{path}",
            headers=self._headers,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json().get("result")

    async def get(self, key: str) -> str | None:
        return await self._call("GET", key)

    async def incr(self, key: str) -> int:
        return int(await self._call("INCR", key))

    async def expire(self, key: str, seconds: int) -> None:
        await self._call("EXPIRE", key, str(seconds))

    async def setnx_ex(self, key: str, ttl_seconds: int) -> bool:
        """SET key 1 NX EX ttl. Returns True if key was created."""
        result = await self._call("SET", key, "1", "NX", "EX", str(ttl_seconds))
        return result == "OK"
