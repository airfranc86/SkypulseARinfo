"""Núcleo del asistente: enruta, arma la hoja, pregunta al modelo y verifica. Es lo único que el endpoint llama.

Recibe los datos ya obtenidos (`Fuentes`) y el modelo por protocolo; no hace pedidos de red. Si el proveedor falla,
la excepción sube tal cual para que el router la convierta en su respuesta de "no disponible" (no es un caso de
`sin_dato`: ahí el modelo sí respondió, o ni hizo falta llamarlo).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.services.asistente.enrutador import enrutar, normalizar
from app.services.asistente.hoja_datos import Fuentes, Hoja, armar_hoja
from app.services.asistente.modelo import Modelo
from app.services.asistente.verificador import FRASE_AERONAUTICA, FRASE_AVISO_OFICIAL, verificar

RESPUESTA_SIN_DATO = "No tengo ese dato a mano. Probá de nuevo en un rato o mirá la página de Previsión."
REDIRECCION_SISMOS_Y_VOLCANES = "De sismos y volcanes no te puedo hablar: mirá las páginas de Terremotos y Volcanes."

_TORMENTAS_O_AVISOS = re.compile(r"\b(?:tormenta|granizo|temporal|alert|avis|alarm|advertenc|emergenc)\w*")


@dataclass(frozen=True)
class Respuesta:
    estado: Literal["ok", "sin_dato", "fuera_de_alcance"]
    texto: str
    bloques: tuple[str, ...]
    motivos: tuple[str, ...] = ()


def _con_frases_obligatorias(texto: str, hoja: Hoja) -> str:
    """Agrega las frases fijas que corresponden: las pone el código, no el modelo, así nunca faltan ni se alteran."""
    if not texto.strip():
        return texto
    partes = [texto.strip()]
    habla_de_avisos = "avisos" in hoja.bloques or _TORMENTAS_O_AVISOS.search(normalizar(texto))
    if habla_de_avisos and FRASE_AVISO_OFICIAL not in texto:
        partes.append(FRASE_AVISO_OFICIAL)
    if {"metar", "taf"} & set(hoja.bloques) and FRASE_AERONAUTICA not in texto:
        partes.append(FRASE_AERONAUTICA)
    return " ".join(partes)


def _sin_dato(hoja: Hoja, motivos: tuple[str, ...] = ()) -> Respuesta:
    """La respuesta de plantilla; si se preguntaba por avisos, también señala la fuente oficial."""
    texto = RESPUESTA_SIN_DATO + (f" {FRASE_AVISO_OFICIAL}" if "avisos" in hoja.bloques else "")
    return Respuesta("sin_dato", texto, hoja.bloques, motivos)


async def responder(
    pregunta: str, fuentes: Fuentes, modelo: Modelo, *, pagina: str | None = None, ahora_utc: datetime,
) -> Respuesta:
    ruta = enrutar(pregunta, pagina)
    if ruta.fuera_de_alcance:
        return Respuesta("fuera_de_alcance", REDIRECCION_SISMOS_Y_VOLCANES, ())

    hoja = armar_hoja(ruta, fuentes, ahora_utc)
    if not hoja.tiene_datos:
        return _sin_dato(hoja)  # sin datos no se gasta una llamada al modelo

    texto = _con_frases_obligatorias(await modelo.generar(pregunta, hoja), hoja)
    veredicto = verificar(texto, hoja)
    if not veredicto.ok:
        return _sin_dato(hoja, veredicto.motivos)
    return Respuesta("ok", texto, hoja.bloques)
