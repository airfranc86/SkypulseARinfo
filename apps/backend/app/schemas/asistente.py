"""Esquemas del asistente de Mora: el cuerpo de la pregunta y la respuesta.

El manejador 422 de `main.py` descarta el valor recibido, así que la pregunta de un usuario nunca vuelve en un
error. La respuesta lleva solo `estado` y `texto`: nada de bloques, motivos ni nombres de modelos o proveedores.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import settings

# Una ruta del sitio, con parámetros si los trae; nunca una URL ni algo que empiece con `//`.
_PAGINA = re.compile(r"/[A-Za-z0-9_\-/.?=&%]{0,79}")


class PreguntaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Tope duro de entrada; el máximo real es `settings.asistente_pregunta_max` (se cuenta ya recortada).
    pregunta: str = Field(max_length=2000, description="La pregunta del usuario, de 1 a 300 caracteres.")
    pagina: str | None = Field(default=None, description="La ruta del sitio desde la que se pregunta.")
    lat: float = Field(ge=-55, le=-21, description="Latitud (Argentina: -55 a -21); se redondea a 2 decimales.")
    lon: float = Field(ge=-74, le=-53, description="Longitud (Argentina: -74 a -53); se redondea a 2 decimales.")

    @field_validator("pregunta")
    @classmethod
    def _pregunta(cls, value: str) -> str:
        # Los caracteres invisibles (categoría Cf: ancho cero, inversión de lectura) se sacan; los de control (Cc) se
        # rechazan, salvo salto de línea, retorno y tabulación. Un NUL en medio de "terremoto" esquivaría las reglas.
        sin_invisibles = "".join(c for c in value if unicodedata.category(c) != "Cf")
        if any(unicodedata.category(c) == "Cc" and c not in "\n\r\t" for c in sin_invisibles):
            raise ValueError("la pregunta tiene caracteres de control")
        recortada = sin_invisibles.strip()
        if not recortada:
            raise ValueError("la pregunta no puede estar vacía")
        if len(recortada) > settings.asistente_pregunta_max:
            raise ValueError("la pregunta es demasiado larga")
        return recortada

    @field_validator("pagina")
    @classmethod
    def _pagina(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value.startswith("//") or not _PAGINA.fullmatch(value):
            raise ValueError("la página tiene que ser una ruta del sitio")
        return value

    @field_validator("lat", "lon")
    @classmethod
    def _dos_decimales(cls, value: float) -> float:
        return round(value, 2)


class RespuestaAsistente(BaseModel):
    estado: Literal["ok", "sin_dato", "fuera_de_alcance"]
    texto: str
