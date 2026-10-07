"""Textos de las notificaciones de alertas push (FRA-354).

Un solo nivel de aviso y texto neutro. El horario va en franjas del día, nunca en horas exactas: el
pronóstico no tiene esa precisión y una hora puntual se lee como una promesa. Todo aviso de tormenta termina
con la leyenda que aclara que no es un aviso oficial. Son texto plano: una notificación no renderiza
markdown, así que la leyenda no lleva un enlace.

Los textos son un BORRADOR que el dueño aprueba antes del merge: cambiar una frase es tocar este archivo.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

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

_FRASE_DE_FRANJA = {
    "madrugada": "de madrugada",
    "mañana": "a la mañana",
    "tarde": "a la tarde",
    "noche": "a la noche",
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


def franjas_de(resultado: ResultadoRegla) -> tuple[str, ...]:
    """Las franjas del día con al menos una hora de tormenta, sin repetir y de la más temprana a la más tardía."""
    presentes = {
        franja(datetime.fromtimestamp(h.timestamp, _AR).hour) for h in resultado.horas
    }
    return tuple(f for f in FRANJAS if f in presentes)


def _frase(franjas: Sequence[str]) -> str:
    """Une las franjas en orden del día: «a la tarde y a la noche», «de madrugada, a la mañana y a la tarde»."""
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


def texto_aviso_manana(zona: Zona, franjas: Sequence[str]) -> Mensaje:
    """El aviso de la noche (21 h): posibles tormentas MAÑANA en esas franjas."""
    return Mensaje(
        titulo=_titulo(zona),
        cuerpo=f"Posibles tormentas mañana {_frase(franjas)}. {LEYENDA}",
    )


def texto_aviso_hoy(zona: Zona, franjas: Sequence[str]) -> Mensaje:
    """El aviso de una revisión del día: posibles tormentas HOY en las franjas que quedan."""
    return Mensaje(
        titulo=_titulo(zona),
        cuerpo=f"Posibles tormentas hoy {_frase(franjas)}. {LEYENDA}",
    )


def texto_prueba(zona: Zona) -> Mensaje:
    """La notificación de prueba: muestra cómo se ven los avisos y confirma que el envío funciona."""
    return Mensaje(
        titulo="SkyPulse · Prueba",
        cuerpo=(
            f"Así vas a ver los avisos de tormenta para {zona.nombre}. "
            "Si te llegó, está todo listo."
        ),
    )
