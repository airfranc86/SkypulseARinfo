"""Which GFS cycle to use and where its files are.

NOAA publishes a cycle every 6 hours (00, 06, 12, 18 UTC) and the `.idx` files of its hours arrive out
of order, so a cycle is only usable once the index of EVERY hour we need exists.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

BUCKET = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
CICLOS_POR_DIA_HORAS = 6

# 0..120 h every 3 h: 41 hours (decision B2).
HORAS: tuple[int, ...] = tuple(range(0, 121, 3))


class CicloIncompleto(RuntimeError):
    """No recent cycle has the index of every hour: nothing is published this run."""


@dataclass(frozen=True)
class Ciclo:
    fecha: datetime  # UTC, hour 0 / 6 / 12 / 18

    def texto(self) -> str:
        """The cycle as the contract writes it, `2026-10-15T12:00Z`."""
        return self.fecha.strftime("%Y-%m-%dT%H:%MZ")


def _carpeta(ciclo: Ciclo) -> str:
    return f"{BUCKET}/gfs.{ciclo.fecha:%Y%m%d}/{ciclo.fecha:%H}/atmos/gfs.t{ciclo.fecha:%H}z.pgrb2.0p25"


def url_grib(ciclo: Ciclo, f: int) -> str:
    return f"{_carpeta(ciclo)}.f{f:03d}"


def url_idx(ciclo: Ciclo, f: int) -> str:
    return url_grib(ciclo, f) + ".idx"


def ciclos_candidatos(ahora: datetime, cantidad: int = 4) -> list[Ciclo]:
    """The most recent cycles at or before `ahora` (timezone-aware), newest first."""
    if ahora.tzinfo is None:
        raise ValueError("`ahora` tiene que tener zona horaria")
    utc = ahora.astimezone(timezone.utc)
    ultimo = utc.replace(minute=0, second=0, microsecond=0, hour=utc.hour - utc.hour % CICLOS_POR_DIA_HORAS)
    return [Ciclo(ultimo - timedelta(hours=CICLOS_POR_DIA_HORAS * i)) for i in range(cantidad)]


def elegir_ciclo(
    ahora: datetime,
    existe: Callable[[str], bool],
    horas: tuple[int, ...] = HORAS,
    cantidad: int = 4,
) -> Ciclo:
    """Newest cycle whose `.idx` exists for every hour in `horas`.

    Hours are probed from the last one backwards: the last hour is the last to be published, so an
    unfinished cycle is discarded after a single request.
    """
    motivos: list[str] = []
    for ciclo in ciclos_candidatos(ahora, cantidad):
        faltante = next((f for f in reversed(horas) if not existe(url_idx(ciclo, f))), None)
        if faltante is None:
            return ciclo
        motivos.append(f"{ciclo.texto()} (falta f{faltante:03d})")
    raise CicloIncompleto("no se publica: ningún ciclo reciente está completo: " + "; ".join(motivos))
