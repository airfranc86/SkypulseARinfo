"""Downloading one forecast hour and the command-line entry point, with the network replaced by fakes."""

from __future__ import annotations

import io
from datetime import datetime, timezone

import numpy as np
import pytest

from isobaras_core.ciclo import Ciclo
from isobaras_core.descarga import bajar_campo, main
from isobaras_core.idx import VariableAusente

AHORA = datetime(2026, 10, 15, 17, 0, tzinfo=timezone.utc)
CICLO = Ciclo(datetime(2026, 10, 15, 12, tzinfo=timezone.utc))


class RedFalsa:
    """Serves one tiny GRIB through the same two calls the real network layer exposes."""

    def __init__(self, grib: bytes, *, con_prmsl: bool = True, idx_que_faltan: tuple[str, ...] = ()):
        self.grib = grib
        self.con_prmsl = con_prmsl
        self.idx_que_faltan = idx_que_faltan
        self.pedidos: list[tuple[str, tuple[int, int | None] | None]] = []

    def idx_texto(self) -> str:
        primera = "PRMSL:mean sea level" if self.con_prmsl else "CLMR:1 hybrid level"
        return (
            f"1:0:d=2026101512:{primera}:anl:\n"
            f"2:{len(self.grib)}:d=2026101512:CLMR:1 hybrid level:anl:\n"
            f"3:{len(self.grib) + 50}:d=2026101512:ICMR:1 hybrid level:anl:\n"
        )

    def existe(self, url: str) -> bool:
        return not any(url.endswith(f"{h}.idx") for h in self.idx_que_faltan)

    def fetch(self, url: str, rango: tuple[int, int | None] | None = None) -> bytes:
        self.pedidos.append((url, rango))
        if url.endswith(".idx"):
            return self.idx_texto().encode()
        assert rango is not None, "un GRIB nunca se baja entero"
        inicio, fin = rango
        return self.grib[inicio : (fin + 1) if fin is not None else None]


def test_bajar_campo_pide_solo_el_rango_de_prmsl(grib_norte_sur):
    red = RedFalsa(grib_norte_sur)
    campo = bajar_campo(CICLO, 24, fetch=red.fetch)
    assert red.pedidos[0][0].endswith("gfs.t12z.pgrb2.0p25.f024.idx")
    assert red.pedidos[1] == (red.pedidos[1][0], (0, len(grib_norte_sur) - 1))
    assert red.pedidos[1][0].endswith("gfs.t12z.pgrb2.0p25.f024")
    assert campo.valores.shape == (5, 8)
    assert list(campo.lat) == [-90, -45, 0, 45, 90]


def test_bajar_campo_sin_prmsl_en_el_idx_lo_dice(grib_norte_sur):
    red = RedFalsa(grib_norte_sur, con_prmsl=False)
    with pytest.raises(VariableAusente):
        bajar_campo(CICLO, 0, fetch=red.fetch)
    assert len(red.pedidos) == 1  # only the index was requested, no GRIB


def _correr(red: RedFalsa, *args: str) -> tuple[int, str, str]:
    salida, errores = io.StringIO(), io.StringIO()
    codigo = main(list(args), ahora=AHORA, existe=red.existe, fetch=red.fetch, out=salida, err=errores)
    return codigo, salida.getvalue(), errores.getvalue()


def test_main_con_el_ciclo_completo_sale_en_0_y_cuenta_la_grilla(grib_norte_sur):
    codigo, salida, errores = _correr(RedFalsa(grib_norte_sur), "--f", "0")
    assert codigo == 0
    assert errores == ""
    assert "2026-10-15T12:00Z" in salida
    assert "f000" in salida
    assert "5x8" in salida


def test_main_si_falta_un_idx_no_publica_y_no_baja_ningun_grib(grib_norte_sur):
    red = RedFalsa(grib_norte_sur, idx_que_faltan=("f120", "f117", "f114"))
    codigo, salida, errores = _correr(red, "--f", "0")
    assert codigo == 2
    assert "no se publica" in errores
    assert "f120" in errores
    assert red.pedidos == []


def test_main_si_falta_prmsl_sale_en_3_con_un_mensaje_claro(grib_norte_sur):
    codigo, _, errores = _correr(RedFalsa(grib_norte_sur, con_prmsl=False), "--f", "0")
    assert codigo == 3
    assert "PRMSL" in errores and "f000" in errores


def test_main_rechaza_una_hora_que_no_esta_en_el_horizonte(grib_norte_sur):
    with pytest.raises(SystemExit):
        _correr(RedFalsa(grib_norte_sur), "--f", "7")


def test_main_un_error_de_red_sale_en_4_con_mensaje_propio(grib_norte_sur):
    red = RedFalsa(grib_norte_sur)

    def existe_roto(url: str) -> bool:
        raise OSError("sin conexión")

    salida, errores = io.StringIO(), io.StringIO()
    codigo = main(["--f", "0"], ahora=AHORA, existe=existe_roto, fetch=red.fetch, out=salida, err=errores)
    assert codigo == 4
    assert "sin conexión" in errores.getvalue()


def test_main_un_grib_roto_sale_en_4_con_mensaje_propio(grib_norte_sur):
    red = RedFalsa(b"esto no es un GRIB")
    codigo, _, errores = _correr(red, "--f", "0")
    assert codigo == 4
    assert "GRIB" in errores
