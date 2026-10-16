"""Which GFS cycle to use: the most recent one whose `.idx` index exists for EVERY hour we need."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from isobaras_core.ciclo import HORAS, Ciclo, CicloIncompleto, ciclos_candidatos, elegir_ciclo, url_grib, url_idx

CICLO = Ciclo(datetime(2026, 10, 15, 12, tzinfo=timezone.utc))
BUCKET = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"


def test_las_horas_son_de_0_a_120_cada_3():
    assert HORAS == tuple(range(0, 121, 3))
    assert len(HORAS) == 41


def test_el_ciclo_se_escribe_como_en_el_manifest():
    assert CICLO.texto() == "2026-10-15T12:00Z"


def test_urls_del_grib_y_del_idx():
    esperado = f"{BUCKET}/gfs.20261015/12/atmos/gfs.t12z.pgrb2.0p25.f024"
    assert url_grib(CICLO, 24) == esperado
    assert url_idx(CICLO, 24) == esperado + ".idx"
    assert url_idx(CICLO, 3).endswith("gfs.t12z.pgrb2.0p25.f003.idx")


def test_candidatos_del_mas_reciente_al_mas_viejo():
    ahora = datetime(2026, 10, 15, 17, 30, tzinfo=timezone.utc)
    textos = [c.texto() for c in ciclos_candidatos(ahora)]
    assert textos == ["2026-10-15T12:00Z", "2026-10-15T06:00Z", "2026-10-15T00:00Z", "2026-10-14T18:00Z"]


def test_un_ahora_justo_en_la_hora_del_ciclo_lo_incluye():
    ahora = datetime(2026, 10, 15, 18, 0, tzinfo=timezone.utc)
    assert ciclos_candidatos(ahora)[0].texto() == "2026-10-15T18:00Z"


def test_un_ahora_sin_zona_horaria_se_rechaza():
    with pytest.raises(ValueError):
        ciclos_candidatos(datetime(2026, 10, 15, 17, 0))


def test_elige_el_mas_reciente_si_tiene_los_idx_de_las_41_horas():
    pedidos: list[str] = []

    def existe(url: str) -> bool:
        pedidos.append(url)
        return True

    ahora = datetime(2026, 10, 15, 17, 0, tzinfo=timezone.utc)
    assert elegir_ciclo(ahora, existe).texto() == "2026-10-15T12:00Z"
    assert len(pedidos) == 41
    assert all(".t12z." in p and p.endswith(".idx") for p in pedidos)


def test_si_al_mas_reciente_le_falta_una_hora_usa_el_anterior():
    ahora = datetime(2026, 10, 15, 17, 0, tzinfo=timezone.utc)

    def existe(url: str) -> bool:
        return not (".t12z." in url and url.endswith("f120.idx"))

    assert elegir_ciclo(ahora, existe).texto() == "2026-10-15T06:00Z"


def test_un_idx_que_falta_en_el_medio_tambien_descarta_el_ciclo():
    ahora = datetime(2026, 10, 15, 17, 0, tzinfo=timezone.utc)

    def existe(url: str) -> bool:
        return not (".t12z." in url and url.endswith("f063.idx"))

    assert elegir_ciclo(ahora, existe).texto() == "2026-10-15T06:00Z"


def test_si_ningun_ciclo_esta_completo_no_se_publica_y_el_mensaje_dice_por_que():
    ahora = datetime(2026, 10, 15, 17, 0, tzinfo=timezone.utc)
    with pytest.raises(CicloIncompleto) as e:
        elegir_ciclo(ahora, lambda url: False)
    mensaje = str(e.value)
    assert "no se publica" in mensaje
    assert "2026-10-15T12:00Z" in mensaje and "f" in mensaje
