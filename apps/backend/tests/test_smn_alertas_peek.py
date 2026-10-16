"""`peek_smn_alertas`: los avisos del SMN que ya están en memoria, sin refrescar ni esperar (para el asistente)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import app.services.smn_alertas as smn
from app.schemas.smn_alertas import SmnAlerta

pytestmark = pytest.mark.unit

AHORA = datetime(2026, 10, 17, 15, 0, tzinfo=timezone.utc)
CORDOBA = (-31.4, -64.2)
LEJOS = (-38.0, -57.5)  # Mar del Plata
POLIGONO = ((-31.0, -64.6), (-31.0, -63.8), (-31.8, -63.8), (-31.8, -64.6))  # una caja alrededor de Córdoba


def _aviso(nivel="naranja", tipo="Tormentas", hasta=AHORA + timedelta(hours=6)):
    return SmnAlerta(
        nivel=nivel, tipo=tipo, fecha_desde=AHORA - timedelta(hours=1), fecha_hasta=hasta, descripcion="x",
    )


def _entrada(aviso, status="Actual", poligonos=(POLIGONO,)):
    return smn.CapAlert(alerta=aviso, status=status, polygons=poligonos)


@pytest.fixture(autouse=True)
def estado_limpio(monkeypatch):
    smn.reset_cache()
    monkeypatch.setattr(smn, "_utcnow", lambda: AHORA)
    monkeypatch.setattr(smn, "_monotonic", lambda: 1000.0)
    yield
    smn.reset_cache()


def _cargar(monkeypatch, *entradas, ultimo_ok=990.0, completo=True, proximo=None):
    estado = smn._FeedState(
        entries={f"g{i}": e for i, e in enumerate(entradas)}, last_feed_ok=ultimo_ok, complete=completo,
        next_attempt_at=proximo,
    )
    monkeypatch.setattr(smn, "_state", estado)


def test_sin_nada_leido_todavia_responde_que_no_esta_verificado():
    r = smn.peek_smn_alertas(*CORDOBA)
    assert (r.available, r.alertas) == (False, [])


def test_con_el_feed_leido_devuelve_los_avisos_de_ese_punto(monkeypatch):
    _cargar(monkeypatch, _entrada(_aviso()))
    r = smn.peek_smn_alertas(*CORDOBA)
    assert r.available is True and [a.tipo for a in r.alertas] == ["Tormentas"]
    assert smn.peek_smn_alertas(*LEJOS).alertas == []  # fuera del polígono: no hay avisos, y el feed sí está verificado
    assert smn.peek_smn_alertas(*LEJOS).available is True


def test_sin_coordenadas_devuelve_todos(monkeypatch):
    _cargar(monkeypatch, _entrada(_aviso()), _entrada(_aviso(tipo="Viento")))
    assert len(smn.peek_smn_alertas().alertas) == 2


def test_un_aviso_vencido_o_que_no_esta_actual_no_se_devuelve(monkeypatch):
    _cargar(
        monkeypatch,
        _entrada(_aviso(tipo="Vencido", hasta=AHORA - timedelta(minutes=1))),
        _entrada(_aviso(tipo="Cancelado"), status="Cancel"),
        _entrada(_aviso(tipo="Vigente")),
    )
    assert [a.tipo for a in smn.peek_smn_alertas(*CORDOBA).alertas] == ["Vigente"]


def test_un_feed_leido_hace_demasiado_no_esta_verificado(monkeypatch):
    _cargar(monkeypatch, _entrada(_aviso()), ultimo_ok=1000.0 - 10 * 3600)
    r = smn.peek_smn_alertas(*CORDOBA)
    assert (r.available, r.alertas) == (False, [])  # "no sé", no "no hay"


def test_un_feed_incompleto_no_esta_verificado(monkeypatch):
    _cargar(monkeypatch, _entrada(_aviso()), completo=False)
    assert smn.peek_smn_alertas(*CORDOBA).available is False


def test_nunca_refresca_aunque_el_refresco_este_vencido(monkeypatch):
    llamados = []

    async def refresco_que_no_debe_correr(*_a, **_k):
        llamados.append(1)
        raise AssertionError("peek no puede refrescar")

    monkeypatch.setattr(smn, "_refresh", refresco_que_no_debe_correr)
    _cargar(monkeypatch, _entrada(_aviso()), proximo=None)  # `next_attempt_at=None`: get_smn_alertas refrescaría
    assert smn.peek_smn_alertas(*CORDOBA).available is True
    assert llamados == []


async def test_no_espera_el_candado_de_un_refresco_en_curso(monkeypatch):
    _cargar(monkeypatch, _entrada(_aviso()))
    async with smn._cache_lock:  # hay un refresco "en curso"
        assert smn.peek_smn_alertas(*CORDOBA).available is True  # y peek contesta igual, al instante


async def test_get_smn_alertas_sigue_igual_con_el_feed_ya_leido(monkeypatch):
    _cargar(monkeypatch, _entrada(_aviso()), proximo=2000.0)  # no toca vencido: no refresca
    r = await smn.get_smn_alertas(*CORDOBA)
    assert r.available is True and [a.tipo for a in r.alertas] == ["Tormentas"]
    assert r == smn.peek_smn_alertas(*CORDOBA)


def test_los_avisos_vencidos_se_filtran_con_la_hora_que_se_le_da(monkeypatch):
    _cargar(monkeypatch, _entrada(_aviso(hasta=AHORA + timedelta(hours=1))))
    assert len(smn.peek_smn_alertas(*CORDOBA).alertas) == 1  # con la hora de `_utcnow` (AHORA) sigue vigente
    assert smn.peek_smn_alertas(*CORDOBA, now=AHORA + timedelta(hours=2)).alertas == []
    assert smn.peek_smn_alertas(*CORDOBA, now=AHORA + timedelta(hours=2)).fetched_at == AHORA + timedelta(hours=2)
