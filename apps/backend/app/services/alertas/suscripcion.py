"""Suscripciones Web Push: validación anti-SSRF, id y alta/baja en Upstash (FRA-353).

El `endpoint` lo manda el navegador y más adelante el backend le hace un POST (FRA-354). Si aceptáramos
cualquier URL, un atacante nos haría pedir recursos internos (p. ej. la metadata de la nube). Por eso:

- solo se aceptan los hosts de los servicios push reales (lista cerrada, no heurística);
- todo se valida ANTES de tocar Upstash (`Suscripcion` valida al construirse);
- el endpoint, las claves y los ids no se loguean ni viajan en la URL de ningún pedido.

Datos en Upstash:
    alertas:sub:{id}     JSON de la suscripción, TTL 180 días (se renueva al repetir el POST)
    alertas:zona:{slug}  set de ids suscriptos a esa ciudad
    alertas:zonas        set de slugs con al menos un suscriptor
    alertas:ids          set de todos los ids (un SCARD alcanza para el tope)

Los ids de suscripciones vencidas (TTL) quedan en los sets hasta que alguien los saque: quien envíe las
notificaciones (FRA-355) llama a `limpiar_id_vencido` cuando el GET de `alertas:sub:{id}` devuelve null.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import ipaddress
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit

from app.core.upstash import UpstashRedis
from app.services.alertas.zonas import zona_por_slug

TOPE_SUSCRIPCIONES = 5000
TTL_SEGUNDOS = 180 * 24 * 60 * 60  # 15.552.000 s

MAX_LARGO_ENDPOINT = 2048
LARGO_P256DH = 65  # punto P-256 sin comprimir: 0x04 + X (32) + Y (32)
LARGO_AUTH = 16
LARGO_ID = 22

# Los servicios push de los navegadores. Nada más.
_HOSTS_EXACTOS = frozenset({"fcm.googleapis.com", "updates.push.services.mozilla.com"})
# Con el punto inicial: `evilpush.apple.com` no termina en `.push.apple.com`.
_SUFIJOS = (".push.apple.com", ".notify.windows.com")

PATRON_ID = re.compile(r"[A-Za-z0-9_-]{22}")

# Todo lo que no sea ASCII imprimible sin espacio (espacios, controles, DEL, no ASCII) y la barra invertida.
_PROHIBIDO = re.compile(r"[^\x21-\x7e]|\\")
_ETIQUETA_DNS = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_ETIQUETA_NUMERICA = re.compile(
    r"0x[0-9a-f]*|[0-9]+"
)  # decimal, hexadecimal u octal: formas de IP
_BASE64URL = re.compile(r"[A-Za-z0-9_-]+={0,2}")

_CLAVE_IDS = "alertas:ids"
_CLAVE_ZONAS = "alertas:zonas"


class SuscripcionInvalida(ValueError):
    """Dato rechazado. El mensaje es un código fijo: nunca incluye lo que mandó el cliente."""


class TopeAlcanzadoError(Exception):
    """Ya hay `TOPE_SUSCRIPCIONES` suscripciones y esta es nueva."""


# ---------------------------------------------------------------------------
# Validación
# ---------------------------------------------------------------------------


def _es_literal_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return True
    return all(_ETIQUETA_NUMERICA.fullmatch(etiqueta) for etiqueta in host.split("."))


def _validar_host(host: str) -> None:
    if len(host) > 253 or not all(_ETIQUETA_DNS.fullmatch(e) for e in host.split(".")):
        raise SuscripcionInvalida(
            "endpoint_invalido"
        )  # incluye punto final, etiquetas vacías, %, _
    if _es_literal_ip(host):
        raise SuscripcionInvalida("endpoint_invalido")
    if host not in _HOSTS_EXACTOS and not host.endswith(_SUFIJOS):
        raise SuscripcionInvalida("endpoint_invalido")


def validar_endpoint(endpoint: str) -> str:
    """Devuelve el endpoint tal cual si es https hacia un servicio push conocido; si no, lo rechaza."""
    if (
        not isinstance(endpoint, str)
        or not endpoint
        or len(endpoint) > MAX_LARGO_ENDPOINT
    ):
        raise SuscripcionInvalida("endpoint_invalido")
    # Antes de parsear: urlsplit descarta tabs y saltos de línea en silencio.
    if (
        _PROHIBIDO.search(endpoint)
        or "#" in endpoint
        or not endpoint.startswith("https://")
    ):
        raise SuscripcionInvalida("endpoint_invalido")
    try:
        partes = urlsplit(endpoint)
        host = partes.hostname
    except ValueError as exc:
        raise SuscripcionInvalida("endpoint_invalido") from exc
    # El netloc debe ser exactamente `host` o `host:443`: descarta usuario/clave, otros puertos, un `:`
    # vacío, corchetes y mayúsculas (`.hostname` pasa a minúsculas, el netloc no).
    if not host or partes.netloc not in (host, f"{host}:443"):
        raise SuscripcionInvalida("endpoint_invalido")
    _validar_host(host)
    return endpoint


def _decodificar_base64url(value: str, largo: int) -> bytes:
    """Decodifica base64url (relleno opcional) exigiendo `largo` bytes y la forma canónica."""
    if (
        not isinstance(value, str)
        or len(value) > 100
        or not _BASE64URL.fullmatch(value)
    ):
        raise SuscripcionInvalida("clave_invalida")
    sin_relleno = value.rstrip("=")
    if sin_relleno != value and len(value) % 4 != 0:
        raise SuscripcionInvalida("clave_invalida")
    try:
        datos = base64.urlsafe_b64decode(sin_relleno + "=" * (-len(sin_relleno) % 4))
    except (binascii.Error, ValueError) as exc:
        raise SuscripcionInvalida("clave_invalida") from exc
    canonico = base64.urlsafe_b64encode(datos).decode().rstrip("=")
    if len(datos) != largo or canonico != sin_relleno:
        raise SuscripcionInvalida("clave_invalida")
    return datos


def validar_p256dh(value: str) -> str:
    if _decodificar_base64url(value, LARGO_P256DH)[0] != 0x04:
        raise SuscripcionInvalida("clave_invalida")
    return value


def validar_auth(value: str) -> str:
    _decodificar_base64url(value, LARGO_AUTH)
    return value


def validar_zona(slug: str) -> str:
    if not isinstance(slug, str) or zona_por_slug(slug) is None:
        raise SuscripcionInvalida("zona_invalida")
    return slug


def id_de_endpoint(endpoint: str) -> str:
    """Los primeros 22 caracteres del SHA-256 del endpoint en base64url, sin relleno.

    El SHA-256 mide 43 caracteres en base64url; 22 son 132 bits, de sobra para no chocar, y el id
    queda corto en las claves de Redis. El mismo endpoint da siempre el mismo id: repetir el alta es un upsert.
    """
    digest = hashlib.sha256(endpoint.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")[:LARGO_ID]


@dataclass(frozen=True)
class Suscripcion:
    """Una suscripción ya validada: no se puede construir con datos que `alta` no aceptaría."""

    endpoint: str
    p256dh: str
    auth: str
    zona: str

    def __post_init__(self) -> None:
        validar_endpoint(self.endpoint)
        validar_p256dh(self.p256dh)
        validar_auth(self.auth)
        validar_zona(self.zona)


# ---------------------------------------------------------------------------
# Alta y baja
# ---------------------------------------------------------------------------


def _clave_sub(sub_id: str) -> str:
    return f"alertas:sub:{sub_id}"


def _clave_zona(slug: str) -> str:
    return f"alertas:zona:{slug}"


def _zona_guardada(registro: str | None) -> str | None:
    """La zona del registro guardado; None si no existe o no se puede leer (no es motivo de error)."""
    if registro is None:
        return None
    try:
        datos = json.loads(registro)
    except ValueError:
        return None
    zona = datos.get("zona") if isinstance(datos, dict) else None
    return zona if isinstance(zona, str) else None


async def alta(redis: UpstashRedis, suscripcion: Suscripcion) -> str:
    """Guarda (o renueva) la suscripción y devuelve su id.

    Raises:
        TopeAlcanzadoError: es nueva y ya hay `TOPE_SUSCRIPCIONES`. Una existente siempre puede renovarse.
        UpstashUnavailableError: Upstash no respondió.
    """
    sub_id = id_de_endpoint(suscripcion.endpoint)
    clave = _clave_sub(sub_id)
    previo = await redis.read(clave)
    if previo is None and await redis.scard(_CLAVE_IDS) >= TOPE_SUSCRIPCIONES:
        raise TopeAlcanzadoError

    registro = json.dumps(
        {
            "endpoint": suscripcion.endpoint,
            "p256dh": suscripcion.p256dh,
            "auth": suscripcion.auth,
            "zona": suscripcion.zona,
            "actualizada": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        separators=(",", ":"),
    )
    await redis.set(clave, registro, ex=TTL_SEGUNDOS)
    await redis.sadd(_clave_zona(suscripcion.zona), sub_id)
    await redis.sadd(_CLAVE_ZONAS, suscripcion.zona)
    await redis.sadd(_CLAVE_IDS, sub_id)

    zona_previa = _zona_guardada(previo)
    if zona_previa is not None and zona_previa != suscripcion.zona:
        await redis.srem(_clave_zona(zona_previa), sub_id)
    return sub_id


async def baja(redis: UpstashRedis, sub_id: str) -> None:
    """Borra la suscripción y la saca de los índices. Idempotente: un id desconocido no es un error."""
    if not isinstance(sub_id, str) or not PATRON_ID.fullmatch(sub_id):
        raise SuscripcionInvalida("id_invalido")
    clave = _clave_sub(sub_id)
    zona = _zona_guardada(await redis.read(clave))
    await redis.delete(clave)
    await redis.srem(_CLAVE_IDS, sub_id)
    if zona is not None:
        await redis.srem(_clave_zona(zona), sub_id)


async def registro_de(redis: UpstashRedis, sub_id: str) -> str | None:
    """El JSON guardado de una suscripción tal cual (para `envio.enviar`); None si no existe o venció.

    Raises:
        SuscripcionInvalida: el id no tiene la forma válida (no se toca Upstash).
        UpstashUnavailableError: Upstash no respondió.
    """
    if not isinstance(sub_id, str) or not PATRON_ID.fullmatch(sub_id):
        raise SuscripcionInvalida("id_invalido")
    return await redis.read(_clave_sub(sub_id))


async def limpiar_id_vencido(
    redis: UpstashRedis, sub_id: str, zona: str | None = None
) -> bool:
    """Saca de los índices un id cuyo registro ya no existe (venció el TTL de 180 días).

    `zona` es el slug del set donde apareció el id; sin él solo se limpia `alertas:ids`, porque con el
    registro borrado ya no hay de dónde leer la zona. Vuelve a leer el registro antes de quitar nada: si
    alguien se resuscribió entre la lectura de quien llama y esta limpieza, no se toca. Devuelve True si
    quitó el id y False si el registro existe.

    Raises:
        SuscripcionInvalida: el id o la zona no tienen la forma válida (no se toca Upstash).
        UpstashUnavailableError: Upstash no respondió.
    """
    if not isinstance(sub_id, str) or not PATRON_ID.fullmatch(sub_id):
        raise SuscripcionInvalida("id_invalido")
    if zona is not None:
        validar_zona(zona)
    if await redis.read(_clave_sub(sub_id)) is not None:
        return False
    await redis.srem(_CLAVE_IDS, sub_id)
    if zona is not None:
        await redis.srem(_clave_zona(zona), sub_id)
    return True
