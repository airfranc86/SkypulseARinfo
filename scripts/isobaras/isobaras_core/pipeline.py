"""The whole run, as the scheduled workflow executes it.

    uv run python -m isobaras_core.pipeline --salida out

Steps: choose the newest cycle whose index exists for all 41 hours, stop if that cycle is the one already
published, download the terrain once and the 41 pressure fields, build every hour file and the manifest,
write them to `--salida`. With `--dry-run` everything runs except the writing.

Exit codes: 0 = done (see `publicar` in the GitHub output), 2 = no complete cycle (nothing is published),
3 = the index has no PRMSL, 4 = a network or data error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

from . import red
from .ciclo import HORAS, Ciclo, CicloIncompleto, elegir_ciclo
from .descarga import NIVEL_TERRENO, VARIABLE_TERRENO, bajar_campo
from .formato import FormatoInvalido, Hora, leer_manifest
from .grib import Campo, GribInvalido
from .hora import construir_hora, construir_manifest, escribir
from .idx import IdxInvalido, VariableAusente

PAGES_BASE = "https://airfranc86.github.io/SkypulseARinfo"
SALIDA_POR_DEFECTO = Path(__file__).resolve().parents[1] / "out"
_ARCHIVO_GENERADO = re.compile(r"isobaras_f[0-9]{3}\.json|manifest\.json")

Bajar = Callable[..., Campo]


def _ciclo_publicado(url_base: str, fetch: Callable[..., bytes]) -> str | None:
    """The cycle of the manifest currently served, or None when there is none or it cannot be read."""
    try:
        return leer_manifest(json.loads(fetch(f"{url_base.rstrip('/')}/manifest.json", None))).cycle
    except (OSError, ValueError, FormatoInvalido):
        return None


def _salida_de_github(ruta: str | None, **valores: str) -> None:
    if not ruta:
        return
    with open(ruta, "a", encoding="utf-8") as f:
        for clave, valor in valores.items():
            f.write(f"{clave}={valor}\n")


def _limpiar(salida: Path) -> None:
    """Empty the output directory of what this pipeline wrote, so an old cycle never lingers next to a new one.

    Refuses (`OSError`) when the directory holds anything else: a wrong `--salida` must never delete files that
    are not ours.
    """
    if not salida.is_dir():
        return
    ajenos = sorted(a.name for a in salida.iterdir() if not (a.is_file() and _ARCHIVO_GENERADO.fullmatch(a.name)))
    if ajenos:
        raise OSError(f"el directorio de salida tiene archivos que no son del pipeline: {', '.join(ajenos)}")
    for archivo in salida.iterdir():
        archivo.unlink()


def main(
    argv: Sequence[str] | None = None,
    *,
    ahora: datetime | None = None,
    existe: Callable[[str], bool] = red.existe,
    fetch: Callable[..., bytes] = red.fetch,
    bajar: Bajar | None = None,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    salida_texto = out or sys.stdout
    errores = err or sys.stderr
    parser = argparse.ArgumentParser(prog="isobaras_core.pipeline", description=__doc__.splitlines()[0])
    parser.add_argument("--salida", type=Path, default=SALIDA_POR_DEFECTO, help="directory for the generated files")
    parser.add_argument("--publicado-url", default=PAGES_BASE, help="where the current manifest is served")
    parser.add_argument("--github-output", default=None, help="file to write `publicar=` and `ciclo=` to")
    parser.add_argument("--dry-run", action="store_true", help="run everything except writing the files")
    args = parser.parse_args(argv)

    momento = ahora or datetime.now(timezone.utc)
    bajar = bajar or (lambda ciclo, f, **k: bajar_campo(ciclo, f, fetch=fetch, **k))

    try:
        ciclo = elegir_ciclo(momento, existe)
    except CicloIncompleto as e:
        print(str(e), file=errores)
        _salida_de_github(args.github_output, publicar="false")
        return 2
    except OSError as e:
        print(f"error de red al buscar el ciclo: {e}", file=errores)
        return 4

    publicado = _ciclo_publicado(args.publicado_url, fetch)
    # ISO dates sort as text. `>=`, not `==`: a transient miss on the newest index would pick an older cycle,
    # and an older cycle must never replace a newer one that is already served.
    if publicado is not None and publicado >= ciclo.texto():
        print(f"ciclo ya publicado: {publicado} (el elegido era {ciclo.texto()})", file=salida_texto)
        _salida_de_github(args.github_output, publicar="false", ciclo=ciclo.texto())
        return 0

    horas: dict[int, Hora] = {}
    f_actual = 0
    try:
        terreno = bajar(ciclo, 0, variable=VARIABLE_TERRENO, nivel=NIVEL_TERRENO)
        for f_actual in HORAS:
            horas[f_actual] = construir_hora(bajar(ciclo, f_actual), ciclo=ciclo, f=f_actual, terreno=terreno)
    except VariableAusente as e:
        print(f"ciclo {ciclo.texto()} f{f_actual:03d}: {e}", file=errores)
        return 3
    except (OSError, GribInvalido, IdxInvalido, FormatoInvalido) as e:
        print(f"ciclo {ciclo.texto()} f{f_actual:03d}: no se pudo generar: {e}", file=errores)
        return 4

    manifest = construir_manifest(ciclo, momento, HORAS)
    curvas = sum(len(h.lineas) for h in horas.values())
    resumen = f"ciclo {ciclo.texto()}: {len(horas)} horas, {curvas} curvas"
    if args.dry_run:
        print(f"{resumen} (dry-run: no se escribió nada)", file=salida_texto)
        _salida_de_github(args.github_output, publicar="false", ciclo=ciclo.texto())
        return 0
    try:
        _limpiar(args.salida)
        escribir(args.salida, manifest, horas)
    except (OSError, FormatoInvalido, ValueError) as e:
        print(f"ciclo {ciclo.texto()}: no se pudo escribir: {e}", file=errores)
        return 4
    print(f"{resumen}, escritas en {args.salida}. publicar=true", file=salida_texto)
    _salida_de_github(args.github_output, publicar="true", ciclo=ciclo.texto())
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
