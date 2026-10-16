"""The map's own background: coastlines and borders, built once from Natural Earth and committed as a static file.

    uv run python -m isobaras_core.base

Natural Earth is public domain (commercial use allowed, no attribution required), so the map needs no key and no
third-party tile server. This script downloads three line layers (coastline, land borders between countries, and
the borders of provinces/states), clips them to a box a little bigger than what the map can show, simplifies them
and writes `apps/frontend/public/mapa/base.json` (a few tens of KB). It only has to be run again if the box or the
tolerances change; the frontend reads the committed file from its own origin.

File format (v1), same idea as the isobar files: integers in 0.01 degrees, the first lat,lon pair of a line is
absolute and the next ones are differences from the previous point.

Exit codes: 0 = written, 4 = a download or a file was not usable (nothing is written).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TextIO

import numpy as np

from . import red
from .curvas import simplificar

FUENTE = "Natural Earth"
ESCALA = 100
# lat_min, lon_min, lat_max, lon_max: the isobar box (-62..-12, -90..-30) plus the 10 degrees the map can pan, plus 2.
CAJA: tuple[float, float, float, float] = (-74.0, -102.0, 0.0, -18.0)
TOLERANCIA_GRADOS = 0.03
LARGO_MINIMO_GRADOS = 0.1  # drops specks: a coastline run shorter than this is not worth a request byte
TOPE_DESCARGA = 40_000_000  # the 10m provinces file is ~21 MB

# A fixed release, not `master`: regenerating the file later must give the same lines.
_BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson"
CAPAS: dict[str, str] = {
    "costas": f"{_BASE}/ne_50m_coastline.geojson",
    "paises": f"{_BASE}/ne_50m_admin_0_boundary_lines_land.geojson",
    # 10m: the 50m provinces file only covers a handful of countries (Argentina is not one of them).
    "provincias": f"{_BASE}/ne_10m_admin_1_states_provinces_lines.geojson",
}
SALIDA_POR_DEFECTO = Path(__file__).resolve().parents[3] / "apps" / "frontend" / "public" / "mapa" / "base.json"

Caja = tuple[float, float, float, float]

# A line whose class says it is not a settled border is left out: drawing it like a defined one would take a side.
# (E.g. the Southern Patagonian Ice Field segment is "Indefinite (please verify)": pending demarcation.)
_CLASES_NO_DEFINIDAS = ("indefinite", "disputed", "line of control", "overlay limit")


class ErrorDeBase(ValueError):
    """A source file does not look like the GeoJSON lines we expect."""


def _segmento_dentro(a: np.ndarray, b: np.ndarray, caja: Caja) -> tuple[float, float] | None:
    """Liang-Barsky: the parameters (t0, t1) of the part of the segment a->b inside the box, or None."""
    lat_min, lon_min, lat_max, lon_max = caja
    t0, t1 = 0.0, 1.0
    d = b - a
    for delta, distancia in (
        (d[0], a[0] - lat_min),
        (-d[0], lat_max - a[0]),
        (d[1], a[1] - lon_min),
        (-d[1], lon_max - a[1]),
    ):
        if delta == 0:
            if distancia < 0:
                return None
            continue
        t = -distancia / delta
        if delta > 0:
            if t > t1:
                return None
            t0 = max(t0, t)
        else:
            if t < t0:
                return None
            t1 = min(t1, t)
    return (t0, t1) if t0 < t1 else None  # touching a corner at a single point is not a run


def recortar_linea(puntos: np.ndarray, caja: Caja) -> list[np.ndarray]:
    """The parts of a `[lat, lon]` polyline that fall inside `caja`, cut exactly at its edges."""
    if len(puntos) < 2:
        return []
    tramos: list[np.ndarray] = []
    actual: list[np.ndarray] = []

    def cerrar() -> None:
        if len(actual) >= 2:
            tramos.append(np.array(actual))
        actual.clear()

    for a, b in zip(puntos[:-1], puntos[1:]):
        dentro = _segmento_dentro(a, b, caja)
        if dentro is None:
            cerrar()
            continue
        t0, t1 = dentro
        entrada = a + (b - a) * t0
        salida = a + (b - a) * t1
        if t0 > 0.0:  # it came in from outside: a new run starts on the edge
            cerrar()
        if not actual:
            actual.append(entrada)
        actual.append(salida)
        if t1 < 1.0:  # it goes out: the run ends on the edge
            cerrar()
    cerrar()
    return tramos


def leer_lineas_geojson(datos: Any) -> list[np.ndarray]:
    """Every LineString and MultiLineString of a GeoJSON FeatureCollection, as `[lat, lon]` arrays."""
    if not isinstance(datos, dict) or not isinstance(datos.get("features"), list):
        raise ErrorDeBase("no es un GeoJSON de tipo FeatureCollection")
    lineas: list[np.ndarray] = []
    for elemento in datos["features"]:
        geometria = elemento.get("geometry") if isinstance(elemento, dict) else None
        if not isinstance(geometria, dict):
            continue
        propiedades = elemento.get("properties")
        clase = str(propiedades.get("FEATURECLA", "")).lower() if isinstance(propiedades, dict) else ""
        if clase.startswith(_CLASES_NO_DEFINIDAS):
            continue
        tipo, coordenadas = geometria.get("type"), geometria.get("coordinates")
        if tipo == "LineString":
            partes = [coordenadas]
        elif tipo == "MultiLineString":
            partes = coordenadas
        else:
            continue
        for parte in partes:
            try:
                lon_lat = np.array(parte, dtype=float)
            except (TypeError, ValueError) as e:
                raise ErrorDeBase("una línea tiene coordenadas que no son números") from e
            if lon_lat.ndim != 2 or lon_lat.shape[1] < 2:
                raise ErrorDeBase("una línea no tiene el formato [lon, lat]")
            lineas.append(lon_lat[:, [1, 0]])  # the file is [lon, lat]; the pipeline works in [lat, lon]
    return lineas


def _largo(linea: np.ndarray) -> float:
    return float(np.hypot(*np.diff(linea, axis=0).T).sum())


def _codificar_linea(linea: np.ndarray) -> list[int] | None:
    enteros = [(math.floor(lat * ESCALA + 0.5), math.floor(lon * ESCALA + 0.5)) for lat, lon in linea]
    sin_repetidos = [p for i, p in enumerate(enteros) if i == 0 or p != enteros[i - 1]]
    if len(sin_repetidos) < 2:
        return None
    c: list[int] = list(sin_repetidos[0])
    for previo, actual in zip(sin_repetidos[:-1], sin_repetidos[1:]):
        c.extend((actual[0] - previo[0], actual[1] - previo[1]))
    return c


def codificar_base(*, costas: Sequence[np.ndarray], paises: Sequence[np.ndarray], provincias: Sequence[np.ndarray]) -> dict:
    """The JSON object of the background file. Lines that collapse to a single point are dropped."""

    def capa(lineas: Sequence[np.ndarray]) -> list[list[int]]:
        return [c for c in (_codificar_linea(l) for l in lineas) if c is not None]

    return {
        "v": 1,
        "fuente": FUENTE,
        "scale": ESCALA,
        "caja": [CAJA[1], CAJA[0], CAJA[3], CAJA[2]],
        "costas": capa(costas),
        "paises": capa(paises),
        "provincias": capa(provincias),
    }


def _preparar(lineas: Sequence[np.ndarray]) -> list[np.ndarray]:
    """Clip to the box, drop specks and simplify."""
    resultado: list[np.ndarray] = []
    for linea in lineas:
        for tramo in recortar_linea(linea, CAJA):
            if _largo(tramo) < LARGO_MINIMO_GRADOS:
                continue
            simple = simplificar(tramo, TOLERANCIA_GRADOS, cerrada=False)
            if simple is not None and len(simple) >= 2:
                resultado.append(simple)
    return resultado


def main(
    argv: Sequence[str] | None = None,
    *,
    fetch: Callable[..., bytes] = red.fetch,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    salida_texto, errores = out or sys.stdout, err or sys.stderr
    parser = argparse.ArgumentParser(prog="isobaras_core.base", description=__doc__.splitlines()[0])
    parser.add_argument("--salida", type=Path, default=SALIDA_POR_DEFECTO, help="where to write base.json")
    args = parser.parse_args(argv)

    capas: dict[str, list[np.ndarray]] = {}
    try:
        for nombre, url in CAPAS.items():
            capas[nombre] = _preparar(leer_lineas_geojson(json.loads(fetch(url, None, tope=TOPE_DESCARGA))))
    except (OSError, ValueError) as e:  # ErrorDeBase and json errors are ValueError
        print(f"no se pudo armar la base: {e}", file=errores)
        return 4

    base = codificar_base(**capas)
    texto = json.dumps(base, separators=(",", ":"), ensure_ascii=False)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(texto, encoding="utf-8")
    total = sum(len(base[n]) for n in CAPAS)
    print(f"{total} líneas ({len(base['costas'])} costas, {len(base['paises'])} fronteras, {len(base['provincias'])} provincias), {len(texto) / 1024:.0f} KB en {args.salida}", file=salida_texto)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
