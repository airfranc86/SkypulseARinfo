"""Alertas push: suscripción y baja (FRA-353).

POST /api/alertas/suscripcion  -> 201 {id, zona}
POST /api/alertas/baja         -> 204

Falla cerrado: sin Upstash o con el tope de suscripciones alcanzado responde 503, nunca 500. No se
loguea el endpoint, las claves ni el cuerpo (el middleware de requests solo registra método, ruta y estado).
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core.rate_limit import limiter
from app.core.upstash import UpstashRedis, UpstashUnavailableError, get_redis
from app.schemas.alertas import BajaRequest, SuscripcionCreada, SuscripcionRequest
from app.services.alertas import suscripcion as svc

logger = logging.getLogger(__name__)

router = APIRouter()

_NO_DISPONIBLE = "alertas_no_disponible"
_TOPE = "alertas_tope"


def redis_de_alertas() -> UpstashRedis:
    """El Upstash configurado en el arranque; 503 si no hay (falla cerrado)."""
    redis = get_redis()
    if redis is None:
        logger.warning("alertas: Upstash no está configurado")
        raise HTTPException(status_code=503, detail=_NO_DISPONIBLE)
    return redis


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
