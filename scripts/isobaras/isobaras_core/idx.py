"""The `.idx` index that NOAA publishes next to every GFS file.

Each line is `message:offset:d=YYYYMMDDHH:VARIABLE:level:detail:`. A message spans from its offset to the
byte before the next line's offset, so a single variable can be fetched with an HTTP `Range` request
(~1 MB for PRMSL) instead of the whole ~500 MB file.
"""

from __future__ import annotations

from dataclasses import dataclass


class IdxInvalido(ValueError):
    """The index text does not have the expected shape."""


class VariableAusente(LookupError):
    """The index has no entry for the requested variable and level."""


@dataclass(frozen=True)
class EntradaIdx:
    numero: int
    offset: int
    fecha: str
    variable: str
    nivel: str
    detalle: str


def parsear_idx(texto: str) -> tuple[EntradaIdx, ...]:
    """Parse an `.idx` file. Blank lines are skipped; anything else that is malformed is rejected."""
    entradas: list[EntradaIdx] = []
    for linea in texto.splitlines():
        if not linea.strip():
            continue
        partes = linea.split(":")
        if len(partes) < 6 or not partes[2].startswith("d="):
            raise IdxInvalido(f"línea del .idx con formato inesperado: {linea[:80]!r}")
        try:
            numero, offset = int(partes[0]), int(partes[1])
        except ValueError as e:
            raise IdxInvalido(f"número u offset inválido en la línea: {linea[:80]!r}") from e
        entradas.append(
            EntradaIdx(numero, offset, partes[2][2:], partes[3], partes[4], ":".join(partes[5:]).rstrip(":"))
        )
    for anterior, actual in zip(entradas, entradas[1:]):
        if actual.offset <= anterior.offset:
            raise IdxInvalido(f"los offsets del .idx no crecen (mensaje {actual.numero})")
    return tuple(entradas)


def rango_de(entradas: tuple[EntradaIdx, ...], variable: str, nivel: str) -> tuple[int, int | None]:
    """Byte range `(first, last)` of the message for `variable` at `nivel`, whatever its forecast suffix.

    `last` is None for the final entry of the file (its end is unknown from the index alone).
    """
    for i, entrada in enumerate(entradas):
        if entrada.variable == variable and entrada.nivel == nivel:
            fin = entradas[i + 1].offset - 1 if i + 1 < len(entradas) else None
            return entrada.offset, fin
    raise VariableAusente(f"el .idx no tiene {variable} en el nivel «{nivel}»")
