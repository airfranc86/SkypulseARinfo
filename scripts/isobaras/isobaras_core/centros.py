"""Centers of high (H) and low (L) pressure.

A cell is a candidate when it is the extreme of a 21-cell window (~5 degrees). It becomes a center when:

- it stands out by at least 2 hPa ("flood" prominence: starting from its value, the area that stays within
  2 hPa of it must not touch a stronger extreme nor the edge of the working grid), which keeps broad
  highs that a plain window test would lose;
- it is at least 1 degree inside the box, so half of its pattern is not cut off;
- the terrain under it is not above 1500 m, because over the Andes the sea-level reduction invents centers.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import label, maximum_filter

from .formato import Bbox, Centro
from .grib import Campo

VENTANA_CELDAS = 21
PROMINENCIA_MINIMA_HPA = 2.0
MARGEN_BORDE_GRADOS = 1.0
ALTURA_MAXIMA_M = 1500.0
MAX_CENTROS = 30
PRESION_NORMAL_HPA = 1013.0


def _destaca(z: np.ndarray, i: int, j: int) -> bool:
    """True if, within `PROMINENCIA_MINIMA_HPA` below its value, the peak region reaches nothing higher nor the edge."""
    v = z[i, j]
    regiones, _ = label(z > v - PROMINENCIA_MINIMA_HPA)
    region = regiones == regiones[i, j]
    if region[0, :].any() or region[-1, :].any() or region[:, 0].any() or region[:, -1].any():
        return False
    return not bool((z[region] > v + 1e-9).any())


def _altura(terreno: Campo, lat: float, lon: float) -> float:
    i = int(np.abs(terreno.lat - lat).argmin())
    j = int(np.abs(terreno.lon - lon).argmin())
    return float(terreno.valores[i, j])


def detectar_centros(suave: Campo, terreno: Campo, bbox: Bbox) -> list[Centro]:
    """H and L centers of the smoothed pressure field (hPa) on the working grid, `terreno` in meters.

    Highs come first from strongest to weakest, then lows from deepest to shallowest; at most
    `MAX_CENTROS` (the ones furthest from the normal 1013 hPa).
    """
    encontrados: list[Centro] = []
    for tipo, signo in (("H", 1.0), ("L", -1.0)):
        z = signo * suave.valores
        # 8-connected, so two equal cells that only touch at a corner are one candidate, not two
        es_extremo = z == maximum_filter(z, size=VENTANA_CELDAS, mode="nearest")
        candidatas, cantidad = label(es_extremo, structure=np.ones((3, 3), dtype=int))
        for k in range(1, cantidad + 1):
            i, j = (int(n) for n in np.argwhere(candidatas == k)[0])
            lat, lon = float(suave.lat[i]), float(suave.lon[j])
            if not (
                bbox.lat_min + MARGEN_BORDE_GRADOS <= lat <= bbox.lat_max - MARGEN_BORDE_GRADOS
                and bbox.lon_min + MARGEN_BORDE_GRADOS <= lon <= bbox.lon_max - MARGEN_BORDE_GRADOS
            ):
                continue
            if not _destaca(z, i, j) or _altura(terreno, lat, lon) > ALTURA_MAXIMA_M:
                continue
            encontrados.append(Centro(tipo, int(round(signo * z[i, j])), lat, lon))
    encontrados.sort(key=lambda c: -abs(c.p - PRESION_NORMAL_HPA))
    del encontrados[MAX_CENTROS:]
    altos = sorted((c for c in encontrados if c.t == "H"), key=lambda c: (-c.p, c.lat, c.lon))
    bajos = sorted((c for c in encontrados if c.t == "L"), key=lambda c: (c.p, c.lat, c.lon))
    return altos + bajos
