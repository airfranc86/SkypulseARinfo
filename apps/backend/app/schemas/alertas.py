"""Esquemas de las alertas push: alta y baja de suscripciones (FRA-353).

El cuerpo del alta es lo que devuelve `PushSubscription.toJSON()` del navegador más la zona. Los campos
que no usamos (p. ej. `expirationTime`) se ignoran. Los validadores reutilizan los de
`services/alertas/suscripcion.py`; el handler 422 de `main.py` descarta el valor recibido, así que
ni un endpoint ni una clave inválidos vuelven en la respuesta.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.services.alertas.suscripcion import (
    validar_auth,
    validar_endpoint,
    validar_p256dh,
    validar_zona,
)


class PushKeys(BaseModel):
    p256dh: str = Field(
        description="Clave pública ECDH P-256 del navegador, base64url (65 bytes)."
    )
    auth: str = Field(description="Secreto de autenticación, base64url (16 bytes).")

    @field_validator("p256dh")
    @classmethod
    def _p256dh(cls, value: str) -> str:
        return validar_p256dh(value)

    @field_validator("auth")
    @classmethod
    def _auth(cls, value: str) -> str:
        return validar_auth(value)


class SuscripcionRequest(BaseModel):
    endpoint: str = Field(
        description="URL https de un servicio push conocido (FCM, Mozilla, Apple, Windows)."
    )
    keys: PushKeys
    zona: str = Field(
        description="Slug de una de las ciudades de alertas, p. ej. `cordoba`."
    )

    @field_validator("endpoint")
    @classmethod
    def _endpoint(cls, value: str) -> str:
        return validar_endpoint(value)

    @field_validator("zona")
    @classmethod
    def _zona(cls, value: str) -> str:
        return validar_zona(value)


class SuscripcionCreada(BaseModel):
    id: str = Field(
        description="Identificador de la suscripción; sirve para darla de baja."
    )
    zona: str


class BajaRequest(BaseModel):
    id: str = Field(
        pattern=r"^[A-Za-z0-9_-]{22}$", description="El `id` devuelto por el alta."
    )
