"""Alertas push: suscripción, baja (FRA-353) y aviso de prueba (FRA-354).

POST /api/alertas/suscripcion  -> 201 {id, zona}
POST /api/alertas/baja         -> 204
POST /api/alertas/prueba       -> 200 {enviada}

Falla cerrado: sin Upstash, sin clave VAPID usable o con el tope de suscripciones alcanzado responde 503,
nunca 500. No se loguea el endpoint, las claves, el id ni el cuerpo (el middleware de requests solo
registra método, ruta y estado).
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from py_vapid import Vapid

from app.core.rate_limit import limiter
from app.core.upstash import UpstashRedis, UpstashUnavailableError, get_redis
from app.schemas.alertas import (
    BajaRequest,
    PruebaEnviada,
    PruebaRequest,
    SuscripcionCreada,
    SuscripcionRequest,
)
from app.services.alertas import envio
from app.services.alertas import suscripcion as svc

logger = logging.getLogger(__name__)

router = APIRouter()

_NO_DISPONIBLE = "alertas_no_disponible"
_TOPE = "alertas_tope"
_NO_ENCONTRADA = "suscripcion_no_encontrada"
_VENCIDA = "suscripcion_vencida"
_PRUEBA_RECIENTE = "prueba_reciente"
_PUSH_NO_DISPONIBLE = "push_no_disponible"


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
