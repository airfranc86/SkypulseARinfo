"""Building one hour file and the manifest from a pressure field, and writing them to disk."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from isobaras_core.ciclo import HORAS, Ciclo
from isobaras_core.formato import codificar_hora, codificar_manifest, leer_hora, leer_manifest
from isobaras_core.grib import Campo
from isobaras_core.hora import BBOX, construir_hora, construir_manifest, escribir

CICLO = Ciclo(datetime(2026, 10, 15, 12, tzinfo=timezone.utc))


def _campo_pa(centro=(-37.0, -60.0), amplitud=2000.0, s=4.0) -> Campo:
    """A global-ish field in Pa (like the decoded GRIB): a Gaussian high over 1013 hPa."""
    lat = np.arange(-90.0, 90.0 + 0.125, 0.25)
    lon = np.arange(-180.0, 180.0, 0.25)
    la, lo = np.meshgrid(lat, lon, indexing="ij")
    r2 = (la - centro[0]) ** 2 + (lo - centro[1]) ** 2
    return Campo(lat, lon, 101300.0 + amplitud * np.exp(-r2 / (2 * s * s)))


def _manifest(ciclo=CICLO, horas=(0, 3, 6, 9)):
    generado = datetime(2026, 10, 15, 16, 52, tzinfo=timezone.utc)
    return construir_manifest(ciclo, generado, horas)


def test_la_hora_trae_el_ciclo_la_hora_y_el_momento_valido():
    hora = construir_hora(_campo_pa(), ciclo=CICLO, f=6)
    assert hora.cycle == "2026-10-15T12:00Z"
    assert hora.f == 6
    assert hora.valid == "2026-10-15T18:00Z"


def test_un_alto_gaussiano_da_cinco_anillos_cerrados_dentro_del_recorte():
    hora = construir_hora(_campo_pa(), ciclo=CICLO, f=0)
    assert sorted(ln.p for ln in hora.lineas) == [1016, 1020, 1024, 1028, 1032]
    for ln in hora.lineas:
        assert ln.cerrada
        assert ln.puntos[0] != ln.puntos[-1]
        for lat, lon in ln.puntos:
            assert BBOX.lat_min <= lat <= BBOX.lat_max and BBOX.lon_min <= lon <= BBOX.lon_max


def test_las_curvas_se_simplifican_pero_siguen_pasando_por_el_validador():
    hora = construir_hora(_campo_pa(), ciclo=CICLO, f=0)
    manifest = leer_manifest(json.loads(json.dumps(codificar_manifest(_manifest()))))
    leida = leer_hora(json.loads(json.dumps(codificar_hora(hora, 100))), manifest)
    assert [ln.p for ln in leida.lineas] == [ln.p for ln in hora.lineas]
    # a ring of ~10 degrees with a 0.03 tolerance needs far fewer than the ~400 grid points it crosses
    assert all(len(ln.puntos) < 150 for ln in leida.lineas)


def test_el_manifest_lista_las_horas_en_orden_con_su_archivo():
    m = _manifest()
    assert m.cycle == "2026-10-15T12:00Z"
    assert m.generated == "2026-10-15T16:52Z"
    assert m.interval_hpa == 4 and m.scale == 100
    assert m.bbox == BBOX
    assert [(h.f, h.valid, h.file) for h in m.hours] == [
        (0, "2026-10-15T12:00Z", "isobaras_f000.json"),
        (3, "2026-10-15T15:00Z", "isobaras_f003.json"),
        (6, "2026-10-15T18:00Z", "isobaras_f006.json"),
        (9, "2026-10-15T21:00Z", "isobaras_f009.json"),
    ]


def test_el_manifest_completo_tiene_41_horas():
    assert len(_manifest(horas=HORAS).hours) == 41


def test_escribir_deja_los_archivos_que_el_validador_acepta(tmp_path):
    campo = _campo_pa()
    manifest = _manifest(horas=(0, 3))
    horas = {f: construir_hora(campo, ciclo=CICLO, f=f) for f in (0, 3)}
    escribir(tmp_path, manifest, horas)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["isobaras_f000.json", "isobaras_f003.json", "manifest.json"]
    m = leer_manifest(json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8")))
    for h in m.hours:
        leer_hora(json.loads((tmp_path / h.file).read_text(encoding="utf-8")), m)


def test_escribir_no_deja_el_manifest_si_falta_una_hora(tmp_path):
    manifest = _manifest(horas=(0, 3))
    horas = {0: construir_hora(_campo_pa(), ciclo=CICLO, f=0)}
    with pytest.raises(ValueError):
        escribir(tmp_path, manifest, horas)
    assert not (tmp_path / "manifest.json").exists()


def test_los_archivos_se_escriben_compactos(tmp_path):
    manifest = _manifest(horas=(0,))
    escribir(tmp_path, manifest, {0: construir_hora(_campo_pa(), ciclo=CICLO, f=0)})
    texto = (tmp_path / "isobaras_f000.json").read_text(encoding="utf-8")
    assert "\n" not in texto and ", " not in texto


# ── Fixture compartido con TypeScript ────────────────────────────────────────

POZO = Path(__file__).resolve().parents[3] / "apps" / "frontend" / "tests" / "fixtures" / "isobaras" / "f000.pozo.json"


def _resumen(hora_cruda: dict) -> list[tuple[int, bool, int]]:
    return [(ln["p"], ln["closed"], len(ln["labels"])) for ln in hora_cruda["lines"]]


def test_el_fixture_del_pozo_lo_acepta_el_validador_y_coincide_con_lo_que_se_genera():
    """`f000.pozo.json` is what this pipeline writes for the synthetic high; the TypeScript tests read it too."""
    fixture = json.loads(POZO.read_text(encoding="utf-8"))
    manifest = leer_manifest(json.loads((POZO.parent / "manifest.json").read_text(encoding="utf-8")))
    hora = leer_hora(fixture, manifest)
    assert [ln.p for ln in hora.lineas] == [1016, 1020, 1024, 1028, 1032]
    ciclo = Ciclo(datetime(2026, 10, 14, 0, tzinfo=timezone.utc))
    generada = codificar_hora(construir_hora(_campo_pa(s=4.0), ciclo=ciclo, f=0), 100)
    assert _resumen(generada) == _resumen(fixture)


def test_la_hora_de_generacion_se_pasa_a_utc():
    menos_tres = timezone(timedelta(hours=-3))
    m = construir_manifest(CICLO, datetime(2026, 10, 15, 13, 52, tzinfo=menos_tres), (0,))
    assert m.generated == "2026-10-15T16:52Z"


def test_una_hora_de_generacion_sin_zona_se_rechaza():
    with pytest.raises(ValueError):
        construir_manifest(CICLO, datetime(2026, 10, 15, 16, 52), (0,))
