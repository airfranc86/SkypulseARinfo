"""Ayudas compartidas por los tests de la firma de QStash (FRA-355).

Las claves son de prueba y obvias; nunca una clave real. `firmar` arma un JWT como el de QStash;
`firmar_a_mano` arma uno sin PyJWT (que no deja firmar con clave vacía ni con un `iss` que no sea texto).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import jwt

CLAVE_ACTUAL = "clave-de-prueba-ACTUAL-0123456789abcdef"
CLAVE_SIGUIENTE = "clave-de-prueba-SIGUIENTE-0123456789abc"
CLAVE_AJENA = "clave-de-prueba-AJENA-0123456789abcdefgh"
URL_EVALUAR = "https://skypulse-test.example/api/alertas/evaluar"
CUERPO = b'{"origen":"qstash","n":1}'

CLAIMS_OBLIGATORIOS = ("exp", "nbf", "iss", "sub", "body")


def b64url(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).decode().rstrip("=")


def hash_cuerpo(cuerpo: bytes) -> str:
    return b64url(hashlib.sha256(cuerpo).digest())


def firmar(
    cuerpo: bytes = CUERPO,
    *,
    clave: str = CLAVE_ACTUAL,
    algoritmo: str = "HS256",
    sub: object = URL_EVALUAR,
    iss: object = "Upstash",
    exp_en: int = 300,
    nbf_en: int = -1,
    body: object = None,
    quitar: tuple[str, ...] = (),
    extra: dict | None = None,
) -> str:
    """Un JWT como el de QStash. `exp_en`/`nbf_en` son segundos respecto de ahora; `quitar` borra claims."""
    ahora = int(time.time())
    claims: dict = {
        "iss": iss,
        "sub": sub,
        "iat": ahora,
        "nbf": ahora + nbf_en,
        "exp": ahora + exp_en,
        "jti": "jwt_prueba_0001",
        "body": hash_cuerpo(cuerpo) if body is None else body,
        **(extra or {}),
    }
    for nombre in quitar:
        claims.pop(nombre, None)
    return jwt.encode(claims, clave, algorithm=algoritmo)


def firmar_a_mano(claims: dict, clave: bytes) -> str:
    """Un JWT HS256 armado sin PyJWT."""
    cabecera = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    carga = b64url(json.dumps(claims).encode())
    firma = hmac.new(clave, f"{cabecera}.{carga}".encode(), hashlib.sha256).digest()
    return f"{cabecera}.{carga}.{b64url(firma)}"


def claims_validos(cuerpo: bytes = CUERPO, **cambios: object) -> dict:
    ahora = int(time.time())
    return {
        "iss": "Upstash",
        "sub": URL_EVALUAR,
        "iat": ahora,
        "nbf": ahora - 1,
        "exp": ahora + 300,
        "body": hash_cuerpo(cuerpo),
        **cambios,
    }
