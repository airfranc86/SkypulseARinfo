"""From a pressure grid to isobar lines: smooth, trace every `intervalo` hPa, simplify, and place labels.

Lines are `(n, 2)` arrays of `[lat, lon]` in degrees. Distances here are plain degrees on the lat/lon
plane, which is what the tolerances (0.03 degrees) and label rules (4, 25 and 1.5 degrees) are written in.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from contourpy import LineType, contour_generator
from scipy.ndimage import gaussian_filter

from .formato import Bbox
from .grib import Campo

LARGO_MINIMO_ETIQUETA = 4.0
LARGO_DOS_ETIQUETAS = 25.0
MARGEN_BORDE_ETIQUETA = 1.5
SEPARACION_MINIMA_ETIQUETAS = 2.0
PASO_CANDIDATOS = 0.25


@dataclass(frozen=True)
class CurvaCruda:
    p: int
    cerrada: bool
    puntos: np.ndarray  # (n, 2) [lat, lon]; a closed curve does not repeat its first point


def suavizar(campo: Campo, sigma_celdas: float = 2.0) -> Campo:
    """Gaussian smoothing (sigma in grid cells) so the lines follow the synoptic pattern, not grid noise."""
    return Campo(campo.lat, campo.lon, gaussian_filter(campo.valores, sigma=sigma_celdas, mode="nearest"))


def niveles(minimo: float, maximo: float, intervalo: int) -> list[int]:
    """The multiples of `intervalo` that fall inside `[minimo, maximo]`."""
    primero = math.ceil(minimo / intervalo) * intervalo
    ultimo = math.floor(maximo / intervalo) * intervalo
    return list(range(primero, ultimo + 1, intervalo))


def trazar(campo_hpa: Campo, intervalo: int) -> list[CurvaCruda]:
    """Every isobar of the field (values in hPa), one entry per connected line."""
    generador = contour_generator(
        x=campo_hpa.lon, y=campo_hpa.lat, z=campo_hpa.valores, line_type=LineType.Separate
    )
    curvas: list[CurvaCruda] = []
    for nivel in niveles(float(campo_hpa.valores.min()), float(campo_hpa.valores.max()), intervalo):
        for linea in generador.lines(nivel):
            puntos = np.asarray(linea, dtype=float)[:, ::-1].copy()  # contourpy gives [x=lon, y=lat]
            # Points on the grid edge can come out 1 ulp outside it (e.g. -29.999999999999996): pull them back in.
            puntos[:, 0] = np.clip(puntos[:, 0], campo_hpa.lat[0], campo_hpa.lat[-1])
            puntos[:, 1] = np.clip(puntos[:, 1], campo_hpa.lon[0], campo_hpa.lon[-1])
            cerrada = len(puntos) > 3 and bool(np.array_equal(puntos[0], puntos[-1]))
            if cerrada:
                puntos = puntos[:-1]
            if len(puntos) >= (3 if cerrada else 2):
                curvas.append(CurvaCruda(nivel, cerrada, puntos))
    return curvas


def _marcar(puntos: np.ndarray, tolerancia: float) -> np.ndarray:
    """Douglas-Peucker, iterative: which points of an open polyline survive."""
    n = len(puntos)
    conservar = np.zeros(n, dtype=bool)
    conservar[0] = conservar[-1] = True
    pila = [(0, n - 1)]
    while pila:
        i, j = pila.pop()
        if j <= i + 1:
            continue
        a, b = puntos[i], puntos[j]
        medio = puntos[i + 1 : j]
        ab = b - a
        largo = math.hypot(ab[0], ab[1])
        if largo == 0:
            distancias = np.hypot(medio[:, 0] - a[0], medio[:, 1] - a[1])
        else:
            distancias = np.abs(ab[0] * (medio[:, 1] - a[1]) - ab[1] * (medio[:, 0] - a[0])) / largo
        k = int(np.argmax(distancias))
        if distancias[k] > tolerancia:
            k += i + 1
            conservar[k] = True
            pila.extend([(i, k), (k, j)])
    return conservar


def simplificar(puntos: np.ndarray, tolerancia: float, *, cerrada: bool) -> np.ndarray | None:
    """Fewer points, never further than `tolerancia` degrees from the original line.

    A closed ring is simplified including its closing segment and keeps no repeated first point; one that
    collapses below 3 points is dropped (None).
    """
    if cerrada:
        anillo = np.vstack([puntos, puntos[:1]])
        simple = anillo[_marcar(anillo, tolerancia)][:-1]
        return simple if len(simple) >= 3 else None
    return puntos[_marcar(puntos, tolerancia)]


def _largo(camino: np.ndarray) -> np.ndarray:
    """Cumulative length along a polyline, starting at 0."""
    pasos = np.hypot(*np.diff(camino, axis=0).T)
    return np.concatenate([[0.0], np.cumsum(pasos)])


def etiquetas(puntos: np.ndarray, cerrada: bool, bbox: Bbox) -> list[tuple[float, float]]:
    """Where to write the hPa value: none under 4 degrees of line, one up to 25, two beyond.

    Labels sit on the line, at least 1.5 degrees from every edge of `bbox` and 2 degrees apart. The
    spot nearest to the ideal position (the middle, or the thirds) that satisfies this is used.
    """
    camino = np.vstack([puntos, puntos[:1]]) if cerrada else puntos
    acumulado = _largo(camino)
    total = float(acumulado[-1])
    if total < LARGO_MINIMO_ETIQUETA:
        return []
    posiciones = np.arange(0.0, total + 1e-9, PASO_CANDIDATOS)
    lat = np.interp(posiciones, acumulado, camino[:, 0])
    lon = np.interp(posiciones, acumulado, camino[:, 1])
    lejos = (
        (lat >= bbox.lat_min + MARGEN_BORDE_ETIQUETA)
        & (lat <= bbox.lat_max - MARGEN_BORDE_ETIQUETA)
        & (lon >= bbox.lon_min + MARGEN_BORDE_ETIQUETA)
        & (lon <= bbox.lon_max - MARGEN_BORDE_ETIQUETA)
    )
    if not lejos.any():
        return []
    objetivos = [0.5] if total <= LARGO_DOS_ETIQUETAS else [1 / 3, 2 / 3]
    elegidas: list[tuple[float, float]] = []
    for fraccion in objetivos:
        orden = np.argsort(np.where(lejos, np.abs(posiciones - fraccion * total), np.inf))
        for idx in orden:
            if not lejos[idx]:
                break
            candidata = (float(lat[idx]), float(lon[idx]))
            if all(math.hypot(candidata[0] - e[0], candidata[1] - e[1]) >= SEPARACION_MINIMA_ETIQUETAS for e in elegidas):
                elegidas.append(candidata)
                break
    return elegidas
