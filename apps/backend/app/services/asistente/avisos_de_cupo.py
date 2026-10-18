"""Avisos a Sentry cuando el sitio va gastando el cupo diario del asistente: al 80, al 95 y al 100 %.

Reutiliza el notificador de umbrales de CheckWX (`app.core.notifier.maybe_notify`), con nombre, tipo y vencimiento propios. El
cupo global se cuenta por día de Argentina en Upstash (`cupos.py`); cada umbral avisa UNA vez por día. La marca de "ya avisé" vive
en Upstash (sobrevive a un reinicio) y además se recuerda en memoria, para no preguntarle a Upstash en cada pregunta una vez
pasado el 80 %. Un aviso que falla (Upstash caído, Sentry caído, un dato raro) nunca rompe la respuesta: se registra y se
reintenta con la próxima pregunta.
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.core.notifier import maybe_notify, umbral_cruzado
from app.core.upstash import UpstashRedis
from app.services.asistente import cupos

logger = logging.getLogger(__name__)

NOMBRE = "Mora"
TIPO = "asistente_quota"
PREFIJO_MARCA = "skypulse:asistente:alerta"

# Los avisos ya dados en este proceso: (día, umbral). Solo guarda el día de hoy, así que nunca crece.
_avisados: set[tuple[str, int]] = set()


def olvidar() -> None:
    """Borra lo recordado en memoria. Lo usan las pruebas; en producción se limpia solo al cambiar el día."""
    _avisados.clear()


class _MarcasEnRedis:
    """Las dos operaciones que `maybe_notify` le pide a un contador, sobre Upstash: una marca por día y umbral."""

    def __init__(self, redis: UpstashRedis) -> None:
        self._redis = redis

    @staticmethod
    def _clave(ciclo: str, umbral: int) -> str:
        return f"{PREFIJO_MARCA}:{ciclo}:{umbral}"

    async def alert_already_sent(self, cycle: str, threshold: int) -> bool:
        return await self._redis.get(self._clave(cycle, threshold)) is not None

    async def mark_alert_sent(self, cycle: str, threshold: int, ttl_seconds: int) -> None:
        await self._redis.set_nx(self._clave(cycle, threshold), "1", ttl_seconds)


async def avisar_si_corresponde(redis: UpstashRedis, ahora: datetime, usados: int, tope: int) -> None:
    """Avisa a Sentry si `usados` de `tope` preguntas del sitio cruzó un umbral que hoy todavía no avisó. Nunca levanta."""
    try:
        umbral = umbral_cruzado(usados, tope)
        if umbral is None:
            return
        dia = cupos.dia_de_argentina(ahora)
        if (dia, umbral) in _avisados:
            return
        await maybe_notify(
            dia, usados, _MarcasEnRedis(redis), tope, name=NOMBRE, kind=TIPO, ttl=cupos.RETENCION_SEGUNDOS,
        )
        _avisados.difference_update({marca for marca in _avisados if marca[0] != dia})
        _avisados.add((dia, umbral))
    except Exception as exc:  # noqa: BLE001 - un aviso nunca puede romper una respuesta; se reintenta con la próxima pregunta
        logger.warning("asistente: no se pudo avisar del cupo (%s)", type(exc).__name__)
