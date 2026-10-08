"""Textos de las notificaciones de alertas push (FRA-354).

Un solo nivel de aviso y texto neutro. El horario va en franjas del día con su rango fijo («a la tarde
(12 a 18 h)»), nunca la hora de la tormenta: el pronóstico no tiene esa precisión y una hora puntual se lee
como una promesa. Si el modelo marca granizo (códigos 96 y 99) el aviso lo dice. Todo aviso de tormenta
termina con la leyenda que aclara que no es un aviso oficial. Son texto plano: una notificación no renderiza
markdown, así que la leyenda no lleva un enlace.

Los textos son un BORRADOR que el dueño aprueba antes del merge: cambiar una frase es tocar este archivo.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.services.alertas import umbrales
from app.services.alertas.regla import ResultadoRegla
from app.services.alertas.zonas import Zona

# Hora de Argentina (sin horario de verano), la misma que usa `regla.py` para sus ventanas.
_AR = timezone(timedelta(hours=-3))

LEYENDA = (
    "Pronóstico de SkyPulse, no es un aviso oficial. "
    "Consultá los avisos del SMN en smn.gob.ar"
)

# De la más temprana a la más tardía: el orden en que se nombran en el texto.
FRANJAS: tuple[str, ...] = ("madrugada", "mañana", "tarde", "noche")

# El rango de cada franja: tiene que coincidir con lo que devuelve `franja(hora)` (hay un test que lo cruza).
_FRASE_DE_FRANJA = {
    "madrugada": "de madrugada (0 a 6 h)",
    "mañana": "a la mañana (6 a 12 h)",
    "tarde": "a la tarde (12 a 18 h)",
    "noche": "a la noche (18 a 24 h)",
}


@dataclass(frozen=True)
class Mensaje:
    titulo: str
    cuerpo: str


def franja(hora: int) -> str:
    """La franja de una hora de Argentina (0 a 23): madrugada 0-5, mañana 6-11, tarde 12-17, noche 18-23."""
    if not 0 <= hora <= 23:
        raise ValueError("hora fuera del día")
    return FRANJAS[hora // 6]


def _franjas_de_horas(horas) -> tuple[str, ...]:
    presentes = {franja(datetime.fromtimestamp(h.timestamp, _AR).hour) for h in horas}
    return tuple(f for f in FRANJAS if f in presentes)


def franjas_de(resultado: ResultadoRegla) -> tuple[str, ...]:
    """Las franjas del día con al menos una hora de tormenta, sin repetir y de la más temprana a la más tardía."""
    return _franjas_de_horas(resultado.horas)


def franjas_granizo(resultado: ResultadoRegla) -> tuple[str, ...]:
    """Las franjas donde el modelo marca tormenta con granizo (código 96 o 99), con el mismo orden que `franjas_de`.

    Una hora de tormenta marcada solo por CAPE no cuenta: el CAPE alto no dice que haya granizo.
    """
    return _franjas_de_horas(
        h for h in resultado.horas if h.weather_code in umbrales.CODIGOS_GRANIZO
    )


def _frase(franjas: Sequence[str]) -> str:
    """Une las franjas en orden del día con su rango: «a la tarde (12 a 18 h) y a la noche (18 a 24 h)»."""
    if not franjas:
        raise ValueError("un aviso necesita al menos una franja")
    desconocidas = set(franjas) - set(FRANJAS)
    if desconocidas:
        raise ValueError("franja desconocida")
    frases = [_FRASE_DE_FRANJA[f] for f in FRANJAS if f in franjas]
    if len(frases) == 1:
        return frases[0]
    return f"{', '.join(frases[:-1])} y {frases[-1]}"


def _titulo(zona: Zona) -> str:
    return f"SkyPulse · {zona.nombre}"


def _frase_granizo(franjas: Sequence[str], granizo: Sequence[str]) -> str:
    """«Posible granizo.» si alcanza a todas las franjas; si no, dice en cuáles. Vacío si no hay granizo."""
    if not granizo:
        return ""
    desconocidas = set(granizo) - set(FRANJAS)
    if desconocidas or not set(granizo) <= set(franjas):
        raise ValueError("el granizo tiene que caer dentro de las franjas del aviso")
    if set(granizo) == set(franjas):
        return " Posible granizo."
    return f" Posible granizo {_frase(granizo)}."


def _cuerpo(dia: str, franjas: Sequence[str], granizo: Sequence[str]) -> str:
    frase = _frase(franjas)  # valida las franjas antes que el granizo
    return (
        f"Posibles tormentas {dia} {frase}.{_frase_granizo(franjas, granizo)} {LEYENDA}"
    )


def texto_aviso_manana(
    zona: Zona, franjas: Sequence[str], granizo: Sequence[str] = ()
) -> Mensaje:
    """El aviso de la noche (21 h): posibles tormentas MAÑANA en esas franjas, y granizo si lo marca el modelo."""
    return Mensaje(titulo=_titulo(zona), cuerpo=_cuerpo("mañana", franjas, granizo))


def texto_aviso_hoy(
    zona: Zona, franjas: Sequence[str], granizo: Sequence[str] = ()
) -> Mensaje:
    """El aviso de una revisión del día: posibles tormentas HOY en las franjas que quedan, y granizo si lo marca."""
    return Mensaje(titulo=_titulo(zona), cuerpo=_cuerpo("hoy", franjas, granizo))


def texto_prueba(zona: Zona) -> Mensaje:
    """La notificación de prueba: confirma que el envío funciona y aclara que los avisos automáticos aún no existen.

    Cuando el envío programado (FRA-355/356) esté activo, este texto vuelve al borrador original:
    "Así vas a ver los avisos de tormenta para {zona}. Si te llegó, está todo listo."
    """
    return Mensaje(
        titulo="SkyPulse · Prueba",
        cuerpo=(
            f"Esto es un aviso de prueba para {zona.nombre}. "
            "Los avisos automáticos de tormenta todavía no están activos."
        ),
    )
