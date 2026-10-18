"""Cupos diarios del asistente: cuántas preguntas puede hacer cada cliente por día y cuántas el sitio entero.

Cada pregunta que llega al modelo gasta cupo, aunque después falle: lo que se cuida es el costo y el abuso, no el
éxito. El día es el de Argentina (UTC-3 fijo, igual que `alertas/metricas.py`): a la medianoche de allá los
contadores vuelven a cero. Todo vive en UN hash de Upstash por día, `skypulse:asistente:cupo:{YYYY-MM-DD}`:

    g           las preguntas del día, de todos los clientes
    c:{hmac16}  las de un cliente: los primeros 16 caracteres del HMAC-SHA256 de su clave con un secreto del servicio
                (`asistente_cupo_secreto`); nunca la IP ni la clave

El secreto es lo que impide revertir el campo: un SHA-256 pelado de una IPv4 se invierte probando las 2^32 direcciones,
y con acceso a la consola de Upstash eso sería leer IPs. Sin un secreto válido (16 caracteres o más) no se cuenta nada.

`HINCRBY` es atómico en el servidor (dos pedidos a la vez no pierden cuentas) y `EXPIRE ... NX` pone el vencimiento una
sola vez, sin estirarlo. No se usa `INCR` + `EXPIRE` porque no es atómico.

Se cuenta primero al cliente: quien ya se pasó de su cupo no gasta el cupo global, así que un solo cliente insistiendo
no puede dejar sin servicio a los demás. Si Upstash no responde, el error sube: el router lo responde con 503 (falla
cerrado, porque sin contador no hay forma de cuidar el costo). Este módulo no lee el reloj: `ahora` lo pone quien llama.

Los clientes que ya se pasaron de su cupo (y el cupo global agotado) se recuerdan EN MEMORIA hasta la medianoche de
Argentina (Render corre una instancia): sus pedidos siguientes se rechazan sin ir a Upstash. Sin eso, un solo cliente
insistiendo a 6 por minuto gastaría unos 17.000 comandos por día del plan gratuito, que comparten las alertas. La
memoria tiene tope; pasado el tope se sigue contando en Upstash, que es la fuente de verdad.

Lo que NO resuelve (decisión de costo, no un descuido): el cupo global de 100 se puede agotar con pocas claves
(100 / 10 = 10 clientes), y los clientes que comparten una clave (varios usuarios detrás de un mismo CGNAT móvil, o la
clave `unverified`) comparten también su cupo diario.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal

from app.core.upstash import UpstashRedis

PREFIJO = "skypulse:asistente:cupo"
CAMPO_GLOBAL = "g"
# Dos días: sobra para que ningún contador del día de hoy desaparezca mientras todavía se usa.
RETENCION_SEGUNDOS = 2 * 24 * 60 * 60

_AR = timezone(timedelta(hours=-3))  # Argentina no tiene horario de verano

SECRETO_MINIMO = 16  # caracteres
MAX_AGOTADOS_EN_MEMORIA = 10_000


@dataclass
class _Agotados:
    dia: str = ""
    clientes: set[str] = field(default_factory=set)
    sitio: bool = False


_agotados = _Agotados()


def olvidar() -> None:
    """Borra la memoria de agotados. Lo usan las pruebas; en producción se borra sola al cambiar el día."""
    _agotados.dia, _agotados.sitio = "", False
    _agotados.clientes.clear()


def _agotados_de(clave_dia: str) -> _Agotados:
    if _agotados.dia != clave_dia:
        olvidar()
        _agotados.dia = clave_dia
    return _agotados


@dataclass(frozen=True)
class ResultadoCupo:
    permitido: bool
    motivo: Literal["cliente", "global"] | None = None
    reintentar_en_segundos: int = 0  # hasta la medianoche de Argentina; solo cuando no se permite
    del_sitio: int | None = None  # cuántas preguntas lleva hoy el sitio entero; None si esta ni siquiera llegó a contarse


def _en_argentina(ahora: datetime) -> datetime:
    if ahora.tzinfo is None:
        raise ValueError("ahora necesita zona horaria")
    return ahora.astimezone(_AR)


def dia_de_argentina(ahora: datetime) -> str:
    """El día de Argentina de `ahora`, como `2026-10-17`."""
    return _en_argentina(ahora).date().isoformat()


def clave_del_dia(ahora: datetime) -> str:
    return f"{PREFIJO}:{dia_de_argentina(ahora)}"


def secreto_valido(secreto: str) -> bool:
    return isinstance(secreto, str) and len(secreto) >= SECRETO_MINIMO


def campo_del_cliente(clave_cliente: str, secreto: str) -> str:
    """El campo del cliente en el hash del día: HMAC-SHA256 de su clave con el secreto del servicio."""
    if not secreto_valido(secreto):
        raise ValueError(f"el secreto de los cupos necesita al menos {SECRETO_MINIMO} caracteres")
    firma = hmac.new(secreto.encode("utf-8"), clave_cliente.encode("utf-8"), hashlib.sha256)
    return "c:" + firma.hexdigest()[:16]


def etiqueta_del_cliente(clave_cliente: str, secreto: str) -> str:
    """Lo que se escribe en el log en lugar de la IP: el mismo campo anónimo de los cupos, o `-` si no hay secreto."""
    return campo_del_cliente(clave_cliente, secreto) if secreto_valido(secreto) else "-"


def segundos_hasta_medianoche(ahora: datetime) -> int:
    """Segundos que faltan para el próximo día de Argentina; nunca 0 (un `Retry-After: 0` invita a reintentar ya)."""
    local = _en_argentina(ahora)
    medianoche = local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return max(1, int((medianoche - local).total_seconds()))


async def consumir_cupo(
    redis: UpstashRedis, clave_cliente: str, ahora: datetime, *, cupo_cliente: int, cupo_global: int, secreto: str,
) -> ResultadoCupo:
    """Cuenta una pregunta del cliente y del sitio y dice si puede seguir. `ValueError` si el secreto no sirve."""
    clave = clave_del_dia(ahora)
    campo = campo_del_cliente(clave_cliente, secreto)
    agotados = _agotados_de(clave)
    if campo in agotados.clientes:
        return ResultadoCupo(False, "cliente", segundos_hasta_medianoche(ahora))
    if agotados.sitio:
        return ResultadoCupo(False, "global", segundos_hasta_medianoche(ahora))

    del_cliente = await redis.hincrby(clave, campo, 1)
    await redis.expire_si_falta(clave, RETENCION_SEGUNDOS)  # idempotente: solo la primera vez pone el vencimiento
    if del_cliente > cupo_cliente:
        if len(agotados.clientes) < MAX_AGOTADOS_EN_MEMORIA:
            agotados.clientes.add(campo)
        return ResultadoCupo(False, "cliente", segundos_hasta_medianoche(ahora))
    del_sitio = await redis.hincrby(clave, CAMPO_GLOBAL, 1)
    if del_sitio > cupo_global:
        agotados.sitio = True
        return ResultadoCupo(False, "global", segundos_hasta_medianoche(ahora), del_sitio)
    return ResultadoCupo(True, del_sitio=del_sitio)
