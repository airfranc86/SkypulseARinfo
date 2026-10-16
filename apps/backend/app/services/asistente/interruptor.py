"""Interruptor de emergencia del asistente: la clave `skypulse:asistente:apagado` en Upstash.

Si la clave EXISTE (con cualquier valor), el asistente está apagado; se maneja desde la consola de Upstash sin
redeploy (`SET skypulse:asistente:apagado 1` para apagar, `DEL` para volver a permitir). Si no se puede leer, también
está apagado: "no sé" cuenta como "apagado" (falla cerrado), igual que el interruptor de las alertas.

A diferencia de `alertas/interruptor.py`, que lee la clave en cada corrida, esta ruta recibe pedidos de usuarios todo
el día: se recuerda lo que dijo la clave durante `asistente_interruptor_cache_segundos` (60 por defecto), así que
apagar o volver a prender tarda hasta ese tiempo en notarse y Upstash recibe un comando por minuto en vez de uno por
pregunta. Una lectura fallida también se recuerda, para no golpear a un Upstash caído en cada pedido. El recuerdo
vive en memoria del proceso (Render corre una instancia). Este módulo solo LEE la clave: nunca la escribe ni la borra.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable

from app.core.config import settings
from app.core.upstash import UpstashRedis

logger = logging.getLogger(__name__)

CLAVE_APAGADO = "skypulse:asistente:apagado"

_recuerdo: tuple[bool, float] | None = None  # (permitido, hasta qué instante del reloj vale)


def olvidar() -> None:
    """Borra lo recordado: la próxima pregunta vuelve a leer la clave. Lo usan las pruebas."""
    global _recuerdo
    _recuerdo = None


async def asistente_permitido(redis: UpstashRedis, *, reloj: Callable[[], float] = time.monotonic) -> bool:
    """True solo si la clave de apagado NO existe y se pudo leer. Nunca levanta: ante cualquier falla, False."""
    global _recuerdo
    ahora = reloj()
    if _recuerdo is not None and ahora < _recuerdo[1]:
        return _recuerdo[0]
    try:
        permitido = await redis.read_strict(CLAVE_APAGADO) is None
    except Exception:  # noqa: BLE001 - cualquier falla de lectura es "apagado"; CancelledError no se atrapa
        logger.warning("asistente: no se pudo leer el interruptor de apagado; se lo toma como apagado")
        permitido = False
    segundos = settings.asistente_interruptor_cache_segundos
    _recuerdo = (permitido, ahora + segundos) if segundos > 0 else None
    return permitido
