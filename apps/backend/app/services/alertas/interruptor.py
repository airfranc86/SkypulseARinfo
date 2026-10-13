"""Interruptor de apagado del envío automático de alertas (FRA-355).

Dos interruptores, y apaga cualquiera de los dos:

1. `settings.alertas_envio_activo` (variable de entorno `ALERTAS_ENVIO_ACTIVO`): el envío nace APAGADO.
2. La clave `alertas:apagado` en Upstash: si existe, sea cual sea su valor, apaga. Se crea o se borra desde la
   consola de Upstash, sin redeploy.

`clave_de_apagado_ausente` es la lectura de la clave, a prueba de fallos, y la usan los dos lados: `envio_activo`
(el envío) y `evaluacion.py` (la evaluación, que además tiene su propio interruptor de entorno,
`alertas_evaluar_en_seco`, y relee la clave antes de cada zona). Recibe el Upstash por parámetro para poder
volver a llamarla entre zonas o tandas de envío.

La 5c (el envío real) debe mandar SOLO si `envio_activo` es verdadero, y releerlo justo antes de cada envío. Nunca
con `evaluacion.evaluacion_permitida`, que también deja pasar la evaluación en seco.

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


async def clave_de_apagado_ausente(redis: UpstashRedis | None) -> bool:
    """True solo si la clave de apagado se pudo leer Y no existe. Sin Upstash o sin poder leerla, False (apagado)."""
    if redis is None:
        logger.warning("alertas: sin Upstash no se puede leer la clave de apagado; queda apagado")
        return False
    try:
        apagado = await redis.read_strict(CLAVE_APAGADO)
    except UpstashUnavailableError:
        logger.warning("alertas: no se pudo leer la clave de apagado; queda apagado")
        return False
    return apagado is None


async def envio_activo(redis: UpstashRedis | None) -> bool:
    """True solo si el envío está encendido en el entorno Y la clave de apagado no existe en Upstash."""
    if not settings.alertas_envio_activo:
        return False
    return await clave_de_apagado_ausente(redis)
