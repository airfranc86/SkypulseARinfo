"""Alertas push: suscripción, baja (FRA-353), aviso de prueba (FRA-354) y evaluación programada (FRA-355).

POST /api/alertas/suscripcion  -> 201 {id, zona}
POST /api/alertas/baja         -> 204
POST /api/alertas/prueba       -> 200 {enviada}
POST /api/alertas/evaluar      -> 200 {estado} | 401   (lo llama QStash, firmado; ver `/evaluar` abajo)

Falla cerrado: sin Upstash, sin clave VAPID usable o con el tope de suscripciones alcanzado responde 503,
nunca 500. No se loguea el endpoint, las claves, el id ni el cuerpo (el middleware de requests solo
registra método, ruta y estado).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from py_vapid import Vapid
from starlette.requests import ClientDisconnect

from app.core.client_context import sin_clave_de_cliente
from app.core.rate_limit import limiter
from app.core.upstash import UpstashRedis, UpstashUnavailableError, get_redis
from app.schemas.alertas import (
    BajaRequest,
    PruebaEnviada,
    PruebaRequest,
    SuscripcionCreada,
    SuscripcionRequest,
)
from app.services.alertas import envio, evaluacion, firma_qstash, interruptor
from app.services.alertas import suscripcion as svc
from app.services.alertas.firma_qstash import motivo_de_rechazo

logger = logging.getLogger(__name__)

router = APIRouter()

_NO_DISPONIBLE = "alertas_no_disponible"
_TOPE = "alertas_tope"
_NO_ENCONTRADA = "suscripcion_no_encontrada"
_VENCIDA = "suscripcion_vencida"
_PRUEBA_RECIENTE = "prueba_reciente"
_PUSH_NO_DISPONIBLE = "push_no_disponible"
# Una sola respuesta para todo rechazo de /evaluar: no le dice a quien prueba qué falló.
_NO_AUTORIZADO = "no_autorizado"

# QStash manda un cuerpo de pocos bytes; más que esto no es QStash y ni se lee entero.
MAX_CUERPO_EVALUAR_BYTES = 64 * 1024


def redis_de_alertas() -> UpstashRedis:
    """El Upstash configurado en el arranque; 503 si no hay (falla cerrado)."""
    redis = get_redis()
    if redis is None:
        logger.warning("alertas: Upstash no está configurado")
        raise HTTPException(status_code=503, detail=_NO_DISPONIBLE)
    return redis


def vapid_de_alertas() -> Vapid:
    """La clave VAPID configurada, lista para firmar; 503 si falta o no sirve (falla cerrado)."""
    try:
        return envio.cargar_vapid()
    except envio.VapidNoDisponibleError as exc:
        logger.warning("alertas: no hay una clave VAPID usable")
        raise HTTPException(status_code=503, detail=_NO_DISPONIBLE) from exc


@router.post(
    "/suscripcion",
    status_code=201,
    response_model=SuscripcionCreada,
    summary="Suscribirse a las alertas push de una ciudad",
)
@limiter.limit("10/hour")
async def post_suscripcion(
    request: Request,
    payload: SuscripcionRequest,
    redis: Annotated[UpstashRedis, Depends(redis_de_alertas)],
) -> SuscripcionCreada:
    """Guarda (o renueva) la suscripción. Repetir el POST con el mismo endpoint es un upsert: devuelve el
    mismo `id`, renueva el vencimiento (180 días) y permite cambiar de ciudad."""
    suscripcion = svc.Suscripcion(
        endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh,
        auth=payload.keys.auth,
        zona=payload.zona,
    )
    try:
        sub_id = await svc.alta(redis, suscripcion)
    except svc.TopeAlcanzadoError as exc:
        logger.warning("alertas: tope de suscripciones alcanzado")
        raise HTTPException(status_code=503, detail=_TOPE) from exc
    except UpstashUnavailableError as exc:
        raise HTTPException(status_code=503, detail=_NO_DISPONIBLE) from exc
    return SuscripcionCreada(id=sub_id, zona=suscripcion.zona)


@router.post(
    "/baja",
    status_code=204,
    summary="Darse de baja de las alertas push",
)
@limiter.limit("10/hour")
async def post_baja(
    request: Request,
    payload: BajaRequest,
    redis: Annotated[UpstashRedis, Depends(redis_de_alertas)],
) -> Response:
    """Borra la suscripción por `id`. Es idempotente: un `id` desconocido también responde 204."""
    try:
        await svc.baja(redis, payload.id)
    except UpstashUnavailableError as exc:
        raise HTTPException(status_code=503, detail=_NO_DISPONIBLE) from exc
    return Response(status_code=204)


@router.post(
    "/prueba",
    response_model=PruebaEnviada,
    summary="Mandar una notificación de prueba a una suscripción",
)
@limiter.limit("5/minute")
async def post_prueba(
    request: Request,
    payload: PruebaRequest,
    redis: Annotated[UpstashRedis, Depends(redis_de_alertas)],
    vapid: Annotated[Vapid, Depends(vapid_de_alertas)],
) -> PruebaEnviada:
    """Manda un aviso de prueba a la suscripción `id`, para que la persona vea cómo le van a llegar.

    Una prueba por suscripción por minuto (429 con `Retry-After`) y 5 por minuto por IP. Si el servicio push
    dice que la suscripción ya no existe responde 410 y ya la borró: hay que volver a suscribirse."""
    try:
        registro = await svc.registro_de(redis, payload.id)
        if registro is None:
            raise HTTPException(status_code=404, detail=_NO_ENCONTRADA)
        if not await envio.reservar_prueba(redis, payload.id):
            raise HTTPException(
                status_code=429,
                detail=_PRUEBA_RECIENTE,
                headers={"Retry-After": str(envio.VENTANA_PRUEBA_SEGUNDOS)},
            )
        resultado = await envio.enviar_prueba(redis, payload.id, registro, vapid=vapid)
    except UpstashUnavailableError as exc:
        raise HTTPException(status_code=503, detail=_NO_DISPONIBLE) from exc
    if resultado is envio.Resultado.VENCIDA:
        raise HTTPException(status_code=410, detail=_VENCIDA)
    if resultado is envio.Resultado.ERROR:
        raise HTTPException(status_code=502, detail=_PUSH_NO_DISPONIBLE)
    return PruebaEnviada(enviada=True)


# ---------------------------------------------------------------------------
# Evaluación programada (FRA-355): el endpoint al que llama QStash
# ---------------------------------------------------------------------------


async def _leer_cuerpo_crudo(request: Request) -> bytes | None:
    """Los bytes del cuerpo tal como llegaron (la firma cubre esos bytes, no un JSON reescrito).

    None si pasa del tope, si la longitud declarada no son dígitos ASCII, o si el cliente se desconecta.
    """
    declarado = request.headers.get("content-length")
    if declarado is not None:
        # `str.isdigit()` acepta dígitos que no son ASCII (por ejemplo "²") y `int()` no: eso era un 500.
        # Una longitud declarada que no son dígitos ASCII no es una longitud: mismo 401 que un cuerpo enorme.
        if not (declarado.isascii() and declarado.isdigit()) or int(declarado) > MAX_CUERPO_EVALUAR_BYTES:
            return None
    cuerpo = bytearray()
    try:
        async for trozo in request.stream():
            cuerpo += trozo
            if len(cuerpo) > MAX_CUERPO_EVALUAR_BYTES:
                return None
    except ClientDisconnect:
        return None  # nadie espera la respuesta: se corta sin ruido
    return bytes(cuerpo)


async def _motivo_de_rechazo_del_pedido(request: Request) -> str | None:
    """None si el pedido trae una firma de QStash válida para su cuerpo crudo; si no, el código fijo del motivo."""
    firma = request.headers.get("upstash-signature")
    if not firma or not firma.strip():
        return firma_qstash.MOTIVO_SIN_CABECERA
    if len(firma) > firma_qstash.MAX_LARGO_FIRMA:
        return firma_qstash.MOTIVO_FIRMA_LARGA  # antes de leer el cuerpo: no hay nada que valga la pena leer
    cuerpo = await _leer_cuerpo_crudo(request)
    if cuerpo is None:
        return firma_qstash.MOTIVO_CUERPO
    return motivo_de_rechazo(firma, cuerpo)


@router.post(
    "/evaluar",
    summary="Evaluación programada de alertas (lo llama QStash, firmado)",
    include_in_schema=False,
)
@limiter.limit("30/minute")
async def post_evaluar(request: Request) -> dict[str, str]:
    """Verifica la firma de QStash sobre el cuerpo crudo y, solo entonces, mira el interruptor y evalúa.

    - 401 `no_autorizado` si falta la firma o no vale (misma respuesta para toda causa; el motivo, un código
      fijo sin valores, queda solo en el registro del servidor).
    - 200 `{"estado": "apagado"}` si el envío está apagado (200 para que QStash no reintente).
    - 200 `{"estado": <resultado de la evaluación>}` si está activo (hoy `listo`; la evaluación llega en la 5b).
    """
    motivo = await _motivo_de_rechazo_del_pedido(request)
    if motivo is not None:
        logger.warning("alertas: /evaluar rechazó un pedido sin firma válida motivo=%s", motivo)
        raise HTTPException(status_code=401, detail=_NO_AUTORIZADO)
    redis = get_redis()
    with sin_clave_de_cliente():
        if not await interruptor.envio_activo(redis) or redis is None:
            return {"estado": "apagado"}
        resultado = await evaluacion.evaluar(redis, datetime.now(timezone.utc))
        return {"estado": resultado.estado}
