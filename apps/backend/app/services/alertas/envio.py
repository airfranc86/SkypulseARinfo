"""Envío de notificaciones Web Push a una suscripción (FRA-354).

`enviar` manda UN mensaje a UNA suscripción y cuenta lo que pasó (`Resultado`). Quién recibe qué y cuándo
(el envío programado, la prueba) es de quien llama. Reglas que no se relajan:

- TTL explícito y positivo. Con TTL 0 Apple rechaza el mensaje, y `pywebpush` lo manda en 0 si no se le dice
  otra cosa (`ttl=0` por defecto).
- Claims VAPID nuevos en cada envío: `pywebpush` escribe `aud` (el servicio push) y `exp` en el dict que
  recibe, así que reusarlo le mandaría a un servicio el `aud` del anterior.
- `Urgency: high` (un aviso de tormenta no puede esperar a que el teléfono salga del ahorro de batería) y
  `Topic` (un mensaje nuevo reemplaza al anterior de la misma ciudad y día que aún no se entregó).
- Sin redirecciones y con timeout: el endpoint lo mandó un navegador; aunque pasó la lista de hosts conocidos
  al darse de alta, una respuesta de un servicio comprometido no puede llevarnos a otro lado.
- 404 y 410 (la suscripción ya no existe) borran el registro; 429, 5xx, errores de red y cualquier otro
  rechazo NO: son del servicio push o de este envío, no de la suscripción.
- Nada sensible llega a un log: ni el endpoint, ni las claves, ni el mensaje, ni la clave VAPID. El texto de
  una `WebPushException` o de un error de `requests` trae el cuerpo de la respuesta o la URL del pedido,
  así que solo se registra el nombre de la clase y el estado HTTP.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
from datetime import date, datetime, timezone
from enum import Enum

import requests
from cryptography.hazmat.primitives.asymmetric import ec
from py_vapid import Vapid
from pywebpush import WebPushException, webpush

from app.core.config import settings
from app.core.upstash import UpstashRedis
from app.services.alertas import suscripcion as svc
from app.services.alertas.textos import Mensaje, texto_prueba
from app.services.alertas.zonas import zona_por_slug

logger = logging.getLogger(__name__)

# urllib3 registra a nivel DEBUG cada pedido con su ruta (`POST /fcm/send/<token>`), y la ruta de un endpoint
# push es un secreto. LOG_LEVEL=DEBUG baja el nivel de toda la app: este tope lo deja fuera.
logging.getLogger("urllib3").setLevel(logging.INFO)

# Adonde lleva tocar la notificación. Todavía no existe la página de alertas: por ahora, la portada.
URL_ALERTAS = "https://skypulse-ar.vercel.app/"

# Cuánto guarda el servicio push un mensaje que no pudo entregar (teléfono apagado o sin señal). Un aviso de
# tormenta pierde sentido pasado el día: 12 h. La prueba, en cambio, se espera "ya": 5 minutos.
TTL_ALERTA_SEGUNDOS = 12 * 60 * 60
TTL_PRUEBA_SEGUNDOS = 5 * 60

# Un servicio que no contesta no puede dejar colgado el envío (ni el hilo que lo corre).
TIMEOUT_SEGUNDOS = 10.0

# Un mensaje push cifrado (aes128gcm) cabe en 4096 bytes; el encabezado ECE ocupa 86, el delimitador 1 y la
# etiqueta de autenticación 16. Quedan 3993 para el texto: medido, no supuesto (ver el test del tamaño).
MAX_PAYLOAD_BYTES = 4096 - 86 - 1 - 16

# Tags de la notificación: una nueva con el mismo tag reemplaza a la anterior en vez de apilarse.
TAG_ALERTA = "skypulse-alerta"
TAG_PRUEBA = "skypulse-prueba"

VENTANA_PRUEBA_SEGUNDOS = 60  # una prueba por suscripción por minuto

_LARGO_TOPIC = 32  # RFC 8030: hasta 32 caracteres del alfabeto base64url
# Solo para probar que la clave firma al cargarla; en un envío real el `aud` es el del endpoint.
_AUD_DE_COMPROBACION = "https://fcm.googleapis.com"


class Resultado(Enum):
    ENVIADA = "ok"  # el servicio push aceptó el mensaje (2xx)
    VENCIDA = "gone"  # 404/410: la suscripción ya no existe y se borró
    ERROR = "error"  # no se pudo enviar; la suscripción sigue guardada


class VapidNoDisponibleError(Exception):
    """No hay una clave VAPID usable. El mensaje es un código fijo: nunca incluye la clave."""


# ---------------------------------------------------------------------------
# Clave VAPID
# ---------------------------------------------------------------------------


def cargar_vapid(clave: str | None = None) -> Vapid:
    """La clave privada VAPID lista para firmar, de `settings.vapid_private_key` (o de `clave`).

    Formatos: los 32 bytes crudos en base64url (el corto, el que se pega en Render), la clave en DER base64,
    o un PEM (con saltos de línea reales o escritos como `\\n`). Prueba firmar con el `sub` configurado, así
    que una clave o un contacto inservibles fallan acá y no en el primer envío.

    Raises:
        VapidNoDisponibleError: sin clave, mal formada, de otra curva que P-256, o con un `sub` inválido.
    """
    texto = (settings.vapid_private_key if clave is None else clave).strip()
    if not texto:
        raise VapidNoDisponibleError("vapid_sin_clave")
    try:
        if "-----BEGIN" in texto:
            vapid = Vapid.from_pem(texto.replace("\\n", "\n").encode("utf-8"))
        else:
            vapid = Vapid.from_string(texto)
        privada = vapid.private_key
        if (
            not isinstance(privada, ec.EllipticCurvePrivateKey)
            or privada.curve.name != "secp256r1"
        ):
            raise ValueError("la clave VAPID debe ser ECDSA P-256")
        vapid.sign({"sub": settings.vapid_subject, "aud": _AUD_DE_COMPROBACION})
    except Exception as exc:  # noqa: BLE001
        # Solo la clase: el texto del error de la librería podría traer parte de la clave.
        logger.warning(
            "alertas: la clave VAPID no se pudo usar exc_type=%s", type(exc).__name__
        )
        # Sentry adjunta las variables locales de cada frame del traceback: que ninguna lleve la clave.
        texto = clave = None
        raise VapidNoDisponibleError("vapid_invalida") from None
    return vapid


def _claims_nuevos() -> dict[str, str | int]:
    """Un dict nuevo en cada llamada: `pywebpush` le agrega `aud` y `exp`."""
    return {"sub": settings.vapid_subject}


# ---------------------------------------------------------------------------
# Mensaje
# ---------------------------------------------------------------------------


def topic_de(zona: str, fecha: date) -> str:
    """El `Topic` RFC 8030 de una ciudad y un día: 32 caracteres base64url derivados de un SHA-256.

    El slug más largo (`san-salvador-de-jujuy`) más la fecha llega justo a 32 caracteres, sin margen (el
    prefijo de la prueba ya lo pasa) y el Topic exige el alfabeto base64url: derivarlo asegura el límite sin
    depender de los nombres de las ciudades. Misma ciudad y día, mismo Topic.
    """
    digest = hashlib.sha256(f"{zona}:{fecha:%Y-%m-%d}".encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")[:_LARGO_TOPIC]


def construir_payload(mensaje: Mensaje, *, tag: str = TAG_ALERTA) -> str:
    """El JSON que viaja cifrado: lleva los dos formatos, porque cada navegador lee uno distinto.

    - Declarativo (`web_push: 8030`, RFC 8030): Safari lo muestra sin ejecutar el service worker.
    - Campos planos `title`, `body`, `tag`, `url`: los que lee `apps/frontend/public/sw.js` en Chrome y Firefox.

    Sin datos personales: ni id, ni endpoint, ni claves. El tamaño se mide en bytes UTF-8.

    Raises:
        ValueError: el mensaje no entra en un mensaje push.
    """
    cuerpo = json.dumps(
        {
            "web_push": 8030,
            "notification": {
                "title": mensaje.titulo,
                "body": mensaje.cuerpo,
                "navigate": URL_ALERTAS,
                "lang": "es-AR",
            },
            "title": mensaje.titulo,
            "body": mensaje.cuerpo,
            "tag": tag,
            "url": URL_ALERTAS,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if len(cuerpo.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise ValueError("el mensaje no entra en una notificación push")
    return cuerpo


def leer_registro(registro: str) -> svc.Suscripcion | None:
    """La suscripción guardada, revalidada; None si el registro está corrupto o ya no pasa la validación.

    Se vuelve a validar el endpoint (lista cerrada de hosts push) porque es lo último antes de hacerle un POST:
    un registro adulterado en Upstash no puede apuntar el envío a otro lado.
    """
    try:
        datos = json.loads(registro)
        return svc.Suscripcion(
            endpoint=datos["endpoint"],
            p256dh=datos["p256dh"],
            auth=datos["auth"],
            zona=datos["zona"],
        )
    except (ValueError, KeyError, TypeError):  # SuscripcionInvalida es un ValueError
        return None


# ---------------------------------------------------------------------------
# Envío
# ---------------------------------------------------------------------------


class _SesionSinRedirecciones(requests.Session):
    """`pywebpush` no deja pasar `allow_redirects`; una sesión que lo fuerza es el único gancho."""

    def request(self, *args, **kwargs):
        kwargs["allow_redirects"] = False
        return super().request(*args, **kwargs)


def _enviar_sync(
    suscripcion: svc.Suscripcion, payload: str, vapid: Vapid, ttl: int, topic: str
) -> None:
    sesion = _SesionSinRedirecciones()
    try:
        webpush(
            subscription_info={
                "endpoint": suscripcion.endpoint,
                "keys": {"p256dh": suscripcion.p256dh, "auth": suscripcion.auth},
            },
            data=payload,
            vapid_private_key=vapid,
            vapid_claims=_claims_nuevos(),
            ttl=ttl,
            # `pywebpush` pasa su `timeout=None` por defecto tal cual a `requests`: sin esto no hay timeout.
            timeout=TIMEOUT_SEGUNDOS,
            headers={"Urgency": "high", "Topic": topic},
            requests_session=sesion,
        )
    finally:
        sesion.close()


async def enviar(
    redis: UpstashRedis,
    sub_id: str,
    registro: str,
    payload: str,
    *,
    zona: str,
    fecha: date,
    ttl: int = TTL_ALERTA_SEGUNDOS,
    vapid: Vapid | None = None,
) -> Resultado:
    """Manda `payload` a la suscripción guardada como `registro` (el JSON de `alertas:sub:{sub_id}`).

    `zona` y `fecha` solo arman el Topic. `vapid` permite cargar la clave una vez para muchos envíos
    (`cargar_vapid()`); sin él se carga de `settings` en cada llamada.

    Raises:
        ValueError: `ttl` no es positivo o `payload` no entra en un mensaje push (no se envía nada).
        VapidNoDisponibleError: no hay clave VAPID usable.
        UpstashUnavailableError: el servicio push dijo 404/410 y Upstash no dejó borrar el registro.
    """
    if ttl <= 0:
        raise ValueError("el TTL debe ser positivo: Apple rechaza TTL 0")
    if len(payload.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise ValueError("el mensaje no entra en una notificación push")
    suscripcion = leer_registro(registro)
    if suscripcion is None:
        logger.warning(
            "alertas: registro de suscripción ilegible o inválido, no se envía"
        )
        return Resultado.ERROR
    if vapid is None:
        vapid = cargar_vapid()

    try:
        await asyncio.to_thread(
            _enviar_sync, suscripcion, payload, vapid, ttl, topic_de(zona, fecha)
        )
    except WebPushException as exc:
        estado = exc.status_code
        if estado in (404, 410):
            logger.info(
                "alertas: suscripción vencida en el servicio push status=%s", estado
            )
            await svc.baja(redis, sub_id)
            return Resultado.VENCIDA
        # `pywebpush` solo da por buena la respuesta 200 a 202; cualquier otro 2xx también es una entrega.
        if estado is not None and 200 <= estado < 300:
            return Resultado.ENVIADA
        logger.warning(
            "alertas: el servicio push rechazó el envío exc_type=%s status=%s",
            type(exc).__name__,
            estado,
        )
        return Resultado.ERROR
    except Exception as exc:  # noqa: BLE001  # red, TLS, timeout, clave de la suscripción: nunca borra
        logger.warning(
            "alertas: no se pudo enviar el push exc_type=%s", type(exc).__name__
        )
        return Resultado.ERROR
    return Resultado.ENVIADA


# ---------------------------------------------------------------------------
# Aviso de prueba
# ---------------------------------------------------------------------------


def _clave_prueba(sub_id: str) -> str:
    """La clave del cupo de la prueba: un hash del id, no el id.

    `UpstashRedis.setnx_ex` manda la clave en la URL del pedido (y en el texto de sus errores), y el id de una
    suscripción es lo único que hace falta para darla de baja: no puede viajar en una URL.
    """
    digest = hashlib.sha256(sub_id.encode()).digest()
    return (
        "alertas:prueba:" + base64.urlsafe_b64encode(digest).decode().rstrip("=")[:22]
    )


async def reservar_prueba(redis: UpstashRedis, sub_id: str) -> bool:
    """Toma el cupo de una prueba para esta suscripción: True la primera vez en `VENTANA_PRUEBA_SEGUNDOS`.

    Raises:
        UpstashUnavailableError: Upstash no respondió.
    """
    return await redis.setnx_ex(_clave_prueba(sub_id), VENTANA_PRUEBA_SEGUNDOS)


async def enviar_prueba(
    redis: UpstashRedis, sub_id: str, registro: str, *, vapid: Vapid | None = None
) -> Resultado:
    """Manda la notificación de prueba (con el nombre de la ciudad de la suscripción) a `registro`.

    El Topic lleva un prefijo propio: una prueba nunca reemplaza a un aviso real todavía sin entregar de la
    misma ciudad y día, ni al revés.
    """
    suscripcion = leer_registro(registro)
    if suscripcion is None:
        logger.warning(
            "alertas: registro de suscripción ilegible o inválido, no se envía la prueba"
        )
        return Resultado.ERROR
    zona = zona_por_slug(suscripcion.zona)  # no es None: `Suscripcion` ya la validó
    return await enviar(
        redis,
        sub_id,
        registro,
        construir_payload(texto_prueba(zona), tag=TAG_PRUEBA),
        zona=f"prueba:{suscripcion.zona}",
        fecha=datetime.now(timezone.utc).date(),
        ttl=TTL_PRUEBA_SEGUNDOS,
        vapid=vapid,
    )
