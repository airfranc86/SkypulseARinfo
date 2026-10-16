"""Structural checks of `.github/workflows/isobaras.yml`: the safety properties we decided, read as text.

The workflow cannot be run locally (it needs GitHub), so these tests pin what must never silently change:
pinned actions, minimal permissions, who may publish, which events trigger it, the cron times.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
TEXTO = (RAIZ / ".github" / "workflows" / "isobaras.yml").read_text(encoding="utf-8").replace("\r\n", "\n")


def _bloque(nombre_job: str) -> str:
    """The text of one job, from its key to the next job (or the end of the file)."""
    inicio = re.search(rf"^  {nombre_job}:\n", TEXTO, re.M)
    assert inicio, f"no hay un job {nombre_job}"
    siguiente = re.search(r"^  [a-z_-]+:\n", TEXTO[inicio.end() :], re.M)
    return TEXTO[inicio.end() : inicio.end() + siguiente.start()] if siguiente else TEXTO[inicio.end() :]


def _permisos(job: str) -> list[str]:
    m = re.search(r"^    permissions:\n((?:      .+\n)+)", _bloque(job), re.M)
    return [linea.strip() for linea in m.group(1).splitlines()] if m else []


def test_cada_accion_de_terceros_esta_fijada_por_sha_de_40_caracteres():
    usos = re.findall(r"^\s*-?\s*uses:\s*(\S+)", TEXTO, re.M)
    assert len(usos) >= 6
    for uso in usos:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", uso), f"acción sin SHA fijo: {uso}"


def test_los_permisos_por_defecto_son_solo_lectura():
    cabecera = TEXTO.split("\njobs:\n")[0]
    permisos = re.search(r"^permissions:\n((?:  .+\n)+)", cabecera, re.M)
    assert permisos
    assert permisos.group(1).strip().splitlines() == ["contents: read"]


def test_solo_el_job_de_publicar_puede_escribir_pages_y_pedir_el_token_de_oidc():
    assert "pages: write" not in _bloque("test") and "id-token: write" not in _bloque("test")
    publicar = _bloque("publicar")
    assert "pages: write" in publicar and "id-token: write" in publicar
    assert "contents: write" not in TEXTO


def test_las_corridas_de_publicacion_van_de_a_una_y_los_pull_request_no_las_cancelan():
    """One group for every publishing run (cron, retry, manual); a PR gets its own so it never displaces them."""
    esperado = (
        "concurrency:\n"
        "  group: isobaras-${{ github.event_name == 'pull_request' && github.ref || 'publicar' }}\n"
        "  cancel-in-progress: false\n"
    )
    assert esperado in TEXTO


def test_los_horarios_son_4_h_45_min_despues_de_cada_ciclo_y_un_reintento_una_hora_despues():
    crones = re.findall(r'cron:\s*"([^"]+)"', TEXTO)
    assert crones == ["45 4,10,16,22 * * *", "45 5,11,17,23 * * *"]


def test_se_puede_correr_a_mano_y_el_test_corre_en_los_pull_request_del_pipeline():
    assert "workflow_dispatch:" in TEXTO
    assert re.search(r"pull_request:\n    paths:\n      - \"scripts/isobaras/\*\*\"", TEXTO)


def test_publicar_solo_desde_main_y_nunca_en_un_pull_request():
    exacto = "    if: github.event_name != 'pull_request' && github.ref == 'refs/heads/main'\n"
    assert exacto in _bloque("publicar")


def test_publicar_espera_a_que_pasen_los_tests_y_usa_el_entorno_de_pages():
    publicar = _bloque("publicar")
    assert re.search(r"^    needs: test$", publicar, re.M)
    assert re.search(r"^    environment:\n      name: github-pages", publicar, re.M)


def test_cada_job_tiene_timeout_de_20_minutos_o_menos():
    for job in ("test", "publicar"):
        m = re.search(r"timeout-minutes:\s*(\d+)", _bloque(job))
        assert m and int(m.group(1)) <= 20, job


@pytest.mark.parametrize("job", ["test", "publicar"])
def test_el_checkout_no_deja_las_credenciales_en_el_repo(job):
    assert "persist-credentials: false" in _bloque(job)


def test_las_dependencias_se_instalan_desde_el_lock_sin_resolver_de_nuevo():
    assert _bloque("test").count("uv sync --locked") == 1
    assert _bloque("publicar").count("uv sync --locked") == 1


def test_solo_se_despliega_si_el_pipeline_dice_que_hay_ciclo_nuevo():
    publicar = _bloque("publicar")
    assert "--github-output" in publicar
    assert publicar.count("steps.generar.outputs.publicar == 'true'") >= 3  # configure, upload, deploy


# ── Regresiones de seguridad que un cambio chico podría colar ─────────────────


def test_los_disparadores_son_exactamente_estos_tres_y_nunca_pull_request_target():
    eventos = TEXTO.split("\non:\n")[1].split("\npermissions:\n")[0]
    assert re.findall(r"^  ([a-z_]+):", eventos, re.M) == ["pull_request", "schedule", "workflow_dispatch"]
    assert "pull_request_target" not in TEXTO
    assert "workflow_run" not in TEXTO


def test_los_permisos_de_cada_job_son_exactamente_los_esperados():
    assert _permisos("test") == []  # inherits the read-only default
    assert _permisos("publicar") == ["contents: read", "pages: write", "id-token: write"]
    assert "write-all" not in TEXTO and "read-all" not in TEXTO


def test_ningun_run_interpola_expresiones_de_github():
    for linea in re.findall(r"^\s*(?:- )?run:\s*(.+)$", TEXTO, re.M):
        assert "${{" not in linea, f"expresión dentro de un run: {linea}"


def test_cada_checkout_deja_las_credenciales_afuera():
    assert TEXTO.count("uses: actions/checkout@") == TEXTO.count("persist-credentials: false") == 2


def test_python_queda_fijado_para_que_las_ruedas_de_eccodes_siempre_existan():
    assert TEXTO.count('python-version: "3.12"') == 2
