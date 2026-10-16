"""Verificador: decide si una respuesta se puede mostrar. Es la defensa contra la invención, no el modelo.

Antes de mirar nada, el texto se lleva a una forma canónica (NFKC, sin caracteres invisibles, con todos los signos
menos como `-`), así los trucos de escritura (ancho completo, superíndices, puntos entre corchetes) no esquivan las
reglas. Una respuesta pasa solo si, sin sus frases fijas:
- no está vacía, no pasa de `MAX_CARACTERES` y solo usa letras latinas;
- toda cifra está en la hoja de datos (con tolerancia de redondeo y con el signo correcto). Las horas y fechas
  ("15:00", "17/10", "a las 15") se cotejan solo contra las horas y fechas de la hoja, no contra las mediciones;
  `lugar` y el METAR crudo no cuentan como fuente de cifras. No hay cifras escritas en letras, que no se podrían
  cotejar (de "diez" para arriba, ni "cinco grados");
- no trae enlaces (ni dominios sin esquema), Markdown, ni el nombre de un modelo o proveedor, ni consignas de
  alarma o evacuación;
- no afirma una alerta o aviso que la hoja no respalda: sin el bloque de avisos, con el bloque vacío, o citando un
  color de nivel que no está entre los avisos vigentes.

Lo que no cubre (y por eso la hoja y el prompt también cuentan): que una cifra de la hoja se use en el lugar
equivocado, o que se afirme algo cualitativo falso con cifras correctas.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.asistente.enrutador import normalizar
from app.services.asistente.hoja_datos import Hoja

MAX_CARACTERES = 700
FRASE_AVISO_OFICIAL = "No es un aviso oficial: para alertas, smn.gob.ar"
FRASE_AERONAUTICA = "Informativo; consultá NOTAM y documentación oficial."

# La frase fija solo se saca si no la sigue nada que la convierta en otro enlace ("smn.gob.ar.com", "smn.gob.ar/x").
_FRASES_FIJAS = tuple(
    re.compile(re.escape(frase) + r"(?!\.?[\w/#@?&=%:-])") for frase in (FRASE_AVISO_OFICIAL, FRASE_AERONAUTICA)
)
_SIGNOS_MENOS = str.maketrans({c: "-" for c in "−‒–‐‑﹣－"})
_PUNTO_OCULTO = re.compile(r"[\[(]\s*\.\s*[\])]")

_NUMERO = re.compile(r"\d+(?:[.,]\d+)*")
_MENOS_ANTES = re.compile(r"\bmenos\s*$", re.IGNORECASE)
_BAJO_CERO = re.compile(r"\s*(?:grados?|[°º]\s*c?)?\s*bajo\s+cero", re.IGNORECASE)
_HORA_O_FECHA = re.compile(r"\b\d{1,2}:\d{2}\b|\b\d{1,2}/\d{1,2}\b")
_HORA_HABLADA = re.compile(r"\blas\s+(\d{1,2})\b", re.IGNORECASE)
_SIN_CIFRAS = frozenset({"lugar", "crudo"})  # texto libre que no es una medición: no habilita ninguna cifra

_NUMEROS_EN_LETRAS = re.compile(
    r"\b(?:diez|once|doce|trece|catorce|quince|dieciseis|diecisiete|dieciocho|diecinueve|veinte|veinti\w+|"
    r"\w*(?:treinta|cuarenta|cincuenta|sesenta|setenta|ochenta|noventa)\w*|cien|ciento|\w*cientos|centenar\w*|"
    r"decena\w*|docena\w*|millon\w*|mil)\b"
)
_CHICOS_CON_UNIDAD = re.compile(
    r"\b(?:dos|tres|cuatro|cinco|seis|siete|ocho|nueve)\s+"
    r"(?:grados|milimetros|mm|centimetros|km|kilometros|metros|nudos|kt|por ciento)\b"
)
_URL = re.compile(
    r"(?:https?|ftp)://\S+|\bwww\.\S+"
    r"|\b[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.[a-z]{2,}\b"   # dominio sin esquema, con cualquier TLD
    r"|[^\s@]+@[^\s@]+\.[^\s@]+"
    r"|\b[a-z][a-z0-9+.-]{1,9}:(?://|[a-z])",                # esquema: hxxp://, mailto:x
    re.IGNORECASE,
)
_FORMATO = re.compile(
    r"\*\*|__|~~|`|\]\s*\(|<[a-z/!]|\|.*\||(?<![\w*])\*[^\s*][^*\n]*\*|^\s*#{1,6}\s|^\s*[-*•]\s",
    re.IGNORECASE | re.MULTILINE,
)
_PROVEEDOR = re.compile(
    r"\b(?:groq|openai|chatgpt|gpt\d*|anthropic|claude|gemini|mistral|mixtral|cloudflare|workers ai|openrouter|"
    r"deepseek|qwen|grok|copilot|perplexity|meta ai|llama[ -]?\d+)\b"
)
_ALARMISMO = re.compile(r"\b(?:evacu|emergenc|alarm)\w*")
_PALABRA_DE_ALERTA = re.compile(r"\b(?:alert|avis|advertenc)\w*")
_NEGACION = re.compile(r"\b(?:no|sin|ningun\w*|tampoco)\b[^.!?;]{0,60}\b(?:alert|avis|advertenc)\w*")
_COLORES = ("roj", "naranj", "amarill")


@dataclass(frozen=True)
class Veredicto:
    ok: bool
    motivos: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------

def _canonico(texto: str) -> str:
    sin_invisibles = "".join(c for c in unicodedata.normalize("NFKC", texto) if unicodedata.category(c) != "Cf")
    return _PUNTO_OCULTO.sub(".", sin_invisibles.translate(_SIGNOS_MENOS))


def _sacar_frases_fijas(texto: str) -> str:
    for frase in _FRASES_FIJAS:
        texto = frase.sub(" ", texto)
    return texto


def _textos_de_la_hoja(valor: Any, claves: frozenset[str]) -> list[str]:
    """Los textos que la propia hoja redactó (definiciones, títulos y motivos de las herramientas)."""
    if isinstance(valor, dict):
        encontrados: list[str] = []
        for clave, v in valor.items():
            if clave in claves and isinstance(v, str):
                encontrados.append(v)
            else:
                encontrados.extend(_textos_de_la_hoja(v, claves))
        return encontrados
    if isinstance(valor, list):
        return [t for v in valor for t in _textos_de_la_hoja(v, claves)]
    return []


# ---------------------------------------------------------------------------
# Cifras
# ---------------------------------------------------------------------------

def _candidatos(token: str) -> list[Decimal]:
    """Los valores que puede significar un número escrito: "1.200" es 1,2 o 1200; "18,5" es 18,5.

    Un número mal formado ("1.2,3.4") no tiene lectura: no se puede cotejar, así que cuenta como inventado.
    """
    try:
        return _lecturas(token)
    except InvalidOperation:
        return []


def _lecturas(token: str) -> list[Decimal]:
    if "." in token and "," in token:
        decimal = "," if token.rfind(",") > token.rfind(".") else "."
        miles = "." if decimal == "," else ","
        return [Decimal(token.replace(miles, "").replace(decimal, "."))]
    for separador in ".,":
        if separador in token:
            partes = token.split(separador)
            if len(partes) > 2:
                return [Decimal("".join(partes))]
            entero, resto = partes
            como_decimal = Decimal(f"{entero}.{resto}")
            if len(resto) == 3 and entero != "0":
                return [como_decimal, Decimal(entero + resto)]
            return [como_decimal]
    return [Decimal(token)]


def _es_negativo(texto: str, m: re.Match[str]) -> bool:
    """`-3`, `menos 3` y `3 grados bajo cero` son negativos; el guion de un rango (`12-26`) no."""
    antes = texto[: m.start()]
    if antes.endswith("-") and (len(antes) == 1 or not antes[-2].isalnum()):
        return True
    return bool(_MENOS_ANTES.search(antes[-12:])) or bool(_BAJO_CERO.match(texto[m.end(): m.end() + 24]))


def _numeros_de_texto(texto: str) -> list[list[Decimal]]:
    """Cada número del texto con sus lecturas posibles."""
    return [
        [-c if _es_negativo(texto, m) else c for c in _candidatos(m.group())]
        for m in _NUMERO.finditer(texto)
    ]


def _separar_tiempos(texto: str, hablado: bool = False) -> tuple[str, list[Decimal]]:
    """Saca las horas y fechas (`15:00`, `17/10`, y con `hablado`, `a las 15`) y devuelve sus componentes aparte."""
    componentes: list[Decimal] = []

    def tomar(m: re.Match[str]) -> str:
        componentes.extend(Decimal(n) for n in re.findall(r"\d+", m.group()))
        return " "

    sin_tiempos = _HORA_O_FECHA.sub(tomar, texto)
    if hablado:
        sin_tiempos = _HORA_HABLADA.sub(tomar, sin_tiempos)
    return sin_tiempos, componentes


def _recolectar(valor: Any, mediciones: list[Decimal], tiempos: list[Decimal]) -> None:
    """Junta las cifras que la hoja permite citar: mediciones por un lado, horas y fechas por el otro."""
    if isinstance(valor, bool) or valor is None:
        return
    if isinstance(valor, (int, float)):
        if math.isfinite(valor):
            mediciones.append(Decimal(str(valor)))
    elif isinstance(valor, str):
        sin_tiempos, componentes = _separar_tiempos(valor)
        tiempos.extend(componentes)
        for lecturas in _numeros_de_texto(sin_tiempos):
            mediciones.extend(lecturas)
    elif isinstance(valor, dict):
        for clave, v in valor.items():
            if clave not in _SIN_CIFRAS:
                _recolectar(v, mediciones, tiempos)
    elif isinstance(valor, (list, tuple)):
        for v in valor:
            _recolectar(v, mediciones, tiempos)


def _esta_en_la_hoja(lecturas: list[Decimal], conocidos: list[Decimal]) -> bool:
    """Con `d` decimales escritos se tolera medio punto de la última cifra: "22" y "22,4" salen de 22,4; "22,5" no."""
    for lectura in lecturas:
        tolerancia = Decimal("0.5") * Decimal(10) ** -max(0, -lectura.as_tuple().exponent)
        if any(abs(lectura - conocido) <= tolerancia for conocido in conocidos):
            return True
    return False


def _hay_cifras_inventadas(texto: str, hoja: Hoja) -> bool:
    mediciones: list[Decimal] = []
    tiempos: list[Decimal] = []
    _recolectar(hoja.datos, mediciones, tiempos)
    sin_tiempos, citados = _separar_tiempos(texto, hablado=True)
    if any(not _esta_en_la_hoja([c], tiempos) for c in citados):
        return True
    return any(not _esta_en_la_hoja(lecturas, mediciones) for lecturas in _numeros_de_texto(sin_tiempos))


# ---------------------------------------------------------------------------
# Avisos
# ---------------------------------------------------------------------------

def _motivos_de_avisos(normal: str, hoja: Hoja) -> list[str]:
    """Solo se puede hablar de alertas si la hoja trae el bloque de avisos y lo que se dice coincide con él."""
    frases = [f for f in re.split(r"[.!?;\n]", normal) if _PALABRA_DE_ALERTA.search(f)]
    if not frases:
        return []
    bloque = hoja.datos.get("avisos")
    if not (isinstance(bloque, dict) and "vigentes" in bloque):
        return ["aviso_sin_bloque"]  # el feed no respondió, o no se pidió: no se puede afirmar nada
    vigentes = bloque["vigentes"]
    niveles = [normalizar(str(a.get("nivel", ""))) for a in vigentes]
    for frase in frases:
        negada = bool(_NEGACION.search(frase))
        colores = [c for c in _COLORES if re.search(rf"\b{c}\w*", frase)]
        if not vigentes and not negada:
            return ["aviso_inventado"]  # hay feed y dice que no hay avisos
        if vigentes and negada and not colores:
            return ["aviso_inventado"]  # dice que no hay, pero hay
        if not negada and any(not any(n.startswith(c) for n in niveles) for c in colores):
            return ["aviso_inventado"]  # cita un color que no está entre los vigentes
    return []


# ---------------------------------------------------------------------------
# Veredicto
# ---------------------------------------------------------------------------

def verificar(respuesta: str, hoja: Hoja) -> Veredicto:
    """Los motivos por los que `respuesta` no se puede mostrar; vacío si pasa."""
    texto = _sacar_frases_fijas(_canonico(respuesta or ""))
    if not texto.strip():
        return Veredicto(False, ("vacia",))
    if len(respuesta) > MAX_CARACTERES:
        return Veredicto(False, ("larga",))  # se descarta igual: no vale la pena mirar el resto de un texto enorme

    motivos: list[str] = []
    if any(c.isalpha() and ord(c) >= 0x250 for c in texto):
        motivos.append("alfabeto")
    if _FORMATO.search(texto):
        motivos.append("formato")
    if _URL.search(texto):
        motivos.append("url")

    normal = normalizar(texto)
    if _PROVEEDOR.search(normal):
        motivos.append("proveedor")
    if _ALARMISMO.search(normal):
        motivos.append("alarmismo")
    # Las definiciones y los motivos que la propia hoja redactó pueden usar la palabra "aviso" ("el primer aviso de
    # que algo viene"): no son una afirmación de alerta.
    sin_propios = normal
    for propio in _textos_de_la_hoja(hoja.datos, frozenset({"definicion", "titulo", "motivo"})):
        if fragmento := normalizar(propio):
            sin_propios = sin_propios.replace(fragmento, " ")
    motivos.extend(_motivos_de_avisos(sin_propios, hoja))
    if _NUMEROS_EN_LETRAS.search(normal) or _CHICOS_CON_UNIDAD.search(normal):
        motivos.append("numero_en_letras")
    if _hay_cifras_inventadas(texto, hoja):
        motivos.append("numero_inventado")
    return Veredicto(not motivos, tuple(motivos))
