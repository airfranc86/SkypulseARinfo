"""Download one forecast hour of mean sea level pressure and the command-line entry point.

    uv run python -m isobaras_core.descarga --f 0

Exit codes: 0 = field read, 2 = no complete cycle (nothing is published), 3 = the index has no PRMSL,
4 = a network or data error (unreadable index or GRIB, request failed).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import TextIO

from . import red
from .ciclo import HORAS, Ciclo, CicloIncompleto, elegir_ciclo, url_grib, url_idx
from .grib import Campo, GribInvalido, decodificar
from .idx import IdxInvalido, VariableAusente, parsear_idx, rango_de

VARIABLE = "PRMSL"
NIVEL = "mean sea level"

Fetch = Callable[[str, tuple[int, int | None] | None], bytes]


def bajar_campo(ciclo: Ciclo, f: int, *, fetch: Fetch) -> Campo:
    """Pressure field (Pa) of hour `f`: read the index, request only PRMSL's bytes, decode them."""
    entradas = parsear_idx(fetch(url_idx(ciclo, f), None).decode("utf-8"))
    rango = rango_de(entradas, VARIABLE, NIVEL)
    return decodificar(fetch(url_grib(ciclo, f), rango))


def main(
    argv: Sequence[str] | None = None,
    *,
    ahora: datetime | None = None,
    existe: Callable[[str], bool] = red.existe,
    fetch: Fetch = red.fetch,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    salida = out or sys.stdout
    errores = err or sys.stderr
    parser = argparse.ArgumentParser(prog="isobaras_core.descarga", description=__doc__.splitlines()[0])
    parser.add_argument("--f", type=int, default=0, choices=HORAS, help="forecast hour (0..120, every 3)")
    args = parser.parse_args(argv)

    try:
        ciclo = elegir_ciclo(ahora or datetime.now(timezone.utc), existe)
    except CicloIncompleto as e:
        print(str(e), file=errores)
        return 2
    except OSError as e:
        print(f"error de red al buscar el ciclo: {e}", file=errores)
        return 4
    try:
        campo = bajar_campo(ciclo, args.f, fetch=fetch)
    except VariableAusente as e:
        print(f"ciclo {ciclo.texto()} f{args.f:03d}: {e}", file=errores)
        return 3
    except (OSError, GribInvalido, IdxInvalido) as e:
        print(f"ciclo {ciclo.texto()} f{args.f:03d}: no se pudo leer el GRIB o su índice: {e}", file=errores)
        return 4
    hpa = campo.valores / 100.0
    print(
        f"ciclo {ciclo.texto()} f{args.f:03d}: grilla {campo.lat.size}x{campo.lon.size}, "
        f"lat {campo.lat[0]:g}..{campo.lat[-1]:g}, lon {campo.lon[0]:g}..{campo.lon[-1]:g}, "
        f"presión {hpa.min():.1f}..{hpa.max():.1f} hPa",
        file=salida,
    )
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
