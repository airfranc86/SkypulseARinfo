"""Cliente httpx compartido — lifecycle gestionado por el lifespan de FastAPI."""
from __future__ import annotations

import httpx

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    """Retorna el cliente global. Raise RuntimeError si no fue inicializado."""
    if _client is None:
        raise RuntimeError(
            "httpx.AsyncClient no inicializado. "
            "Verificá que create_client() se llamó en el lifespan startup."
        )
    return _client


async def create_client() -> None:
    """Crea el cliente global. Llamar una vez en startup."""
    global _client
    _client = httpx.AsyncClient()


async def close_client() -> None:
    """Cierra el cliente global. Llamar una vez en shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
