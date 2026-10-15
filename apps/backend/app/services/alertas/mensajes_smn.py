"""Text of the push for an OFFICIAL storm alert of the SMN (FRA-359, T2).

It is NOT the forecast push of `textos.py`: the body speaks of the official notice (level in words, "Fuente: SMN"),
so the legend "no es un aviso oficial" that closes the forecast push does not apply here, and no hour of the storm is
ever said. If the notice starts later than `ahora` (the SMN publishes some alerts hours ahead; the owner chose to
notify as soon as they are published, L8) the body says since when it is in force, in Argentina time; a notice
already in force just says so. The free text of the feed (`descripcion`, `instruccion`) is never relayed: it is long,
it changes with every update of the same alert and a notification has no room for it.

Only storm alerts of level amarillo, naranja or rojo get here (`smn_alertas.es_aviso_de_tormenta_notificable`,
T1); any other level is a programming error and is refused. The feed is CC BY 4.0 (verified, L6): the attribution
the push carries is "Fuente: SMN".

The texts are a DRAFT the owner approves before the merge: changing a sentence is touching this file, and only this
file. Plain text: a notification renders no markdown.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.schemas.smn_alertas import SmnAlerta
from app.services.alertas.textos import Mensaje
from app.services.alertas.zonas import Zona

__all__ = ["FUENTE", "Mensaje", "NIVELES_CON_PALABRA", "texto_aviso_smn"]

# Argentina time (no DST), the same offset `textos.py` and `regla.py` use.
_AR = timezone(timedelta(hours=-3))

# The attribution of the official notice. The feed is CC BY 4.0; the push only names the source.
FUENTE = "Fuente: SMN"

# The level, in words, as the body says it. Only these levels are pushed (S1); `nivel` is free text in the schema,
# so anything else (``otro``, a new colour) is refused here rather than printed.
NIVELES_CON_PALABRA: dict[str, str] = {
    "amarillo": "amarillo",
    "naranja": "naranja",
    "rojo": "rojo",
}

# Only storm alerts are pushed in this stage (S8): the phenomenon is fixed, not read from `tipo`.
_FENOMENO = "tormentas"


def _titulo(zona: Zona) -> str:
    """The same title as the forecast push: the city, so the person knows which subscription it is."""
    return f"SkyPulse · {zona.nombre}"


def _en_argentina(momento: datetime) -> datetime:
    """`momento` in Argentina time. A naive datetime is read as UTC (the CAP feed carries offsets, so this is a guard,
    not the expected path)."""
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(_AR)


def _hora(local: datetime) -> str:
    """«las 15 h», or «las 15:30 h» when the notice does not start on the hour."""
    if local.minute == 0:
        return f"las {local.hour} h"
    return f"las {local.hour}:{local.minute:02d} h"


def frase_de_inicio(fecha_desde: datetime | None, ahora: datetime) -> str:
    """«Rige desde las 15 h.» (today), «Rige desde mañana a las 9 h.» or «Rige desde el 16/10 a las 9:30 h.», in
    Argentina time, for a notice that starts AFTER `ahora`. Empty for a notice already in force or without a start:
    then the body says it is in force and names no hour at all."""
    if fecha_desde is None:
        return ""
    inicio, hoy = _en_argentina(fecha_desde), _en_argentina(ahora)
    if inicio <= hoy:
        return ""
    if inicio.date() == hoy.date():
        return f"Rige desde {_hora(inicio)}."
    if inicio.date() == hoy.date() + timedelta(days=1):
        return f"Rige desde mañana a {_hora(inicio)}."
    return f"Rige desde el {inicio.day}/{inicio.month:02d} a {_hora(inicio)}."


def texto_aviso_smn(zona: Zona, alerta: SmnAlerta, *, ahora: datetime) -> Mensaje:
    """The push of an official SMN storm alert for `zona`.

    `ahora` (time-zone aware) decides whether the notice is already in force or the body says since when it is;
    the caller injects it, like everywhere else in the evaluation (this module never reads the wall clock).

    Raises:
        ValueError: `alerta.nivel` is not one of the levels that are pushed (amarillo, naranja, rojo).
    """
    palabra = NIVELES_CON_PALABRA.get(alerta.nivel)
    if palabra is None:
        raise ValueError("nivel sin palabra para el aviso")
    inicio = frase_de_inicio(alerta.fecha_desde, ahora)
    if inicio:
        cuerpo = f"Aviso oficial de nivel {palabra} por {_FENOMENO}. {inicio} {FUENTE}"
    else:
        cuerpo = f"Aviso oficial de nivel {palabra} por {_FENOMENO}, ya vigente. {FUENTE}"
    return Mensaje(titulo=_titulo(zona), cuerpo=cuerpo)
