"""Interruptor de apagado del envío automático de alertas (FRA-355).

Dos interruptores, y apaga cualquiera de los dos:

1. `settings.alertas_envio_activo` (variable de entorno `ALERTAS_ENVIO_ACTIVO`): el envío nace APAGADO.
2. La clave `alertas:apagado` en Upstash: si existe, sea cual sea su valor, apaga. Se crea o se borra desde la
   consola de Upstash, sin redeploy.

`envio_activo` recibe el Upstash por parámetro para que un servicio la pueda volver a llamar entre zonas o
tandas de envío (la 5c debe releer el interruptor justo antes de cada envío).

Falla cerrado: sin Upstash, sin poder leer la clave, o con una respuesta de Upstash sin `result` utilizable
(`{}`, `{"error": ...}`, un `result` que no es texto) cuenta como apagado. Solo un `{"result": null}`
explícito significa "la clave no existe".
"""

from __future__ import annotations

import logging

from app.core.config import settings
from app.core.upstash import UpstashRedis, UpstashUnavailableError

logger = logging.getLogger(__name__)

CLAVE_APAGADO = "alertas:apagado"


async def envio_activo(redis: UpstashRedis | None) -> bool:
    """True solo si el envío está encendido en el entorno Y la clave de apagado no existe en Upstash."""
    if not settings.alertas_envio_activo:
        return False
    if redis is None:
        logger.warning("alertas: sin Upstash no se puede leer el interruptor; el envío queda apagado")
        return False
    try:
        apagado = await redis.read_strict(CLAVE_APAGADO)
    except UpstashUnavailableError:
        logger.warning("alertas: no se pudo leer el interruptor de apagado; el envío queda apagado")
        return False
    return apagado is None
