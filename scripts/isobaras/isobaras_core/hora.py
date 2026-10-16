"""Build the files the map reads (one per forecast hour, plus the manifest) from decoded pressure fields."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .ciclo import Ciclo
from .centros import detectar_centros
from .curvas import etiquetas, simplificar, suavizar, trazar
from .formato import (
    Bbox,
    Hora,
    HoraDelManifest,
    Linea,
    Manifest,
    codificar_hora,
    codificar_manifest,
    leer_hora,
    leer_manifest,
)
from .grib import Campo, recortar

BBOX = Bbox(lon_min=-90, lat_min=-62, lon_max=-30, lat_max=-12)
INTERVALO_HPA = 4
ESCALA = 100
SIGMA_CELDAS = 2.0
MARGEN_GRADOS = 6.0  # extra degrees around the box while smoothing, so the edges are not distorted
TOLERANCIA_GRADOS = 0.03
FUENTE = "NOAA GFS 0.25° PRMSL"


def _texto(fecha: datetime) -> str:
    """A timezone-aware moment as the contract writes it, always in UTC (`...Z`)."""
    if fecha.tzinfo is None:
        raise ValueError("la fecha tiene que tener zona horaria")
    return fecha.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def construir_hora(campo_pa: Campo, *, ciclo: Ciclo, f: int, terreno: Campo) -> Hora:
    """Isobar lines and H/L centers of one forecast hour from its pressure field in Pa and the terrain height in m."""
    margen = recortar(
        campo_pa,
        lat_min=BBOX.lat_min,
        lat_max=BBOX.lat_max,
        lon_min=BBOX.lon_min,
        lon_max=BBOX.lon_max,
        margen=MARGEN_GRADOS,
    )
    hpa = Campo(margen.lat, margen.lon, margen.valores / 100.0)
    suave = suavizar(hpa, SIGMA_CELDAS)
    caja = recortar(suave, lat_min=BBOX.lat_min, lat_max=BBOX.lat_max, lon_min=BBOX.lon_min, lon_max=BBOX.lon_max)
    lineas: list[Linea] = []
    for curva in trazar(caja, INTERVALO_HPA):
        simple = simplificar(curva.puntos, TOLERANCIA_GRADOS, cerrada=curva.cerrada)
        if simple is None:
            continue
        marcas = etiquetas(simple, curva.cerrada, BBOX)
        lineas.append(
            Linea(
                p=curva.p,
                cerrada=curva.cerrada,
                puntos=tuple((float(lat), float(lon)) for lat, lon in simple),
                etiquetas=tuple(marcas),
            )
        )
    lineas.sort(key=lambda ln: (ln.p, ln.puntos[0]))
    return Hora(
        cycle=ciclo.texto(),
        f=f,
        valid=_texto(ciclo.fecha + timedelta(hours=f)),
        lineas=tuple(lineas),
        centros=tuple(detectar_centros(suave, terreno, BBOX)),
    )


def construir_manifest(ciclo: Ciclo, generado: datetime, horas: tuple[int, ...] | list[int]) -> Manifest:
    """The manifest that lists `horas` (forecast hours, ascending) of `ciclo`."""
    return Manifest(
        source=FUENTE,
        cycle=ciclo.texto(),
        generated=_texto(generado),
        bbox=BBOX,
        interval_hpa=INTERVALO_HPA,
        scale=ESCALA,
        hours=tuple(
            HoraDelManifest(f, _texto(ciclo.fecha + timedelta(hours=f)), f"isobaras_f{f:03d}.json") for f in horas
        ),
    )


def _json(objeto: dict) -> str:
    return json.dumps(objeto, separators=(",", ":"), ensure_ascii=False)


def escribir(salida: Path, manifest: Manifest, horas: dict[int, Hora]) -> None:
    """Write every hour file and, last, `manifest.json`; each file is read back with the validator first.

    Nothing is written if an hour of the manifest is missing, and the manifest goes last so a reader never
    sees a manifest that points to a file that is not there yet.
    """
    faltan = [h.f for h in manifest.hours if h.f not in horas]
    if faltan:
        raise ValueError(f"faltan las horas {faltan} del manifest")
    textos: dict[str, str] = {}
    leido = leer_manifest(json.loads(_json(codificar_manifest(manifest))))
    for h in leido.hours:
        crudo = codificar_hora(horas[h.f], leido.scale)
        leer_hora(json.loads(_json(crudo)), leido)  # raises FormatoInvalido if we would publish something unreadable
        textos[h.file] = _json(crudo)
    textos["manifest.json"] = _json(codificar_manifest(manifest))
    salida.mkdir(parents=True, exist_ok=True)
    for nombre, texto in textos.items():
        (salida / nombre).write_text(texto, encoding="utf-8")

