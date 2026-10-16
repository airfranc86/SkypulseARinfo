"""Reading the `.idx` index that sits next to each GFS file: where does PRMSL start and end?"""

from __future__ import annotations

from pathlib import Path

import pytest

from isobaras_core.idx import EntradaIdx, IdxInvalido, VariableAusente, parsear_idx, rango_de

FIXTURES = Path(__file__).parent / "fixtures"


def _entradas(nombre: str):
    return parsear_idx((FIXTURES / nombre).read_text(encoding="utf-8"))


def test_parsea_las_lineas_reales_de_f000_y_f024():
    f000 = _entradas("gfs_f000.idx")
    f024 = _entradas("gfs_f024.idx")
    assert len(f000) == len(f024) == 8
    assert f000[0] == EntradaIdx(1, 0, "2026101512", "PRMSL", "mean sea level", "anl")
    assert f024[0] == EntradaIdx(1, 0, "2026101512", "PRMSL", "mean sea level", "24 hour fcst")


def test_prmsl_se_encuentra_con_el_sufijo_anl_y_con_el_de_pronostico():
    assert rango_de(_entradas("gfs_f000.idx"), "PRMSL", "mean sea level") == (0, 997172)
    assert rango_de(_entradas("gfs_f024.idx"), "PRMSL", "mean sea level") == (0, 995595)


def test_hgt_surface_termina_donde_empieza_la_linea_siguiente():
    assert rango_de(_entradas("gfs_f000.idx"), "HGT", "surface") == (414877663, 415370105)
    assert rango_de(_entradas("gfs_f024.idx"), "HGT", "surface") == (415767344, 416259786)


def test_la_ultima_entrada_no_tiene_fin_conocido():
    entradas = _entradas("gfs_f000.idx")
    assert rango_de(entradas, "TSOIL", "0-0.1 m below ground") == (415948259, None)


def test_una_variable_ausente_dice_cual_falta():
    with pytest.raises(VariableAusente) as e:
        rango_de(_entradas("gfs_f000.idx"), "PRMSL", "surface")
    assert "PRMSL" in str(e.value) and "surface" in str(e.value)


def test_un_idx_sin_prmsl_no_se_confunde_con_otra_variable():
    entradas = parsear_idx("1:0:d=2026101512:CLMR:1 hybrid level:anl:\n2:500:d=2026101512:ICMR:1 hybrid level:anl:\n")
    with pytest.raises(VariableAusente):
        rango_de(entradas, "PRMSL", "mean sea level")


def test_lineas_vacias_se_ignoran():
    assert len(parsear_idx("1:0:d=2026101512:PRMSL:mean sea level:anl:\n\n")) == 1


@pytest.mark.parametrize(
    "malo",
    [
        "esto no es una linea del idx\n",
        "x:0:d=2026101512:PRMSL:mean sea level:anl:\n",
        "1:abc:d=2026101512:PRMSL:mean sea level:anl:\n",
        "1:0:d=2026101512:PRMSL\n",
    ],
)
def test_lineas_malformadas_se_rechazan(malo):
    with pytest.raises(IdxInvalido):
        parsear_idx(malo)


def test_offsets_que_no_crecen_se_rechazan():
    with pytest.raises(IdxInvalido):
        parsear_idx("1:100:d=2026101512:PRMSL:mean sea level:anl:\n2:50:d=2026101512:CLMR:1 hybrid level:anl:\n")
