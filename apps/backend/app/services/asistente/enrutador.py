"""Enrutador de intención: reglas puras (sin modelo) que eligen los bloques de datos de la hoja.

Según la pregunta y la página de origen devuelve hasta `TOPE_BLOQUES` bloques, o marca la pregunta como fuera
de alcance (sismos y volcanes, decisión D5). Las reglas se miran sobre el texto sin tildes y en minúsculas, por
palabra completa o por raíz, así que un texto hostil o larguísimo no puede hacer nada más que sumar bloques de
la lista fija.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlsplit

BLOQUES_POR_DEFECTO = ("ahora", "horas")
TOPE_BLOQUES = 4
SISMOS_Y_VOLCANES = "sismos_y_volcanes"

_LARGO_MAXIMO = 600  # lo que pasa de acá no cambia el enrutado: se corta para no gastar tiempo en un texto enorme
_GENERICOS = frozenset({"ahora", "horas", "dias"})
_BLOQUES_DE_HERRAMIENTA = ("herramienta:tender", "herramienta:deporte", "herramienta:lavar_auto", "cota_nieve")

# Términos que el glosario sabe explicar (en minúsculas y sin tildes).
TERMINOS_GLOSARIO = (
    "cirro", "cirrocumulo", "cirrostrato", "cumulo", "cumulonimbo", "altocumulo", "altoestrato", "estrato",
    "estratocumulo", "nimboestrato", "nimbo", "lenticular", "mammatus", "virga", "cape", "isobara", "granizo",
    "rocio", "helada", "escarcha", "zonda", "niebla",
)

# Qué muestra cada página cuando la pregunta no trae pistas propias.
_BLOQUES_POR_PAGINA = {
    "/tender-ropa": ("herramienta:tender",),
    "/hacer-deporte": ("herramienta:deporte",),
    "/lavar-auto": ("herramienta:lavar_auto",),
    "/cota-de-nieve": ("cota_nieve",),
    "/niebla": ("niebla",),
    "/metar": ("metar", "taf"),
}

_SISMOS = ("sism", "terremot", "volcan", "erupci", "ceniza", "tsunami")
_TEMBLORES = {"temblor", "temblores", "temblar"}
_TENDER = {"ropa", "tender", "tendi", "tiendo", "tendedero", "colgar", "secar", "secado", "secarse"}
_DEPORTE = {
    "deporte", "deportes", "correr", "corro", "running", "trotar", "entrenar", "entreno", "entrenamiento", "bici",
    "bicicleta", "ciclismo", "futbol", "caminata", "caminar", "nadar",
}
_LAVAR = {"lavar", "lavado", "lavo", "lavarlo"}
_AUTO = {"auto", "autito", "coche", "carro", "vehiculo", "camioneta", "camion", "moto"}
_NIEVE = {"cota", "nieve", "esqui", "esquiar", "snowboard"}
_TORMENTAS = {"tormenta", "tormentas", "granizo", "temporal", "temporales"}
_AVISOS = _TORMENTAS | {"zonda", "smn", "vigente", "vigentes", "warning"}
_AEROPUERTO = {"aeropuerto", "aerodromo", "vuelo", "vuelos", "aeronautico", "aeronautica"}
_DIAS = {
    "manana", "semana", "finde", "proximos", "proximas", "lunes", "martes", "miercoles", "jueves", "viernes",
    "sabado", "domingo",
}
_HORAS = _TORMENTAS | {"tarde", "noche", "madrugada", "hoy", "horas", "paraguas", "mediodia", "amanecer", "atardecer"}
_AHORA = {"ahora", "ahorita", "actual", "actualmente"}


@dataclass(frozen=True)
class Ruta:
    """Lo que el enrutador decidió: los bloques de la hoja, los términos del glosario o que no se responde."""
    bloques: tuple[str, ...]
    terminos: tuple[str, ...] = ()
    fuera_de_alcance: str | None = None


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes, sin caracteres invisibles y con los espacios colapsados."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) not in ("Mn", "Cf")
    )
    return " ".join(sin_tildes.lower().split())


def _prefijo(palabras: Iterable[str], raices: tuple[str, ...]) -> bool:
    return any(p.startswith(r) for p in palabras for r in raices)


def _terminos(palabras: Iterable[str]) -> tuple[str, ...]:
    """Los términos del glosario nombrados en la pregunta, en orden y sin repetir (acepta el plural con `s`)."""
    hallados: list[str] = []
    for palabra in palabras:
        for termino in TERMINOS_GLOSARIO:
            if palabra in (termino, termino + "s") and termino not in hallados:
                hallados.append(termino)
    return tuple(hallados)


def _pide_definicion(texto: str, palabras: set[str], terminos: tuple[str, ...], hay_otros_bloques: bool) -> bool:
    """Una definición se pide con "qué es (un) <término>", o con "explicame/definición" si no pide nada más."""
    articulo = r"(?:(?:el|la|los|las|lo|un|una|unos|unas)\s+)?"
    directa = any(
        re.search(rf"\bque (?:es|son|significa|significan)\s+{articulo}{termino}s?\b", texto) for termino in terminos
    )
    indirecta = bool(palabras & {"explicame", "explica", "explicar", "definicion", "glosario"}) and not hay_otros_bloques
    return directa or indirecta


def _bloques_de_la_pregunta(palabras: set[str]) -> list[str]:
    """Los bloques que la pregunta pide, en orden de prioridad (el tope se queda con los primeros)."""
    hallados: list[str] = []

    def sumar(bloque: str, condicion: bool) -> None:
        if condicion and bloque not in hallados:
            hallados.append(bloque)

    sumar("herramienta:tender", bool(palabras & _TENDER))
    sumar("herramienta:deporte", bool(palabras & _DEPORTE))
    sumar("herramienta:lavar_auto", bool(palabras & _LAVAR) and bool(palabras & _AUTO))
    sumar("cota_nieve", bool(palabras & _NIEVE))
    sumar("avisos", _prefijo(palabras, ("alert", "avis")) or bool(palabras & _AVISOS))
    sumar("niebla", _prefijo(palabras, ("niebl", "nebl", "bruma", "visib")) or "fog" in palabras)
    sumar("metar", bool(palabras & ({"metar", "speci"} | _AEROPUERTO)))
    sumar("taf", bool(palabras & ({"taf"} | _AEROPUERTO)))
    sumar("dias", bool(palabras & _DIAS))
    sumar("horas", _prefijo(palabras, ("llov", "llu", "nev", "nieva")) or bool(palabras & _HORAS))
    sumar("ahora", _prefijo(palabras, ("calor", "frio", "temperat", "humed", "viento")) or bool(palabras & _AHORA))

    # Una herramienta ya trae su propia ventana horaria: sumarle `ahora`/`horas` gastaría presupuesto de la hoja.
    if any(b in _BLOQUES_DE_HERRAMIENTA for b in hallados):
        hallados = [b for b in hallados if b not in _GENERICOS]
    return hallados


def enrutar(pregunta: str, pagina: str | None = None) -> Ruta:
    """Elige los bloques de la hoja para `pregunta`; `pagina` (la ruta de origen) solo desempata si no hay pistas."""
    texto = normalizar((pregunta or "")[:_LARGO_MAXIMO])
    palabras = re.findall(r"[a-z0-9]+", texto)
    conjunto = set(palabras)

    if _prefijo(palabras, _SISMOS) or conjunto & _TEMBLORES:
        return Ruta(bloques=(), fuera_de_alcance=SISMOS_Y_VOLCANES)

    bloques = _bloques_de_la_pregunta(conjunto)
    terminos = _terminos(palabras)
    if terminos and _pide_definicion(texto, conjunto, terminos, bool(bloques)):
        return Ruta(bloques=("glosario",), terminos=terminos)

    if not bloques:
        ruta_de_la_pagina = urlsplit(pagina or "").path.rstrip("/").lower()
        bloques = list(_BLOQUES_POR_PAGINA.get(ruta_de_la_pagina, BLOQUES_POR_DEFECTO))
    return Ruta(bloques=tuple(bloques[:TOPE_BLOQUES]))
