"""El modelo de lenguaje, detrás de un protocolo, y `ModeloFalso`, que responde por plantillas desde la hoja.

`ModeloFalso` solo repite cifras de la hoja y no mira la pregunta: por eso sirve para probar todo lo demás (el
enrutado, la hoja, el verificador) sin red, sin claves y sin que un texto hostil pueda cambiarle la respuesta.
Los proveedores reales (Groq, etc.) van en otro módulo y cumplen el mismo protocolo.
"""
from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

from app.services.asistente.hoja_datos import Hoja

# Deja lugar, dentro de los 700 caracteres del verificador, para las frases fijas que agrega el núcleo.
LIMITE_CARACTERES = 500


@runtime_checkable
class Modelo(Protocol):
    async def generar(self, pregunta: str, hoja: Hoja) -> str:
        """Redacta la respuesta usando solo la hoja. Puede levantar una excepción si el proveedor falla."""
        ...


def _fmt(valor: int | float) -> str:
    return str(valor).replace(".", ",")


def _enumerar(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " y " + items[-1]


def _con_punto(texto: str) -> str:
    return texto if texto.endswith((".", "!", "?")) else texto + "."


def _ahora(d: dict[str, Any]) -> str:
    partes = []
    if "temp_c" in d:
        partes.append(f"{_fmt(d['temp_c'])} °C")
    if "humedad_pct" in d:
        partes.append(f"humedad de {_fmt(d['humedad_pct'])} %")
    if "viento_kmh" in d:
        partes.append(f"viento de {_fmt(d['viento_kmh'])} km/h")
    return f"Ahora hay {_enumerar(partes)}." if partes else "No tengo datos de ahora en este momento."


def _horas(franjas: list[dict[str, Any]]) -> str:
    con_lluvia = next((f for f in franjas if f.get("lluvia_mm", 0) > 0), None)
    if con_lluvia is None:
        return "No se espera lluvia en las próximas horas."
    tormenta = ", con tormenta" if con_lluvia.get("tormenta") else ""
    desde, hasta = con_lluvia["franja"].split("-")
    return f"Se espera lluvia entre las {desde} y las {hasta} ({_fmt(con_lluvia['lluvia_mm'])} mm){tormenta}."


def _dias(dias: list[dict[str, Any]]) -> str:
    oraciones = []
    for d in dias:
        cuando = d["cuando"].capitalize() if "cuando" in d else d["fecha"]
        extremos = []
        if "max_c" in d:
            extremos.append(f"máxima de {_fmt(d['max_c'])} °C")
        if "min_c" in d:
            extremos.append(f"mínima de {_fmt(d['min_c'])} °C")
        oracion = f"{cuando}: {' y '.join(extremos)}" if extremos else f"{cuando}: sin temperaturas"
        if d.get("lluvia_mm", 0) > 0:
            probabilidad = f" (probabilidad de {_fmt(d['prob_lluvia_pct'])} %)" if "prob_lluvia_pct" in d else ""
            oracion += f", con lluvia de {_fmt(d['lluvia_mm'])} mm{probabilidad}"
        oraciones.append(oracion + ".")
    return " ".join(oraciones)


def _avisos(d: dict[str, Any]) -> str:
    vigentes = d["vigentes"]
    if not vigentes:
        return "El SMN no informa avisos vigentes."

    def uno(a: dict[str, Any]) -> str:
        # "vigentes" incluye los que empiezan más tarde: siempre se dice desde cuándo y hasta cuándo.
        desde = f", desde {a['desde']}" if "desde" in a else ""
        hasta = f" hasta {a['hasta']}" if "hasta" in a else ""
        return f"{a['tipo']}, nivel {a['nivel']}{desde}{hasta}"

    mas = " Hay más avisos en la página del SMN." if "total" in d else ""
    if len(vigentes) == 1:
        return f"El SMN informa un aviso: {uno(vigentes[0])}.{mas}"
    return f"El SMN informa avisos: {'; '.join(uno(a) for a in vigentes)}.{mas}"


def _niebla(d: dict[str, Any]) -> str:
    if "visibilidad_m" in d:
        estacion = f" ({d['estacion']})" if "estacion" in d else ""
        texto = f"Visibilidad de {_fmt(d['visibilidad_m'])} m: {d['estado']}{estacion}."
    else:
        texto = f"Estado de la visibilidad: {d['estado']}."
    if "horas_con_niebla" in d:
        texto += f" Habrá niebla a las {_enumerar(d['horas_con_niebla'])}."
    return texto


def _cota_nieve(d: dict[str, Any]) -> str:
    detalle = [f"fórmula de Alcaide: {_fmt(d['alcaide_m'])} m", f"gradiente estándar: {_fmt(d['gradiente_m'])} m"]
    if "presion_m" in d:
        detalle.append(f"nivel de presión de referencia: {_fmt(d['presion_m'])} m")
    return f"La cota de nieve ronda los {_fmt(d['promedio_m'])} m ({'; '.join(detalle)})."


def _metar(d: dict[str, Any]) -> str:
    partes = []
    if "temp_c" in d:
        partes.append(f"{_fmt(d['temp_c'])} °C")
    if "viento_kmh" in d:
        direccion = f"{_fmt(d['viento_dir_deg'])}° a " if "viento_dir_deg" in d else ""
        rafaga = f" con ráfagas de {_fmt(d['rafaga_kmh'])} km/h" if "rafaga_kmh" in d else ""
        partes.append(f"viento de {direccion}{_fmt(d['viento_kmh'])} km/h{rafaga}")
    if "fenomeno" in d:
        partes.append(f"fenómeno {d['fenomeno']}")
    observado = f" ({d['observado']})" if "observado" in d else ""
    detalle = ", ".join(partes) if partes else "sin datos decodificados"
    return f"METAR de {d['estacion']}{observado}: {detalle}."


def _taf(d: dict[str, Any]) -> str:
    def periodo(p: dict[str, Any]) -> str:
        hasta = f" hasta {p['hasta']}" if "hasta" in p else ""
        fenomenos = f" con {', '.join(p['fenomenos'])}" if "fenomenos" in p else ""
        return f"{p['tipo']}{hasta}{fenomenos}"

    return f"TAF de {d['estacion']}: {'; '.join(periodo(p) for p in d['periodos'])}."


def _herramienta(d: dict[str, Any]) -> str:
    texto = f"{_con_punto(d['titulo'])} {_con_punto(d['motivo'])}"
    return texto + (f" Mejor franja: {d['mejor_franja']}." if "mejor_franja" in d else "")


def _glosario(entradas: list[dict[str, str]]) -> str:
    return " ".join(f"{e['termino'].capitalize()}: {_con_punto(e['definicion'])}" for e in entradas)


_PLANTILLAS: dict[str, Callable[[Any], str]] = {
    "ahora": _ahora, "horas": _horas, "dias": _dias, "avisos": _avisos, "niebla": _niebla, "cota_nieve": _cota_nieve,
    "metar": _metar, "taf": _taf, "glosario": _glosario,
}
_NOMBRES = {"cota_nieve": "la cota de nieve", "lavar_auto": "lavar el auto", "tender": "tender la ropa", "deporte": "deporte"}


def _frase(bloque: str, valor: Any) -> str:
    if valor == {"estado": "sin_dato"}:
        if bloque == "avisos":
            return "No pude consultar al SMN en este momento."
        nombre = bloque.split(":")[-1]
        return f"No tengo datos de {_NOMBRES.get(nombre, nombre)} en este momento."
    plantilla = _herramienta if bloque.startswith("herramienta:") else _PLANTILLAS[bloque]
    return plantilla(valor)


class ModeloFalso:
    """Redacta una oración por bloque, en orden, hasta `LIMITE_CARACTERES`. No usa la pregunta."""

    async def generar(self, pregunta: str, hoja: Hoja) -> str:
        oraciones = []
        if "pronostico_hace_h" in hoja.datos:
            oraciones.append(f"Ojo: el pronóstico es de hace {_fmt(hoja.datos['pronostico_hace_h'])} h.")
        oraciones += [_frase(bloque, hoja.datos[bloque]) for bloque in hoja.bloques]

        texto = oraciones[0] if oraciones else ""
        for oracion in oraciones[1:]:
            if len(texto) + 1 + len(oracion) > LIMITE_CARACTERES:
                break
            texto += " " + oracion
        return texto
