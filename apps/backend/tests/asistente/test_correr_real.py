"""Fase 3b: el script que corre los conjuntos dorado y rojo contra el modelo REAL (`tests/asistente/correr_real.py`).

Lo corre el dueño (gasta cupo del día de Groq). Acá se prueba todo lo que no necesita red: qué casos corre, a qué ritmo, qué
cuenta como discrepancia, el resumen, la proyección de cupos y el informe. Todo con un modelo falso y sin dormir de verdad.
"""
import json
from pathlib import Path

import pytest

from app.core.config import settings
from app.services.asistente import modelo as modelo_mod
from app.services.asistente.modelo import ModeloFalso, ModeloNoDisponible
from tests.asistente import correr_real as cr

pytestmark = pytest.mark.unit

DIR = Path(__file__).parent
DORADO = json.loads((DIR / "golden.json").read_text(encoding="utf-8"))
ROJO = json.loads((DIR / "red.json").read_text(encoding="utf-8"))


# --- Los casos --------------------------------------------------------------------------------------------------------------

def test_el_conjunto_dorado_son_todos_sus_casos_con_su_hoja_y_sus_frases():
    casos = cr.cargar_casos("dorado")
    assert [c.id for c in casos] == [c["id"] for c in DORADO]
    primero = casos[0]
    assert (primero.conjunto, primero.escenario, primero.estado_esperado) == ("dorado", DORADO[0]["escenario"], "ok")
    assert primero.contiene == tuple(DORADO[0]["contiene"])


def test_del_conjunto_rojo_solo_corren_las_preguntas_hostiles_porque_lo_demas_prueba_al_verificador_solo():
    casos = cr.cargar_casos("rojo")
    esperados = [c["id"] for c in ROJO if c["tipo"] == "pregunta"]
    assert [c.id for c in casos] == esperados and len(esperados) >= 3
    assert all(c.conjunto == "rojo" for c in casos)


def test_ambos_son_el_dorado_y_despues_el_rojo_con_ids_unicos():
    casos = cr.cargar_casos("ambos")
    assert [c.id for c in casos] == [c.id for c in cr.cargar_casos("dorado")] + [c.id for c in cr.cargar_casos("rojo")]
    assert len({c.id for c in casos}) == len(casos)


def test_un_conjunto_que_no_existe_se_rechaza():
    with pytest.raises(ValueError):
        cr.cargar_casos("verde")


def test_todos_los_escenarios_de_los_casos_existen():
    from tests.asistente import escenarios as esc

    assert {c.escenario for c in cr.cargar_casos("ambos")} <= set(esc.ESCENARIOS)


def test_el_plan_corta_desde_un_caso_con_un_maximo():
    casos = cr.cargar_casos("dorado")
    assert cr.plan(casos, 0, 3) == casos[:3]
    assert cr.plan(casos, 5, 3) == casos[5:8]
    assert cr.plan(casos, 0, None) == casos
    assert cr.plan(casos, len(casos) + 10, 5) == []
    assert cr.plan(casos, 0, 0) == []


# --- El ritmo ---------------------------------------------------------------------------------------------------------------

def test_la_pausa_entre_preguntas_cuida_los_tokens_por_minuto():
    assert cr.pausa_entre_preguntas() == 16  # 1.900 tokens a 8.000 por minuto: una cada 14,25 s, más uno de margen
    assert cr.pausa_entre_preguntas(800, 8000) == 7
    assert cr.pausa_entre_preguntas(1900, 4000) == 30
    assert cr.pausa_entre_preguntas(1900, 8000) * cr.TOKENS_PESIMISTAS_POR_PREGUNTA // 60 <= cr.TOKENS_POR_MINUTO


# --- Qué cuenta como discrepancia ---------------------------------------------------------------------------------------------

def _caso(**cambios):
    base = dict(id="x", conjunto="dorado", escenario="templado", pregunta="¿Va a llover?", pagina=None,
                estado_esperado="ok", contiene=(), no_contiene=())
    return cr.Caso(**{**base, **cambios})


def test_una_respuesta_que_cumple_no_tiene_discrepancias():
    assert cr.discrepancias(_caso(contiene=("22,4 °C",), no_contiene=("aviso",)), "ok", "Ahora hay 22,4 °C.") == []


def test_cada_incumplimiento_se_nombra():
    caso = _caso(contiene=("22,4 °C", "55 %"), no_contiene=("aviso oficial",))
    d = cr.discrepancias(caso, "sin_dato", "Hay un aviso oficial. " + "x" * 800)
    assert any("estado sin_dato" in x and "ok" in x for x in d)
    assert any("larga" in x for x in d)
    assert any("falta" in x and "22,4 °C" in x for x in d) and any("falta" in x and "55 %" in x for x in d)
    assert any("sobra" in x and "aviso oficial" in x for x in d)


def test_el_largo_maximo_es_inclusivo_y_un_caracter_mas_ya_es_largo():
    from app.services.asistente.verificador import MAX_CARACTERES

    assert cr.discrepancias(_caso(), "ok", "x" * MAX_CARACTERES) == []
    assert any("larga" in x for x in cr.discrepancias(_caso(), "ok", "x" * (MAX_CARACTERES + 1)))


def test_el_estado_esperado_distinto_de_ok_tambien_se_compara():
    assert cr.discrepancias(_caso(estado_esperado="sin_dato"), "sin_dato", "No tengo ese dato a mano.") == []
    assert cr.discrepancias(_caso(estado_esperado="sin_dato"), "ok", "Algo.") != []


# --- Resumen y proyección ------------------------------------------------------------------------------------------------------

def _res(i, estado="ok", tokens=1400, ms=2000, motivos=(), error=None, discrepancias=()):
    return cr.Resultado(caso=_caso(id=f"c{i}"), estado=estado, motivos=tuple(motivos), texto="t", tokens=tokens, ms=ms,
                        error=error, discrepancias=tuple(discrepancias))


def test_el_resumen_cuenta_estados_motivos_tokens_y_latencia():
    resultados = [
        _res(1, tokens=1000, ms=1000), _res(2, tokens=2000, ms=3000),
        _res(3, estado="sin_dato", motivos=["numero_inventado"], tokens=1500, ms=2000, discrepancias=["estado"]),
        _res(4, estado="sin_dato", motivos=["numero_inventado", "formato"], tokens=None, ms=500),
        _res(5, estado=None, tokens=None, ms=0, error="timeout"),
    ]
    r = cr.resumen(resultados)
    assert (r["total"], r["ok"], r["sin_dato"], r["errores"]) == (5, 2, 2, 1)
    assert r["motivos"] == {"numero_inventado": 2, "formato": 1}
    assert r["con_discrepancias"] == 1
    assert (r["tokens_medidos"], r["tokens_total"], r["tokens_promedio"], r["tokens_maximo"]) == (3, 4500, 1500, 2000)
    assert r["ms_promedio"] == 1300 and r["ms_p95"] == 3000


def test_un_resumen_sin_resultados_ni_tokens_no_revienta():
    vacio = cr.resumen([])
    assert vacio["total"] == 0 and vacio["tokens_promedio"] is None and vacio["ms_p95"] is None
    sin_tokens = cr.resumen([_res(1, tokens=None)])
    assert sin_tokens["tokens_medidos"] == 0 and sin_tokens["tokens_maximo"] is None


def test_la_proyeccion_calcula_cuantas_preguntas_entran_por_dia_y_por_minuto_con_margen():
    p = cr.proyeccion(promedio=1400, maximo=1900)
    assert p["por_dia_tipico"] == 128      # 200.000 * 0,9 / 1.400
    assert p["por_dia_pesimista"] == 94    # 200.000 * 0,9 / 1.900
    assert p["por_minuto"] == 4            # 8.000 / 1.900
    assert p["cupo_global_sugerido"] == 90 and p["cupo_cliente_sugerido"] == 9  # redondeado a 5 hacia abajo, un décimo por persona


def test_la_proyeccion_sin_tokens_medidos_no_inventa_nada():
    assert cr.proyeccion(None, None) is None


# --- El informe -------------------------------------------------------------------------------------------------------------

def test_el_informe_trae_el_resumen_la_proyeccion_y_cada_caso():
    from datetime import datetime, timezone

    resultados = [_res(1), _res(2, estado="sin_dato", motivos=["formato"], discrepancias=["estado sin_dato (esperado ok)"])]
    informe = cr.formatear_informe(resultados, cr.resumen(resultados), cr.proyeccion(1400, 1400), datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc), "openai/gpt-oss-20b")
    for pieza in ("openai/gpt-oss-20b", "2026-10-18", "c1", "c2", "sin_dato", "formato", "ASISTENTE_CUPO_GLOBAL_DIA", "estado sin_dato (esperado ok)"):
        assert pieza in informe, pieza


def test_el_informe_no_se_rompe_con_barras_ni_saltos_de_linea_en_el_texto():
    from datetime import datetime, timezone

    r = cr.Resultado(caso=_caso(), estado="ok", motivos=(), texto="a | b\nc", tokens=1, ms=1, error=None, discrepancias=())
    informe = cr.formatear_informe([r], cr.resumen([r]), None, datetime(2026, 10, 18, tzinfo=timezone.utc), "m")
    fila = next(linea for linea in informe.splitlines() if linea.startswith("| x "))
    assert "\n" not in fila and fila.count("|") == informe.splitlines()[informe.splitlines().index(fila) - 1].count("|")


# --- Correr ----------------------------------------------------------------------------------------------------------------

class ModeloDeMentira:
    """Responde como el falso, anota los tokens que 'gastó' y puede fallar a pedido."""

    def __init__(self, fallas=()):
        self.fallas = list(fallas)
        self.llamadas = 0
        self.tokens_ultima_llamada = None

    async def generar(self, pregunta, hoja):
        self.llamadas += 1
        self.tokens_ultima_llamada = None
        if self.fallas:
            falla = self.fallas.pop(0)
            if falla is not None:
                raise falla
        self.tokens_ultima_llamada = 1234
        return await ModeloFalso().generar(pregunta, hoja)


class Reloj:
    def __init__(self):
        self.pausas = []

    async def dormir(self, segundos):
        self.pausas.append(segundos)


async def test_corre_cada_caso_con_su_hoja_y_anota_estado_tokens_y_discrepancias():
    casos = cr.plan(cr.cargar_casos("dorado"), 0, 3)
    reloj = Reloj()
    resultados = await cr.correr(casos, ModeloDeMentira(), pausa=16, dormir=reloj.dormir)
    assert [r.caso.id for r in resultados] == [c.id for c in casos]
    assert all(r.estado == "ok" and r.tokens == 1234 and r.error is None for r in resultados)
    assert all(r.discrepancias == () for r in resultados)  # el modelo falso cumple lo que el dorado pide


async def test_espera_entre_preguntas_y_no_antes_de_la_primera():
    casos = cr.plan(cr.cargar_casos("dorado"), 0, 4)
    reloj = Reloj()
    await cr.correr(casos, ModeloDeMentira(), pausa=16, dormir=reloj.dormir)
    assert reloj.pausas == [16, 16, 16]


async def test_un_limite_de_groq_espera_lo_que_pide_y_reintenta_una_vez():
    casos = cr.plan(cr.cargar_casos("dorado"), 0, 1)
    reloj = Reloj()
    modelo = ModeloDeMentira(fallas=[ModeloNoDisponible("limite", 30)])
    resultados = await cr.correr(casos, modelo, pausa=16, dormir=reloj.dormir)
    assert resultados[0].estado == "ok" and modelo.llamadas == 2
    assert reloj.pausas == [30]


async def test_la_espera_por_un_limite_tiene_tope():
    casos = cr.plan(cr.cargar_casos("dorado"), 0, 1)
    reloj = Reloj()
    await cr.correr(casos, ModeloDeMentira(fallas=[ModeloNoDisponible("limite", 5000)]), pausa=16, dormir=reloj.dormir)
    assert reloj.pausas == [cr.ESPERA_MAXIMA_SEGUNDOS]


async def test_una_falla_que_se_repite_queda_anotada_y_la_corrida_sigue():
    casos = cr.plan(cr.cargar_casos("dorado"), 0, 3)
    modelo = ModeloDeMentira(fallas=[ModeloNoDisponible("timeout"), ModeloNoDisponible("timeout")])
    resultados = await cr.correr(casos, modelo, pausa=1, dormir=Reloj().dormir)
    assert resultados[0].estado is None and resultados[0].error == "timeout"
    assert [r.estado for r in resultados[1:]] == ["ok", "ok"]


@pytest.mark.parametrize("motivo", ["sin_clave", "credenciales"])
async def test_si_la_clave_no_sirve_se_frena_enseguida_sin_gastar_el_resto(motivo):
    casos = cr.plan(cr.cargar_casos("dorado"), 0, 5)
    modelo = ModeloDeMentira(fallas=[ModeloNoDisponible(motivo)])
    resultados = await cr.correr(casos, modelo, pausa=1, dormir=Reloj().dormir)
    assert len(resultados) == 1 and resultados[0].error == motivo and modelo.llamadas == 1


async def test_un_modelo_que_inventa_una_cifra_queda_como_sin_dato_con_el_motivo():
    class Inventor(ModeloDeMentira):
        async def generar(self, pregunta, hoja):
            self.tokens_ultima_llamada = 900
            return "Ahora hay 99 °C."

    casos = cr.plan(cr.cargar_casos("dorado"), 0, 1)
    r = (await cr.correr(casos, Inventor(), pausa=1, dormir=Reloj().dormir))[0]
    assert r.estado == "sin_dato" and "numero_inventado" in r.motivos and r.tokens == 900
    assert r.discrepancias  # y eso se ve como una discrepancia contra lo que el dorado esperaba


# --- La línea de comandos ------------------------------------------------------------------------------------------------------

def test_listar_muestra_el_plan_y_el_costo_sin_llamar_a_nadie(monkeypatch, capsys):
    def prohibido(*_a, **_k):
        raise AssertionError("listar no puede crear el modelo ni pedir nada")

    monkeypatch.setattr(cr, "ModeloGroq", prohibido)
    assert cr.main(["--listar", "--max", "10"]) == 0
    salida = capsys.readouterr().out
    assert "10 preguntas" in salida and "tokens" in salida and "%" in salida


def test_sin_clave_no_corre_y_dice_que_hace_falta_sin_mostrar_nada_secreto(monkeypatch, capsys):
    monkeypatch.setattr(settings, "groq_api_key", "")
    assert cr.main(["--si", "--max", "1"]) == 2
    assert "GROQ_API_KEY" in capsys.readouterr().out


def test_sin_confirmar_no_corre(monkeypatch, capsys):
    monkeypatch.setattr(settings, "groq_api_key", "gsk_clave_de_prueba_0123456789")
    monkeypatch.setattr("builtins.input", lambda *_a: "n")

    def prohibido(*_a, **_k):
        raise AssertionError("sin confirmar no se crea el modelo")

    monkeypatch.setattr(cr, "ModeloGroq", prohibido)
    assert cr.main(["--max", "1"]) == 1
    assert "gsk_" not in capsys.readouterr().out


def test_el_modelo_falso_de_las_pruebas_sigue_cumpliendo_el_protocolo():
    assert isinstance(ModeloFalso(), modelo_mod.Modelo)


def test_el_p95_deja_afuera_al_5_por_ciento_mas_lento_y_no_es_el_maximo():
    resultados = [_res(i, ms=i * 100) for i in range(1, 21)]  # 100, 200, ... 2.000 ms
    r = cr.resumen(resultados)
    assert r["ms_p95"] == 1900 and r["ms_promedio"] == 1050
