"""Verificación de la firma de QStash (FRA-355).

QStash firma cada mensaje que entrega con un JWT HS256 en la cabecera `Upstash-Signature`. Se acepta solo
si TODO esto se cumple, con la clave actual o, si falla, con la siguiente (rotación de claves):

- el algoritmo de la cabecera es HS256 (ni `none` ni otro HMAC ni uno asimétrico; `algorithms=["HS256"]`);
- `iss == "Upstash"`;
- `sub` es exactamente la URL del endpoint (`settings.alertas_evaluar_url`): una firma válida para otro
  destino no sirve acá;
- `body` es el SHA-256 de los bytes CRUDOS del cuerpo, en base64url (se tolera el relleno `=`, como los SDK
  oficiales). Quien llama debe pasar los bytes tal como llegaron, sin parsear ni reescribir nada;
- `exp`, `nbf`, `iss`, `sub` y `body` están presentes; `exp`, `nbf` e `iat` se verifican con una tolerancia
  de reloj pequeña.

Falla CERRADO: sin ninguna clave o sin URL configurada, con una firma ausente, mal formada, enorme o con
cualquier error inesperado, rechaza. Nunca se loguea ni la firma, ni el cuerpo, ni las claves, ni el texto
de una excepción de la librería: solo mensajes fijos.

`motivo_de_rechazo` devuelve None si la firma vale, o UN CÓDIGO FIJO (`MOTIVO_*`, sin valores) con la causa:
sirve para el registro del servidor. Hacia afuera la respuesta es siempre la misma, genérica: el código no
sale en la respuesta HTTP. `firma_valida` es la versión booleana.

LIMITACIÓN CONOCIDA (repetición): una firma válida se puede volver a presentar durante su vida (~5 minutos)
y esta función la acepta cada vez. No hay claim `jti` obligatorio ni registro de los ya vistos: decisión
tomada en la 5b, que NO exige ni registra el `jti` hasta capturar un reintento real de QStash (si QStash
reusara el mismo `jti` en un reintento, un registro rechazaría un reintento legítimo). La repetición dentro de
la vida de la firma la frena el lock de la corrida, `alertas:lock:evaluar` (`services/alertas/evaluacion.py`):
se toma con SET NX EX, dura más que la firma (`alertas_lock_ttl_segundos`, 600 s por defecto) y NO se libera,
se deja vencer.

Los digests y la URL se comparan con `hmac.compare_digest` (tiempo constante); la firma HMAC del JWT la
compara PyJWT de la misma forma.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging

import jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

EMISOR = "Upstash"
ALGORITMO = "HS256"
# Tolerancia de reloj entre QStash y este servidor para `exp`/`nbf`/`iat`. Pequeña a propósito: una firma
# vencida es un mensaje repetido.
TOLERANCIA_RELOJ_SEGUNDOS = 5
# Un JWT de QStash mide ~400 caracteres; más de esto no es una firma de QStash y ni se decodifica.
MAX_LARGO_FIRMA = 4096
CLAIMS_OBLIGATORIOS = ("exp", "nbf", "iss", "sub", "body")

# Códigos fijos del motivo de un rechazo (solo para el registro; nunca llevan valores).
MOTIVO_SIN_CABECERA = "sin_cabecera"  # no vino la cabecera, o vino vacía
MOTIVO_FIRMA_LARGA = "firma_larga"  # la cabecera pasa de MAX_LARGO_FIRMA
MOTIVO_FORMATO = "formato"  # no es un JWT legible
MOTIVO_CUERPO = "cuerpo"  # el cuerpo no se pudo leer, o pasa del tope
MOTIVO_ALGORITMO = "algoritmo"  # la cabecera del JWT no declara HS256
MOTIVO_CLAVE = "clave"  # la firma no es de ninguna de las claves configuradas
MOTIVO_ISS = "iss"
MOTIVO_SUB = "sub"
MOTIVO_BODY = "body"
MOTIVO_EXP_NBF = "exp_nbf"  # vencida, todavía no válida, sin exp/nbf o con iat en el futuro
MOTIVO_CONFIG = "config"  # faltan las claves o la URL del endpoint
MOTIVO_INTERNO = "interno"  # una excepción inesperada

_MOTIVO_POR_CLAIM_AUSENTE = {"iss": MOTIVO_ISS, "sub": MOTIVO_SUB, "body": MOTIVO_BODY}

_aviso_de_configuracion_emitido = False


def reset_aviso_de_configuracion_para_tests() -> None:
    """Vuelve a armar el aviso de configuración faltante (que sale una vez por proceso)."""
    global _aviso_de_configuracion_emitido
    _aviso_de_configuracion_emitido = False


def _avisar_configuracion_faltante() -> None:
    """Un solo WARNING por proceso: sin esto, cada pedido sin autenticar escribiría una línea en el registro."""
    global _aviso_de_configuracion_emitido
    if _aviso_de_configuracion_emitido:
        return
    _aviso_de_configuracion_emitido = True
    logger.warning("qstash: sin claves de firma o sin URL del endpoint configuradas; se rechaza todo")


def _hash_cuerpo(cuerpo: bytes) -> str:
    """SHA-256 del cuerpo en base64url sin relleno (el formato del claim `body`)."""
    return base64.urlsafe_b64encode(hashlib.sha256(cuerpo).digest()).decode().rstrip("=")


def _claves_configuradas() -> tuple[str, ...]:
    claves = (settings.qstash_current_signing_key, settings.qstash_next_signing_key)
    return tuple(clave for clave in claves if clave)


def _mismo_texto(a: object, b: str) -> bool:
    """Igualdad en tiempo constante de dos textos; False si `a` no es un texto."""
    if not isinstance(a, str):
        return False
    return hmac.compare_digest(a.encode(), b.encode())


def _sin_relleno(valor: object) -> object:
    return valor.rstrip("=") if isinstance(valor, str) else valor


def _motivo_del_algoritmo(firma: str) -> str | None:
    """None si la cabecera del JWT declara HS256; si no, el código del motivo."""
    try:
        cabecera = jwt.get_unverified_header(firma)
    except jwt.PyJWTError:
        return MOTIVO_FORMATO
    return None if cabecera.get("alg") == ALGORITMO else MOTIVO_ALGORITMO


def _motivo_de_excepcion(exc: jwt.PyJWTError) -> str:
    """El código fijo de un error de PyJWT (el texto de la excepción nunca se usa ni se registra)."""
    if isinstance(exc, jwt.InvalidSignatureError):
        return MOTIVO_CLAVE
    if isinstance(exc, jwt.MissingRequiredClaimError):
        return _MOTIVO_POR_CLAIM_AUSENTE.get(exc.claim, MOTIVO_EXP_NBF)
    if isinstance(exc, jwt.InvalidIssuerError):
        return MOTIVO_ISS
    if isinstance(exc, getattr(jwt.exceptions, "InvalidSubjectError", ())):  # PyJWT >= 2.10
        return MOTIVO_SUB
    if isinstance(exc, jwt.ExpiredSignatureError | jwt.ImmatureSignatureError | jwt.exceptions.InvalidIssuedAtError):
        return MOTIVO_EXP_NBF
    if isinstance(exc, jwt.InvalidAlgorithmError):
        return MOTIVO_ALGORITMO
    if isinstance(exc, jwt.InvalidKeyError):
        return MOTIVO_CLAVE
    return MOTIVO_FORMATO


def _decodificar(firma: str, clave: str) -> tuple[dict | None, str]:
    """(claims, "") si la firma es de `clave` y los tiempos y el emisor valen; (None, motivo) en otro caso."""
    try:
        claims = jwt.decode(
            firma,
            clave,
            algorithms=[ALGORITMO],
            issuer=EMISOR,
            leeway=TOLERANCIA_RELOJ_SEGUNDOS,
            options={"require": list(CLAIMS_OBLIGATORIOS)},
        )
    except jwt.PyJWTError as exc:
        return None, _motivo_de_excepcion(exc)
    if not isinstance(claims, dict):
        return None, MOTIVO_FORMATO
    return claims, ""


def motivo_de_rechazo(firma: object, cuerpo: object) -> str | None:
    """None si `firma` (la cabecera `Upstash-Signature`) es una firma vigente de QStash para `cuerpo`; si no,
    el código fijo (`MOTIVO_*`) de por qué se rechaza."""
    try:
        return _motivo_de_rechazo(firma, cuerpo)
    except Exception:  # noqa: BLE001 - una verificación que no puede concluir rechaza; nunca un 500
        logger.warning("qstash: error inesperado al verificar la firma")
        return MOTIVO_INTERNO


def firma_valida(firma: object, cuerpo: object) -> bool:
    """True solo si `firma` es una firma vigente de QStash para `cuerpo` (ver `motivo_de_rechazo`)."""
    return motivo_de_rechazo(firma, cuerpo) is None


def _motivo_de_rechazo(firma: object, cuerpo: object) -> str | None:
    url = settings.alertas_evaluar_url
    claves = _claves_configuradas()
    if not url or not claves:
        _avisar_configuracion_faltante()
        return MOTIVO_CONFIG
    if firma is None or (isinstance(firma, str) and not firma.strip()):
        return MOTIVO_SIN_CABECERA
    if not isinstance(firma, str):
        return MOTIVO_FORMATO
    if len(firma) > MAX_LARGO_FIRMA:
        return MOTIVO_FIRMA_LARGA
    if not isinstance(cuerpo, bytes | bytearray):
        return MOTIVO_CUERPO
    motivo_algoritmo = _motivo_del_algoritmo(firma)
    if motivo_algoritmo is not None:
        return motivo_algoritmo

    for clave in claves:
        claims, motivo = _decodificar(firma, clave)
        if claims is None:
            if motivo == MOTIVO_CLAVE:
                continue  # no es de esta clave: probar la siguiente
            return motivo  # la firma era de esta clave pero un claim no vale: con la otra tampoco valdría
        # Con la firma de esta clave ya verificada, los claims se comparan con lo que se espera de ESTE pedido.
        sub_coincide = _mismo_texto(claims.get("sub"), url)
        cuerpo_coincide = _mismo_texto(_sin_relleno(claims.get("body")), _hash_cuerpo(bytes(cuerpo)))
        if not sub_coincide:
            return MOTIVO_SUB
        return None if cuerpo_coincide else MOTIVO_BODY
    return MOTIVO_CLAVE
