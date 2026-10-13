"""Evaluación programada de alertas (FRA-355): el gancho de la 5b.

Hoy `evaluar` no hace nada: lo llama `POST /api/alertas/evaluar` después de verificar la firma de QStash y de
mirar el interruptor, y devuelve `listo`. La evaluación real (consulta a Open-Meteo, reglas, envío) llega en la
5b y la 5c.

OBLIGACIONES DE LA 5b, ANTES de evaluar o mandar nada (la firma sola no impide que se repita un mensaje dentro
de su vida de ~5 minutos; ver `firma_qstash.py`):

a) tomar el lock de la corrida: `redis.set_nx("alertas:evaluar:lock", ..., ex=...)`; si ya está tomado,
   responder 200 sin hacer nada. Dejarlo vencer: un `delete` simple puede liberar el lock de otro dueño;
b) registrar el `jti` de la firma: `redis.set_nx("alertas:jti:<jti>", "1", ex=<vida que le queda a la firma>)`;
   si ya estaba, responder 200 sin hacer nada; si Upstash no responde, FALLAR CERRADO (no evaluar). Hacer
   obligatorio el claim `jti` espera a ver, en un reintento real capturado, si QStash firma cada reintento con
   un `jti` nuevo.

La 5c (el envío real) además debe volver a leer el interruptor (`interruptor.envio_activo(redis)`) justo antes
de cada envío: el router lo lee una sola vez, al entrar.

PRESUPUESTO DE OPEN-METEO: el router corre esto dentro de `sin_clave_de_cliente()`, y sin clave de cliente el
presupuesto de Open-Meteo no aplica NI el tope por cliente NI el GLOBAL. La 5b debe darle al trabajo su propia
clave fija (por ejemplo `set_client_key("job:alertas")`) para que el balde global siga valiendo, o acotar la
cantidad de zonas por corrida y espaciar los pedidos.

TIEMPO DE RESPUESTA: QStash espera la respuesta un tiempo limitado y reintenta si no llega. La 5b debe
contestar rápido (el 200 sale en cuanto se tomó el lock y se registró el `jti`) y hacer el trabajo largo fuera
del pedido (`BackgroundTasks`), o repartirlo en varias llamadas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.core.upstash import UpstashRedis


@dataclass(frozen=True)
class ResultadoEvaluacion:
    """Qué pasó en una corrida; `estado` es lo que viaja en la respuesta JSON."""

    estado: str


async def evaluar(redis: UpstashRedis, ahora: datetime) -> ResultadoEvaluacion:
    """Hoy no hace nada (la evaluación llega en la 5b). `ahora` es la hora de la corrida, en UTC."""
    return ResultadoEvaluacion(estado="listo")
