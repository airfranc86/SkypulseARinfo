"""Structural checks of `.github/workflows/isobaras.yml`: the safety properties we decided, read as text.

The workflow cannot be run locally (it needs GitHub), so these tests pin what must never silently change:
pinned actions, minimal permissions, who may publish, which events trigger it, how often it asks for a new cycle.
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


def test_solo_el_job_de_desplegar_puede_escribir_pages_y_pedir_el_token_de_oidc():
    for job in ("test", "generar"):
        assert "pages: write" not in _bloque(job) and "id-token: write" not in _bloque(job), job
    desplegar = _bloque("desplegar")
    assert "pages: write" in desplegar and "id-token: write" in desplegar
    assert "contents: write" not in TEXTO


def test_las_corridas_de_publicacion_van_de_a_una_y_los_pull_request_no_las_cancelan():
    """One group for every publishing run (cron, manual); a PR gets its own so it never displaces them."""
    esperado = (
        "concurrency:\n"
        "  group: isobaras-${{ github.event_name == 'pull_request' && github.ref || 'publicar' }}\n"
        "  cancel-in-progress: false\n"
    )
    assert esperado in TEXTO


def test_pregunta_por_un_ciclo_nuevo_cada_20_minutos_fuera_de_la_hora_en_punto():
    """GitHub delays (and sometimes drops) scheduled runs: asking often means a late run delays the map by minutes,
    not by a whole model cycle (6 h). The first runs of the project came 4.5 h late with only 8 asks a day."""
    crones = re.findall(r'cron:\s*"([^"]+)"', TEXTO)
    assert crones == ["7,27,47 * * * *"]
    minutos = [int(m) for m in crones[0].split()[0].split(",")]
    assert 0 not in minutos, "la hora en punto es cuando GitHub más atrasa las corridas programadas"
    assert all(b - a >= 5 for a, b in zip(minutos, minutos[1:])), "GitHub no admite menos de 5 minutos entre corridas"
    assert 60 - minutos[-1] + minutos[0] >= 5
    assert (60 // len(minutos)) <= 20 + 1  # one ask every ~20 minutes


def test_se_puede_correr_a_mano_y_el_test_corre_en_los_pull_request_del_pipeline():
    assert "workflow_dispatch:" in TEXTO
    assert re.search(r"pull_request:\n    paths:\n      - \"scripts/isobaras/\*\*\"", TEXTO)


def test_generar_solo_desde_main_y_nunca_en_un_pull_request():
    exacto = "    if: github.event_name != 'pull_request' && github.ref == 'refs/heads/main'\n"
    assert exacto in _bloque("generar")


def test_generar_espera_a_que_pasen_los_tests_en_cada_corrida_y_estos_no_se_saltean_en_ninguna():
    """`main` has no branch protection: this is the only thing that keeps a red `main` from reaching users."""
    assert re.search(r"^    needs: test$", _bloque("generar"), re.M)
    assert not re.search(r"^    if:", _bloque("test"), re.M), "los tests corren en todos los eventos"


def test_desplegar_depende_de_generar_solo_corre_si_hay_ciclo_nuevo_y_es_el_unico_con_entorno():
    desplegar = _bloque("desplegar")
    assert re.search(r"^    needs: generar$", desplegar, re.M)
    assert "    if: needs.generar.outputs.publicar == 'true'\n" in desplegar
    assert re.search(r"^    environment:\n      name: github-pages", desplegar, re.M)
    # A job with an environment leaves a deployment record on every run: only the one that really deploys has it,
    # so the 72 daily asks that find nothing new leave no trace in the Deployments list.
    assert "environment:" not in _bloque("test") and "environment:" not in _bloque("generar")
    assert TEXTO.count("environment:") == 1


def test_generar_cuenta_si_hay_ciclo_nuevo_y_sube_el_sitio_solo_en_ese_caso():
    generar = _bloque("generar")
    assert re.search(r"^    outputs:\n      publicar: \$\{\{ steps\.generar\.outputs\.publicar \}\}$", generar, re.M)
    assert "--github-output" in generar
    assert generar.count("steps.generar.outputs.publicar == 'true'") == 1  # the upload of the artifact
    assert "actions/upload-pages-artifact@" in generar
    assert "actions/deploy-pages@" not in generar


def test_los_jobs_que_no_publican_no_declaran_permisos_propios_ni_en_una_sola_linea():
    for job in ("test", "generar"):
        assert "permissions" not in _bloque(job), f"{job}: hereda solo-lectura y nada más (tampoco `permissions: {{...}}`)"


def test_cada_job_tiene_timeout_de_20_minutos_o_menos():
    for job in ("test", "generar", "desplegar"):
        m = re.search(r"timeout-minutes:\s*(\d+)", _bloque(job))
        assert m and int(m.group(1)) <= 20, job


@pytest.mark.parametrize("job", ["test", "generar"])
def test_el_checkout_no_deja_las_credenciales_en_el_repo(job):
    assert "persist-credentials: false" in _bloque(job)


def test_las_dependencias_se_instalan_desde_el_lock_sin_resolver_de_nuevo():
    assert _bloque("test").count("uv sync --locked") == 1
    assert _bloque("generar").count("uv sync --locked") == 1
    assert "uv sync" not in _bloque("desplegar")


def test_desplegar_solo_despliega_el_artefacto_que_subio_generar_y_no_baja_el_repo():
    desplegar = _bloque("desplegar")
    assert "actions/deploy-pages@" in desplegar and "actions/configure-pages@" in desplegar
    assert "actions/checkout@" not in desplegar and "uv " not in desplegar


# ── Regresiones de seguridad que un cambio chico podría colar ─────────────────


def test_los_disparadores_son_exactamente_estos_tres_y_nunca_pull_request_target():
    eventos = TEXTO.split("\non:\n")[1].split("\npermissions:\n")[0]
    assert re.findall(r"^  ([a-z_]+):", eventos, re.M) == ["pull_request", "schedule", "workflow_dispatch"]
    assert "pull_request_target" not in TEXTO
    assert "workflow_run" not in TEXTO


def test_los_permisos_de_cada_job_son_exactamente_los_esperados():
    assert _permisos("test") == []  # inherits the read-only default
    assert _permisos("generar") == []  # same: it only reads the repo and writes an artifact
    assert _permisos("desplegar") == ["pages: write", "id-token: write"]  # it does not read the repo at all
    assert "write-all" not in TEXTO and "read-all" not in TEXTO


def test_ningun_run_interpola_expresiones_de_github():
    for linea in re.findall(r"^\s*(?:- )?run:\s*(.+)$", TEXTO, re.M):
        assert "${{" not in linea, f"expresión dentro de un run: {linea}"


def test_cada_checkout_deja_las_credenciales_afuera():
    assert TEXTO.count("uses: actions/checkout@") == TEXTO.count("persist-credentials: false") == 2


def test_python_queda_fijado_para_que_las_ruedas_de_eccodes_siempre_existan():
    assert TEXTO.count('python-version: "3.12"') == 2
