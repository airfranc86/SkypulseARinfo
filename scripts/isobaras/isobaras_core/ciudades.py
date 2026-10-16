"""The cities drawn on the map: picked once from Natural Earth and committed as a TypeScript module.

    uv run python -m isobaras_core.ciudades

Natural Earth is public domain (commercial use allowed, no attribution required), the same source as the map's
background (`base.py`). This script downloads its populated places, keeps the ones inside the box the isobar files
cover, in Argentina, Chile, Uruguay, Paraguay, Bolivia and Brazil, gives each a level (1 = the biggest, always on
screen; 3 = shown only when zoomed in) and writes `apps/frontend/src/lib/mapa/ciudadesDatos.ts`. It only has to be
run again if the box, the countries or the thresholds change; the frontend imports the committed file.

Exit codes: 0 = written, 4 = the download or the file was not usable (nothing is written).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, TextIO

from . import red

FUENTE = "Natural Earth"
# A fixed release, not `master`: regenerating the file later must give the same cities.
URL_FUENTE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_10m_populated_places_simple.geojson"
TOPE_DESCARGA = 12_000_000  # the file is ~5 MB
SALIDA_POR_DEFECTO = Path(__file__).resolve().parents[3] / "apps" / "frontend" / "src" / "lib" / "mapa" / "ciudadesDatos.ts"

# lat_min, lon_min, lat_max, lon_max: the area the isobar files cover (same as `hora.BBOX`).
CAJA: tuple[float, float, float, float] = (-62.0, -90.0, -12.0, -30.0)

# Natural Earth's `adm0name` -> the ISO code the frontend uses.
PAISES: dict[str, str] = {"Argentina": "AR", "Chile": "CL", "Uruguay": "UY", "Paraguay": "PY", "Bolivia": "BO", "Brazil": "BR"}

CAPITALES_NACIONALES = ("Admin-0 capital", "Admin-0 capital alt")
CAPITAL_DE_PROVINCIA = "Admin-1 capital"
# Population needed for level 1, 2 and 3 (a national capital is always level 1; a province capital is level 2 or 3).
UMBRALES_POR_DEFECTO = (1_500_000, 500_000, 150_000)
# A province capital smaller than this (the Paraguayan Chaco has some of 5 000 people) is only shown when zoomed in.
POBLACION_CAPITAL_RELEVANTE = 50_000
# Brazil has 240 places in the box, many of them suburbs of a handful of big cities: it asks for more people.
# Argentina lowers level 3 to 100 000 so the big cities of Patagonia (Comodoro Rivadavia) are there.
UMBRALES_POR_PAIS = {"BR": (3_000_000, 1_500_000, 700_000), "AR": (1_500_000, 500_000, 100_000)}
# A place that is not a capital and is closer than this to a bigger one is part of the same urban area (Santo André
# next to São Paulo).
RADIO_MINIMO_GRADOS = 0.5

Ciudad = dict[str, Any]

# Natural Earth 5.1.2 has some stale or wrong entries in this region. Small, explicit corrections, by (country, name as
# written in the source): places to leave out and names to write properly.
EXCLUIDAS: frozenset[tuple[str, str]] = frozenset(
    {
        ("PY", "Capitan Pablo Lagerenza"),  # capital of a department abolished in 1992
        ("PY", "General Eugenio Alejandrino Garay"),  # same
        ("PY", "Pozo Colorado"),  # not the capital of Presidente Hayes any more (it is Villa Hayes)
        ("PY", "Mariscal Estigarribia"),  # not the capital of Boquerón any more (it is Filadelfia)
        ("PY", "Ypacaraí"),  # not the capital of Central any more (it is Areguá)
        ("BR", "Guaira"),  # tagged as a state capital; it is a small town
        ("BO", "Santa Ana"),  # a population of 234 000 that does not match the town
    }
)
RENOMBRADAS: dict[tuple[str, str], str] = {
    ("AR", "San Nicolas"): "San Nicolás",
    ("CL", "Coihaique"): "Coyhaique",
}


def nivel_de(pais: str, clase: str, poblacion: float) -> int | None:
    """1 = always on screen, 3 = only when zoomed in, None = not drawn."""
    if pais not in PAISES.values():
        return None
    umbral_1, umbral_2, umbral_3 = UMBRALES_POR_PAIS.get(pais, UMBRALES_POR_DEFECTO)
    if clase in CAPITALES_NACIONALES or poblacion >= umbral_1:
        return 1
    if poblacion >= umbral_2:
        return 2
    if clase == CAPITAL_DE_PROVINCIA:
        return 2 if poblacion >= POBLACION_CAPITAL_RELEVANTE else 3
    if poblacion >= umbral_3:
        return 3
    return None


def _candidata(lugar: Any) -> tuple[Ciudad, bool] | None:
    """A usable place as (city, is it a capital), or None if it is not usable or not drawn."""
    if not isinstance(lugar, Mapping):
        return None
    props, geometria = lugar.get("properties"), lugar.get("geometry")
    if not isinstance(props, Mapping) or not isinstance(geometria, Mapping):
        return None
    pais = PAISES.get(str(props.get("adm0name")))
    nombre = props.get("name")
    coordenadas = geometria.get("coordinates")
    if pais is None or not isinstance(nombre, str) or not nombre.strip():
        return None
    if not isinstance(coordenadas, Sequence) or len(coordenadas) < 2:
        return None
    lon, lat = coordenadas[0], coordenadas[1]
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (lat, lon)):
        return None
    lat_min, lon_min, lat_max, lon_max = CAJA
    if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
        return None
    bruto = props.get("pop_max")
    poblacion = int(bruto) if isinstance(bruto, (int, float)) and math.isfinite(bruto) and bruto > 0 else 0
    clase = str(props.get("featurecla"))
    nivel = nivel_de(pais, clase, poblacion)
    if nivel is None:
        return None
    nombre = nombre.strip()
    if (pais, nombre) in EXCLUIDAS:
        return None
    nombre = RENOMBRADAS.get((pais, nombre), nombre)
    ciudad = {"nombre": nombre, "pais": pais, "lat": round(lat, 2), "lon": round(lon, 2), "nivel": nivel, "pob": poblacion}
    return ciudad, clase in CAPITALES_NACIONALES or clase == CAPITAL_DE_PROVINCIA


def _distancia_grados(a: Ciudad, b: Ciudad) -> float:
    """Rough distance in degrees (longitude scaled by latitude): enough to tell neighbours from different cities."""
    return math.hypot(a["lat"] - b["lat"], (a["lon"] - b["lon"]) * math.cos(math.radians((a["lat"] + b["lat"]) / 2)))


def elegir_ciudades(lugares: Sequence[Any]) -> list[Ciudad]:
    """The cities to draw, biggest first. The same input always gives the same list (ties go by name)."""
    candidatas = [c for c in map(_candidata, lugares) if c is not None]
    candidatas.sort(key=lambda par: (-par[0]["pob"], par[0]["nombre"]))
    elegidas: list[Ciudad] = []
    for ciudad, es_capital in candidatas:
        # Capitals are never dropped, even next to a bigger city (Corrientes and Resistencia are twins).
        if not es_capital and any(_distancia_grados(ciudad, otra) < RADIO_MINIMO_GRADOS for otra in elegidas):
            continue
        elegidas.append(ciudad)
    return _desambiguar(elegidas)


def _desambiguar(ciudades: list[Ciudad]) -> list[Ciudad]:
    """A name that two countries share (Concepción in Chile and Paraguay) gets its country: "Concepción (CL)"."""
    repetidos = {n for n in (c["nombre"] for c in ciudades) if sum(1 for c in ciudades if c["nombre"] == n) > 1}
    return [{**c, "nombre": f"{c['nombre']} ({c['pais']})"} if c["nombre"] in repetidos else c for c in ciudades]


def _literal(texto: str) -> str:
    """A TypeScript string literal in single quotes: backslash, quote and line breaks escaped."""
    escapado = texto.replace("\\", "\\\\").replace("'", "\\'")
    for caracter, secuencia in (("\n", "\\n"), ("\r", "\\r"), ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        escapado = escapado.replace(caracter, secuencia)
    return "'" + escapado + "'"


def a_typescript(ciudades: Sequence[Ciudad]) -> str:
    """The TypeScript module the frontend imports."""
    lineas = [
        f"// Generated by scripts/isobaras/isobaras_core/ciudades.py from {FUENTE} (public domain, v5.1.2). Do not edit by hand:",
        "// run `uv run python -m isobaras_core.ciudades` from scripts/isobaras instead.",
        "",
        "export interface CiudadDelMapa {",
        "  nombre: string",
        "  /** ISO 3166-1 alpha-2 code of the country. */",
        "  pais: string",
        "  lat: number",
        "  lon: number",
        "  /** 1 = always on screen, 3 = only when zoomed in. */",
        "  nivel: 1 | 2 | 3",
        "  /** Population of the urban area (the biggest first when two names collide on screen). */",
        "  pob: number",
        "}",
        "",
        "export const CIUDADES_DEL_MAPA: readonly CiudadDelMapa[] = [",
    ]
    for c in ciudades:
        lineas.append(
            f"  {{ nombre: {_literal(c['nombre'])}, pais: {_literal(c['pais'])}, lat: {c['lat']}, lon: {c['lon']}, nivel: {c['nivel']}, pob: {c['pob']} }},"
        )
    lineas.append("]")
    return "\n".join(lineas) + "\n"


def main(
    argv: Sequence[str] | None = None,
    *,
    fetch: Callable[..., bytes] = red.fetch,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    salida_texto, errores = out or sys.stdout, err or sys.stderr
    parser = argparse.ArgumentParser(prog="isobaras_core.ciudades", description=__doc__.splitlines()[0])
    parser.add_argument("--salida", type=Path, default=SALIDA_POR_DEFECTO, help="where to write ciudadesDatos.ts")
    args = parser.parse_args(argv)

    try:
        datos = json.loads(fetch(URL_FUENTE, None, tope=TOPE_DESCARGA))
        lugares = datos.get("features") if isinstance(datos, Mapping) else None
        if not isinstance(lugares, list):
            raise ValueError("el archivo no es una colección de lugares")
        ciudades = elegir_ciudades(lugares)
        if not ciudades:
            raise ValueError("ninguna ciudad cae en la zona y los países pedidos")
        # Encoded before the file is touched: a name that cannot be written leaves the old file as it was.
        contenido = a_typescript(ciudades).encode("utf-8")
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        args.salida.write_bytes(contenido)
    except (OSError, ValueError) as e:  # json and encoding errors are ValueError
        print(f"no se pudo armar la lista de ciudades: {e}", file=errores)
        return 4
    por_nivel = ", ".join(f"nivel {n}: {sum(1 for c in ciudades if c['nivel'] == n)}" for n in (1, 2, 3))
    print(f"{len(ciudades)} ciudades ({por_nivel}) en {args.salida}", file=salida_texto)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
