"""Contract v1 of the pressure-map files: `manifest.json` and one `isobaras_fNNN.json` per forecast hour.

The pipeline writes them with `codificar_*`; `leer_*` validate and decode them (the pipeline checks its own
output with them before publishing). The frontend has the mirror module `src/lib/isobaras/formato.ts` and
both are tested against the same fixtures in `apps/frontend/tests/fixtures/isobaras/`.

Coordinates travel as integers in units of 1/scale degrees (0.01 degrees with scale 100). In a line's `c`
the first lat,lon pair is absolute and the following ones are differences from the previous point. A
closed line does not repeat its first point: the client closes it when drawing.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

MOTIVOS = ("version", "formato", "fuera-de-bbox", "ciclo-cambiado")

# ASCII digits and `fullmatch` on purpose: `\d` accepts other scripts' digits and `$` accepts a trailing newline,
# neither of which the JavaScript reader accepts. The two readers must accept exactly the same files.
_FECHA = re.compile(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}Z")
_ARCHIVO_HORA = re.compile(r"isobaras_f[0-9]{3}\.json")

# The files come from a third-party host: bound everything before drawing it.
MAX_ABS = 2**31  # any integer in a file; also keeps TypeScript far from the 2**53 precision limit
MAX_BBOX_ABS = 360
MAX_HORAS = 129
MAX_LINEAS = 200
MAX_PUNTOS_POR_LINEA = 5000
MAX_ETIQUETAS_POR_LINEA = 2
MAX_CENTROS = 30


class FormatoInvalido(ValueError):
    """A file does not match the contract. `motivo` is one of `MOTIVOS`."""

    def __init__(self, motivo: str, detalle: str) -> None:
        super().__init__(detalle)
        self.motivo = motivo


@dataclass(frozen=True)
class Bbox:
    lon_min: float
    lat_min: float
    lon_max: float
    lat_max: float


@dataclass(frozen=True)
class HoraDelManifest:
    f: int
    valid: str
    file: str


@dataclass(frozen=True)
class Manifest:
    source: str
    cycle: str
    generated: str
    bbox: Bbox
    interval_hpa: int
    scale: int
    hours: tuple[HoraDelManifest, ...]


@dataclass(frozen=True)
class Linea:
    p: int
    cerrada: bool
    puntos: tuple[tuple[float, float], ...]
    etiquetas: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class Centro:
    t: str
    p: int
    lat: float
    lon: float


@dataclass(frozen=True)
class Hora:
    cycle: str
    f: int
    valid: str
    lineas: tuple[Linea, ...]
    centros: tuple[Centro, ...]


def _rechazar(motivo: str, detalle: str) -> Any:
    raise FormatoInvalido(motivo, detalle)


def _a_entero_json(x: object) -> int | None:
    """An integer written as `1`, `1.0` or `1e0` (JavaScript cannot tell them apart, so neither do we), or None."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    if not abs(x) <= MAX_ABS:  # also False for NaN, and safe for huge ints
        return None
    if isinstance(x, float):
        return int(x) if x.is_integer() else None
    return x


def _objeto(x: object, donde: str) -> dict:
    return x if isinstance(x, dict) else _rechazar("formato", f"{donde}: se esperaba un objeto")


def _entero(x: object, donde: str) -> int:
    n = _a_entero_json(x)
    return n if n is not None else _rechazar("formato", f"{donde}: se esperaba un entero")


def _fecha(x: object, donde: str) -> str:
    if isinstance(x, str) and _FECHA.fullmatch(x):
        try:
            datetime.strptime(x, "%Y-%m-%dT%H:%MZ")
            return x
        except ValueError:
            pass
    return _rechazar("formato", f"{donde}: se esperaba AAAA-MM-DDTHH:MMZ")


def _lista(x: object, donde: str, maximo: int | None = None) -> list:
    if not isinstance(x, list):
        _rechazar("formato", f"{donde}: se esperaba una lista")
    if maximo is not None and len(x) > maximo:  # type: ignore[arg-type]
        _rechazar("formato", f"{donde}: más de {maximo} elementos")
    return x  # type: ignore[return-value]


def _version(raw: dict) -> None:
    v = _entero(raw.get("v"), "v")
    if v != 1:
        _rechazar("version", f"versión {v} desconocida")


def leer_manifest(raw: object) -> Manifest:
    """Validate and decode `manifest.json`."""
    m = _objeto(raw, "manifest")
    _version(m)
    caja = _lista(m.get("bbox"), "bbox")
    if len(caja) != 4 or not all(
        isinstance(n, (int, float)) and not isinstance(n, bool) and abs(n) <= MAX_BBOX_ABS for n in caja
    ):
        _rechazar("formato", "bbox: se esperaban 4 números")
    lon_min, lat_min, lon_max, lat_max = caja
    if lon_min >= lon_max or lat_min >= lat_max:
        _rechazar("formato", "bbox: mínimos mayores que máximos")
    interval_hpa = _entero(m.get("interval_hpa"), "interval_hpa")
    scale = _entero(m.get("scale"), "scale")
    if interval_hpa <= 0 or scale <= 0:
        _rechazar("formato", "interval_hpa y scale tienen que ser positivos")
    if not isinstance(m.get("source"), str):
        _rechazar("formato", "source: se esperaba texto")
    horas: list[HoraDelManifest] = []
    for i, h in enumerate(_lista(m.get("hours"), "hours", MAX_HORAS)):
        hora = _objeto(h, f"hours[{i}]")
        f = _entero(hora.get("f"), f"hours[{i}].f")
        if f < 0:
            _rechazar("formato", f"hours[{i}].f: no puede ser negativo")
        archivo = hora.get("file")
        if not isinstance(archivo, str) or not _ARCHIVO_HORA.fullmatch(archivo):
            _rechazar("formato", f"hours[{i}].file: nombre de archivo no permitido")
        horas.append(HoraDelManifest(f, _fecha(hora.get("valid"), f"hours[{i}].valid"), archivo))
    if not horas:
        _rechazar("formato", "hours: no puede estar vacía")
    if any(b.f <= a.f for a, b in zip(horas, horas[1:])):
        _rechazar("formato", "hours: las horas tienen que ir en orden creciente")
    return Manifest(
        source=m["source"],
        cycle=_fecha(m.get("cycle"), "cycle"),
        generated=_fecha(m.get("generated"), "generated"),
        bbox=Bbox(lon_min, lat_min, lon_max, lat_max),
        interval_hpa=interval_hpa,
        scale=scale,
        hours=tuple(horas),
    )


def codificar_manifest(manifest: Manifest) -> dict:
    """The JSON object for `manifest.json`."""
    b = manifest.bbox
    return {
        "v": 1,
        "source": manifest.source,
        "cycle": manifest.cycle,
        "generated": manifest.generated,
        "bbox": [b.lon_min, b.lat_min, b.lon_max, b.lat_max],
        "interval_hpa": manifest.interval_hpa,
        "scale": manifest.scale,
        "hours": [{"f": h.f, "valid": h.valid, "file": h.file} for h in manifest.hours],
    }


def _dentro(lat: float, lon: float, bbox: Bbox) -> bool:
    return bbox.lat_min <= lat <= bbox.lat_max and bbox.lon_min <= lon <= bbox.lon_max


def _en_bbox(lat: float, lon: float, bbox: Bbox, donde: str) -> tuple[float, float]:
    if not _dentro(lat, lon, bbox):
        _rechazar("fuera-de-bbox", f"{donde}: fuera del recorte del manifest")
    return lat, lon


def leer_hora(raw: object, manifest: Manifest) -> Hora:
    """Validate and decode one hour file against its manifest (same rules as the TypeScript reader)."""
    h = _objeto(raw, "hora")
    _version(h)
    if _entero(h.get("scale"), "scale") != manifest.scale:
        _rechazar("formato", "scale: distinta de la del manifest")
    cycle = _fecha(h.get("cycle"), "cycle")
    if cycle != manifest.cycle:
        _rechazar("ciclo-cambiado", "el ciclo de la hora no es el del manifest")
    escala = manifest.scale
    f = _entero(h.get("f"), "f")
    valid = _fecha(h.get("valid"), "valid")
    del_manifest = next((x for x in manifest.hours if x.f == f), None)
    if del_manifest is None or del_manifest.valid != valid:
        _rechazar("formato", "f/valid: la hora no coincide con la del manifest")

    lineas: list[Linea] = []
    for i, l in enumerate(_lista(h.get("lines"), "lines", MAX_LINEAS)):
        linea = _objeto(l, f"lines[{i}]")
        p = _entero(linea.get("p"), f"lines[{i}].p")
        if not isinstance(linea.get("closed"), bool):
            _rechazar("formato", f"lines[{i}].closed: se esperaba true o false")
        c = _lista(linea.get("c"), f"lines[{i}].c", 2 * MAX_PUNTOS_POR_LINEA)
        if len(c) % 2 != 0 or len(c) < 4:
            _rechazar("formato", f"lines[{i}].c: se esperaban pares lat,lon (al menos 2)")
        puntos: list[tuple[float, float]] = []
        lat = lon = 0
        for k in range(0, len(c), 2):
            d_lat = _entero(c[k], f"lines[{i}].c[{k}]")
            d_lon = _entero(c[k + 1], f"lines[{i}].c[{k + 1}]")
            lat, lon = (d_lat, d_lon) if k == 0 else (lat + d_lat, lon + d_lon)
            puntos.append(_en_bbox(lat / escala, lon / escala, manifest.bbox, f"lines[{i}].c[{k}]"))
        if linea["closed"] and (len(puntos) < 3 or puntos[-1] == puntos[0]):
            _rechazar("formato", f"lines[{i}]: una curva cerrada necesita 3 puntos y no repite el primero")
        etiquetas: list[tuple[float, float]] = []
        for j, e in enumerate(_lista(linea.get("labels"), f"lines[{i}].labels", MAX_ETIQUETAS_POR_LINEA)):
            par = _lista(e, f"lines[{i}].labels[{j}]")
            if len(par) != 2:
                _rechazar("formato", f"lines[{i}].labels[{j}]: se esperaba [lat, lon]")
            e_lat = _entero(par[0], "label lat") / escala
            e_lon = _entero(par[1], "label lon") / escala
            etiquetas.append(_en_bbox(e_lat, e_lon, manifest.bbox, f"lines[{i}].labels[{j}]"))
        lineas.append(Linea(p, linea["closed"], tuple(puntos), tuple(etiquetas)))

    centros: list[Centro] = []
    for i, c in enumerate(_lista(h.get("centers"), "centers", MAX_CENTROS)):
        centro = _objeto(c, f"centers[{i}]")
        if centro.get("t") not in ("H", "L"):
            _rechazar("formato", f"centers[{i}].t: se esperaba H o L")
        c_lat = _entero(centro.get("lat"), f"centers[{i}].lat") / escala
        c_lon = _entero(centro.get("lon"), f"centers[{i}].lon") / escala
        _en_bbox(c_lat, c_lon, manifest.bbox, f"centers[{i}]")
        centros.append(Centro(centro["t"], _entero(centro.get("p"), f"centers[{i}].p"), c_lat, c_lon))

    return Hora(cycle, f, valid, tuple(lineas), tuple(centros))


def _a_entero(grados: float, escala: int) -> int:
    """Nearest integer in 1/scale degrees, halves rounded up (same rule on every platform)."""
    return math.floor(grados * escala + 0.5)


def codificar_hora(hora: Hora, escala: int) -> dict:
    """The JSON object for one `isobaras_fNNN.json`. A closed line that repeats its first point loses the repeat."""
    lineas = []
    for ln in hora.lineas:
        puntos = ln.puntos
        enteros = [(_a_entero(lat, escala), _a_entero(lon, escala)) for lat, lon in puntos]
        if ln.cerrada and len(enteros) > 1 and enteros[-1] == enteros[0]:  # compared after rounding
            enteros.pop()
        c: list[int] = []
        previo = (0, 0)
        for k, actual in enumerate(enteros):
            c.extend(actual if k == 0 else (actual[0] - previo[0], actual[1] - previo[1]))
            previo = actual
        etiquetas = [[_a_entero(lat, escala), _a_entero(lon, escala)] for lat, lon in ln.etiquetas]
        lineas.append({"p": ln.p, "closed": ln.cerrada, "c": c, "labels": etiquetas})
    centros = [
        {"t": c.t, "p": c.p, "lat": _a_entero(c.lat, escala), "lon": _a_entero(c.lon, escala)} for c in hora.centros
    ]
    return {
        "v": 1,
        "cycle": hora.cycle,
        "f": hora.f,
        "valid": hora.valid,
        "scale": escala,
        "lines": lineas,
        "centers": centros,
    }
