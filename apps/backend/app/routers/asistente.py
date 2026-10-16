"""`POST /api/asistente`: la pregunta a Mora (PR 2b del plan del asistente).

Este router es el "sobre de seguridad" del asistente. Cada pedido pasa, en este orden, por:

1. La bandera `asistente_enabled` (apagada por defecto): 404. Es una dependencia de la ruta y no un `if` adentro, así corre
   ANTES del límite de pedidos: con la bandera apagada nadie gasta fichas ni ve un 429. (No es "sin rastro" del todo:
   `GET` da 405, `POST` con barra final da 307, un JSON roto da 422 y la ruta figura en `/openapi.json`.)
2. El límite de 6 pedidos por minuto por cliente (`client_key`, que no se puede falsificar).
3. Que haya Upstash y un secreto de cupos válido (`asistente_cupo_secreto`): si no, 503 (falla cerrado).
4. El interruptor de emergencia `skypulse:asistente:apagado` en Upstash (con 60 s de memoria): 503.
5. Una sola pregunta en vuelo por cliente (en memoria; Render corre una instancia): 429.
6. Los cupos diarios, por cliente y globales (`services/asistente/cupos.py`): 429 o 503, con `Retry-After`.
7. Los datos (`ProveedorDeFuentes`) y el modelo (`Modelo`), con un plazo total: 503 si tardan o fallan.

Todo lo que no se puede atender responde 503 `asistente_no_disponible` sin detalles (nunca 500, nunca un mensaje de un
proveedor): el navegador pasa al modo degradado. Esos 503 se DEVUELVEN, no se lanzan como `HTTPException`: Sentry captura
como error toda excepción 5xx, y un interruptor puesto o un cupo agotado son estados esperados que, a 6 pedidos por minuto,
agotarían la cuota de errores de todo el backend. Los 429 sí se lanzan (Sentry no los captura).

**Privacidad:** el texto de la pregunta y el de la respuesta no se guardan ni se registran, y la IP tampoco (el log del
pedido lleva la etiqueta anónima de los cupos, ver `main.py`); hay UNA línea de log por pregunta, con el estado, los bloques
y la duración. Los logs de error no llevan `exc_info`, y Sentry corre sin cuerpos de pedido ni variables locales. Lo que
queda fuera de este módulo: la línea de "ratelimit exceeded" de slowapi escribe la IP.

Los datos y el modelo entran por dependencias para poder reemplazarlos: hoy son `FuentesDeCache` (lee solo de las cachés,
sin provocar pedidos de red; PR 2c) y `ModeloFalso` (la Fase 3 pone el proveedor real).
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.rate_limit import client_key, limiter
from app.core.upstash import UpstashRedis, UpstashUnavailableError, get_redis
from app.schemas.asistente import PreguntaRequest, RespuestaAsistente
from app.services.asistente import cupos, interruptor
from app.services.asistente.enrutador import enrutar
from app.services.asistente.fuentes import ProveedorDeFuentes
from app.services.asistente.fuentes_cache import FuentesDeCache
from app.services.asistente.hoja_datos import Fuentes
from app.services.asistente.modelo import Modelo, ModeloFalso
from app.services.asistente.nucleo import Respuesta, responder

logger = logging.getLogger(__name__)

router = APIRouter()

_NO_DISPONIBLE = "asistente_no_disponible"
_CUPO_DIARIO = "cupo_diario"
_EN_CURSO = "pregunta_en_curso"
_ESPERA_APAGADO_SEGUNDOS = 60  # lo que tarda en notarse el interruptor (su memoria)
_ESPERA_EN_CURSO_SEGUNDOS = 5

# Los clientes con una pregunta andando. Es de proceso: con más de una instancia no se garantizaría (hoy hay una).
_en_vuelo: set[str] = set()


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def asistente_habilitado() -> None:
    """404 mientras la bandera esté apagada: la ruta se comporta como si no existiera."""
    if not settings.asistente_enabled:
        raise HTTPException(status_code=404)


def redis_del_asistente() -> UpstashRedis | None:
    """El Upstash configurado en el arranque, o `None`: el endpoint responde 503 (falla cerrado)."""
    return get_redis()


def fuentes_del_asistente() -> ProveedorDeFuentes:
    return FuentesDeCache()


def modelo_del_asistente() -> Modelo:
    return ModeloFalso()


def _no_disponible(reintentar_en: int) -> JSONResponse:
    """503 como respuesta (no como excepción: ver el docstring del módulo)."""
    return JSONResponse(
        status_code=503, content={"detail": _NO_DISPONIBLE}, headers={"Retry-After": str(max(1, reintentar_en))},
    )


async def _contestar(payload: PreguntaRequest, fuentes: ProveedorDeFuentes, modelo: Modelo, ahora: datetime) -> Respuesta:
    ruta = enrutar(payload.pregunta, payload.pagina)
    datos = Fuentes()  # un tema fuera de alcance no pide datos
    if ruta.bloques:
        datos = await fuentes.obtener(ruta.bloques, lat=payload.lat, lon=payload.lon, ahora_utc=ahora)
    return await responder(payload.pregunta, datos, modelo, pagina=payload.pagina, ahora_utc=ahora, ruta=ruta)


@router.post(
    "",
    response_model=RespuestaAsistente,
    summary="Preguntarle a Mora sobre el clima",
    dependencies=[Depends(asistente_habilitado)],
)
@limiter.limit("6/minute")
async def post_asistente(
    request: Request,
    payload: PreguntaRequest,
    redis: Annotated[UpstashRedis | None, Depends(redis_del_asistente)],
    fuentes: Annotated[ProveedorDeFuentes, Depends(fuentes_del_asistente)],
    modelo: Annotated[Modelo, Depends(modelo_del_asistente)],
) -> RespuestaAsistente | JSONResponse:
    ahora = _ahora_utc()
    cliente = client_key(request)
    secreto = settings.asistente_cupo_secreto

    if redis is None:
        logger.warning("asistente: Upstash no está configurado")
        return _no_disponible(_ESPERA_APAGADO_SEGUNDOS)
    if not cupos.secreto_valido(secreto):
        logger.warning("asistente: falta ASISTENTE_CUPO_SECRETO (16 caracteres o más); no se atiende")
        return _no_disponible(_ESPERA_APAGADO_SEGUNDOS)
    if not await interruptor.asistente_permitido(redis):
        return _no_disponible(_ESPERA_APAGADO_SEGUNDOS)

    if cliente in _en_vuelo:
        raise HTTPException(status_code=429, detail=_EN_CURSO, headers={"Retry-After": str(_ESPERA_EN_CURSO_SEGUNDOS)})
    _en_vuelo.add(cliente)
    try:
        try:
            cupo = await cupos.consumir_cupo(
                redis, cliente, ahora,
                cupo_cliente=settings.asistente_cupo_cliente_dia, cupo_global=settings.asistente_cupo_global_dia,
                secreto=secreto,
            )
        except UpstashUnavailableError:
            logger.warning("asistente: no se pudieron contar los cupos")
            return _no_disponible(_ESPERA_APAGADO_SEGUNDOS)
        if not cupo.permitido:
            logger.info("asistente: cupo agotado motivo=%s", cupo.motivo)
            if cupo.motivo == "cliente":
                raise HTTPException(
                    status_code=429, detail=_CUPO_DIARIO, headers={"Retry-After": str(cupo.reintentar_en_segundos)},
                )
            return _no_disponible(cupo.reintentar_en_segundos)

        inicio = time.monotonic()
        try:
            respuesta = await asyncio.wait_for(
                _contestar(payload, fuentes, modelo, ahora), timeout=settings.asistente_timeout_segundos,
            )
        except asyncio.TimeoutError:
            logger.warning("asistente: se pasó el plazo de %.0f s", settings.asistente_timeout_segundos)
            return _no_disponible(_ESPERA_APAGADO_SEGUNDOS)
        except Exception as exc:  # noqa: BLE001 - lo que falle (datos o modelo) es "no disponible"; sin mensaje ni traza
            logger.warning("asistente: falló la respuesta (%s)", type(exc).__name__)
            return _no_disponible(_ESPERA_APAGADO_SEGUNDOS)
    finally:
        _en_vuelo.discard(cliente)

    logger.info(
        "asistente: estado=%s bloques=%s ms=%d",
        respuesta.estado, ",".join(respuesta.bloques) or "-", (time.monotonic() - inicio) * 1000,
    )
    return RespuestaAsistente(estado=respuesta.estado, texto=respuesta.texto)
