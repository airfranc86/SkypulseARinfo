"""The whole run: choose the cycle, skip it if it is already published, build 41 hours and write them."""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone

import numpy as np
import pytest

from isobaras_core.ciclo import HORAS, Ciclo
from isobaras_core.formato import leer_hora, leer_manifest
from isobaras_core.grib import Campo
from isobaras_core.pipeline import main

AHORA = datetime(2026, 10, 15, 17, 0, tzinfo=timezone.utc)
CICLO_TEXTO = "2026-10-15T12:00Z"


def _presion(f: int) -> Campo:
    """A moving Gaussian high over 1013 hPa, in Pa on a global 0.25 degree grid."""
    lat = np.arange(-90.0, 90.0 + 0.125, 0.25)
    lon = np.arange(-180.0, 180.0, 0.25)
    la, lo = np.meshgrid(lat, lon, indexing="ij")
    centro_lon = -75.0 + f * 0.1
    return Campo(lat, lon, 101300.0 + 2000.0 * np.exp(-((la + 37.0) ** 2 + (lo - centro_lon) ** 2) / 32.0))


def _terreno() -> Campo:
    lat = np.arange(-90.0, 90.0 + 0.125, 0.25)
    lon = np.arange(-180.0, 180.0, 0.25)
    return Campo(lat, lon, np.zeros((lat.size, lon.size)))


class Entorno:
    def __init__(self, *, publicado: str | None = None, idx_que_faltan: tuple[str, ...] = ()):
        self.publicado = publicado
        self.idx_que_faltan = idx_que_faltan
        self.campos_pedidos: list[tuple[int, str]] = []
        self.urls: list[str] = []

    def existe(self, url: str) -> bool:
        return not any(url.endswith(f"{h}.idx") for h in self.idx_que_faltan)

    def bajar(self, ciclo: Ciclo, f: int, *, variable: str = "PRMSL", nivel: str = "mean sea level") -> Campo:
        self.campos_pedidos.append((f, variable))
        return _terreno() if variable == "HGT" else _presion(f)

    def fetch(self, url: str, rango=None) -> bytes:
        self.urls.append(url)
        if not url.endswith("manifest.json") or self.publicado is None:
            raise OSError("404")
        return json.dumps({**_manifest_minimo(), "cycle": self.publicado}).encode()


def _manifest_minimo() -> dict:
    return {
        "v": 1,
        "source": "x",
        "cycle": CICLO_TEXTO,
        "generated": "2026-10-15T16:00Z",
        "bbox": [-90, -62, -30, -12],
        "interval_hpa": 4,
        "scale": 100,
        "hours": [{"f": 0, "valid": "2026-10-15T12:00Z", "file": "isobaras_f000.json"}],
    }


def _correr(entorno: Entorno, *args: str):
    salida, errores = io.StringIO(), io.StringIO()
    codigo = main(
        list(args),
        ahora=AHORA,
        existe=entorno.existe,
        fetch=entorno.fetch,
        bajar=entorno.bajar,
        out=salida,
        err=errores,
    )
    return codigo, salida.getvalue(), errores.getvalue()


def test_una_corrida_completa_escribe_el_manifest_y_las_41_horas(tmp_path):
    entorno = Entorno()
    codigo, salida, errores = _correr(entorno, "--salida", str(tmp_path / "out"), "--publicado-url", "http://pages.test")
    assert codigo == 0, errores
    archivos = sorted(p.name for p in (tmp_path / "out").iterdir())
    assert len(archivos) == 42 and "manifest.json" in archivos
    manifest = leer_manifest(json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8")))
    assert manifest.cycle == CICLO_TEXTO
    assert [h.f for h in manifest.hours] == list(HORAS)
    for h in manifest.hours:
        hora = leer_hora(json.loads((tmp_path / "out" / h.file).read_text(encoding="utf-8")), manifest)
        assert len(hora.lineas) > 0 and len(hora.centros) >= 1
    assert "publicar" in salida


def test_el_terreno_se_baja_una_sola_vez_por_ciclo(tmp_path):
    entorno = Entorno()
    _correr(entorno, "--salida", str(tmp_path / "out"), "--publicado-url", "http://pages.test")
    assert [v for _, v in entorno.campos_pedidos].count("HGT") == 1
    assert [f for f, v in entorno.campos_pedidos if v == "PRMSL"] == list(HORAS)


def test_si_el_ciclo_ya_esta_publicado_sale_sin_bajar_nada_y_sin_escribir(tmp_path):
    entorno = Entorno(publicado=CICLO_TEXTO)
    github = tmp_path / "github_output"
    codigo, salida, _ = _correr(
        entorno, "--salida", str(tmp_path / "out"), "--publicado-url", "http://pages.test", "--github-output", str(github)
    )
    assert codigo == 0
    assert "ciclo ya publicado" in salida
    assert entorno.campos_pedidos == []
    assert not (tmp_path / "out").exists()
    assert "publicar=false" in github.read_text(encoding="utf-8")


def test_si_lo_publicado_es_de_un_ciclo_viejo_se_publica_el_nuevo(tmp_path):
    entorno = Entorno(publicado="2026-10-15T06:00Z")
    github = tmp_path / "github_output"
    codigo, _, _ = _correr(
        entorno, "--salida", str(tmp_path / "out"), "--publicado-url", "http://pages.test", "--github-output", str(github)
    )
    assert codigo == 0
    texto = github.read_text(encoding="utf-8")
    assert "publicar=true" in texto and f"ciclo={CICLO_TEXTO}" in texto


def test_si_falta_un_idx_no_publica_y_sale_en_2_sin_bajar_campos(tmp_path):
    entorno = Entorno(idx_que_faltan=("f120",))
    # the fake never has the f120 index, so no recent cycle is complete
    codigo, _, errores = _correr(entorno, "--salida", str(tmp_path / "out"), "--publicado-url", "http://pages.test")
    assert codigo == 2
    assert "no se publica" in errores
    assert entorno.campos_pedidos == []
    assert not (tmp_path / "out").exists()


def test_dry_run_hace_todo_menos_escribir(tmp_path):
    entorno = Entorno()
    github = tmp_path / "github_output"
    codigo, salida, _ = _correr(
        entorno,
        "--dry-run",
        "--salida",
        str(tmp_path / "out"),
        "--publicado-url",
        "http://pages.test",
        "--github-output",
        str(github),
    )
    assert codigo == 0
    assert not (tmp_path / "out").exists()
    assert len([f for f, v in entorno.campos_pedidos if v == "PRMSL"]) == 41
    assert "dry-run" in salida
    assert "publicar=false" in github.read_text(encoding="utf-8")


def test_una_salida_con_archivos_viejos_se_limpia_antes_de_escribir(tmp_path):
    salida = tmp_path / "out"
    salida.mkdir()
    (salida / "isobaras_f999.json").write_text("viejo", encoding="utf-8")
    codigo, _, errores = _correr(Entorno(), "--salida", str(salida), "--publicado-url", "http://pages.test")
    assert codigo == 0, errores
    assert not (salida / "isobaras_f999.json").exists()


def test_un_error_de_red_al_bajar_un_campo_sale_en_4_y_no_deja_un_manifest_a_medias(tmp_path):
    class Roto(Entorno):
        def bajar(self, ciclo, f, *, variable="PRMSL", nivel="mean sea level"):
            if variable == "PRMSL" and f == 60:
                raise OSError("sin conexión")
            return super().bajar(ciclo, f, variable=variable, nivel=nivel)

    codigo, _, errores = _correr(Roto(), "--salida", str(tmp_path / "out"), "--publicado-url", "http://pages.test")
    assert codigo == 4
    assert "f060" in errores
    assert not (tmp_path / "out" / "manifest.json").exists()


def test_el_manifest_publicado_ilegible_no_impide_publicar(tmp_path):
    class Basura(Entorno):
        def fetch(self, url, rango=None):
            return b"no es json"

    codigo, _, errores = _correr(Basura(), "--salida", str(tmp_path / "out"), "--publicado-url", "http://pages.test")
    assert codigo == 0, errores
    assert (tmp_path / "out" / "manifest.json").exists()


def test_el_ciclo_elegido_es_el_mas_reciente_completo():
    entorno = Entorno()
    salida = io.StringIO()
    main(["--dry-run", "--publicado-url", "http://pages.test"], ahora=AHORA, existe=entorno.existe, fetch=entorno.fetch, bajar=entorno.bajar, out=salida, err=io.StringIO())
    assert CICLO_TEXTO in salida.getvalue()


def test_si_lo_publicado_es_de_un_ciclo_mas_nuevo_no_se_pisa_con_uno_viejo(tmp_path):
    """A transient miss on the newest index would pick an older cycle: never deploy it over a newer one."""
    entorno = Entorno(publicado="2026-10-15T18:00Z")
    github = tmp_path / "github_output"
    codigo, salida, _ = _correr(
        entorno, "--salida", str(tmp_path / "out"), "--publicado-url", "http://pages.test", "--github-output", str(github)
    )
    assert codigo == 0
    assert "ciclo ya publicado" in salida
    assert entorno.campos_pedidos == []
    assert "publicar=false" in github.read_text(encoding="utf-8")


def test_una_salida_con_archivos_ajenos_se_rechaza_y_no_se_borra_nada(tmp_path):
    salida = tmp_path / "out"
    salida.mkdir()
    ajeno = salida / "manifest.webmanifest"
    ajeno.write_text("no tocar", encoding="utf-8")
    (salida / "manifest.json").write_text("viejo", encoding="utf-8")
    codigo, _, errores = _correr(Entorno(), "--salida", str(salida), "--publicado-url", "http://pages.test")
    assert codigo == 4
    assert "manifest.webmanifest" in errores
    assert ajeno.read_text(encoding="utf-8") == "no tocar"
    assert (salida / "manifest.json").read_text(encoding="utf-8") == "viejo"
