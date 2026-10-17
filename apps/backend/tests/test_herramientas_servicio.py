"""El servicio de herramientas (asistente 2d-1): tender ropa, hacer deporte y lavar el auto, sin FastAPI.

La lógica vivía pegada a `routers/tools.py`. Ahora está en `services/herramientas.py` para que el router y el asistente
(2d-2) usen UNA sola cuenta. Este archivo prueba tres cosas:

- las funciones puras funcionan solas (`om` y `now` entran por parámetro, sin red ni FastAPI);
- dan EXACTAMENTE lo que contestan los endpoints (la extracción no cambió ningún número; las 91 pruebas de los routers
  son la otra red de seguridad);
- los endpoints delegan en el servicio.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.core.params import SOURCE_OPENMETEO_FORECAST
from app.schemas.tools import CarWashDay, HourlyScore, ToolResult
from app.services import herramientas
from tests.hourly_fixtures import AR, DAY0, make_hourly

pytestmark = pytest.mark.integration

HOURLY = "app.routers.tools.get_hourly_forecast_ext"
# Un sábado a las 10:00 de Argentina: arranca la serie, así la hora en curso cae adentro.
AHORA = datetime(2026, 9, 19, 10, 0, tzinfo=AR).astimezone(timezone.utc)


def _serie(**sobrescribir):
    """7 días desde el 19/09/2026 00:00 con lluvia el domingo a la tarde y un poco de calor el lunes."""
    por_defecto = {
        "precipitations": {h: 2.5 for h in range(40, 46)},
        "temps_c": {h: 31.0 for h in range(48 + 11, 48 + 17)},
        "wind_speeds": {h: 25.0 for h in range(72, 80)},
    }
    por_defecto.update(sobrescribir)
    return make_hourly(hours=168, start=DAY0, **por_defecto)


class _AhoraFijo(datetime):
    """`datetime` cuyo `now()` es siempre AHORA (para comparar el servicio con el endpoint)."""

    @classmethod
    def now(cls, tz=None):  # noqa: ANN001, ANN206
        return AHORA.astimezone(tz) if tz is not None else AHORA.replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Tender ropa
# ---------------------------------------------------------------------------


def test_tender_ropa_arma_el_resultado_completo_sin_red() -> None:
    resultado = herramientas.tender_ropa(_serie(), AHORA)
    assert isinstance(resultado, ToolResult)
    assert resultado.tool == "tender-ropa" and resultado.source == SOURCE_OPENMETEO_FORECAST
    assert 0 <= resultado.score <= 100 and resultado.label and resultado.reason
    assert len(resultado.hourly) == 24  # franjas de 3 h: 72 h
    assert sum(1 for h in resultado.hourly if h.is_best) == 1
    assert resultado.temp == 20.0 and resultado.humidity == 50.0  # las condiciones de ahora de la serie


def test_tender_ropa_con_lluvia_adelante_puntua_menos_que_con_cielo_limpio() -> None:
    seco = herramientas.tender_ropa(_serie(precipitations={}), AHORA)
    # lluvia fuerte en las próximas 6 h (de 10 a 16 h)
    mojado = herramientas.tender_ropa(_serie(precipitations={h: 4.0 for h in range(10, 16)}), AHORA)
    assert mojado.score < seco.score
    assert mojado.precip > seco.precip == 0.0


# ---------------------------------------------------------------------------
# Hacer deporte
# ---------------------------------------------------------------------------


def test_hacer_deporte_arma_el_resultado_completo_sin_red() -> None:
    resultado = herramientas.hacer_deporte(_serie(), AHORA)
    assert resultado.tool == "hacer-deporte" and resultado.source == SOURCE_OPENMETEO_FORECAST
    assert len(resultado.hourly) == 12  # franjas de 3 h: 36 h
    assert sum(1 for h in resultado.hourly if h.is_best) == 1
    assert resultado.best_window is None or resultado.best_window.startswith("A las ")


def test_hacer_deporte_usa_su_propio_horizonte_de_lluvia_de_12_horas() -> None:
    # lluvia a las 20 h (10 h adelante): entra en las próximas 12 h del deporte pero NO en las 6 h de tender
    serie = _serie(precipitations={20: 5.0})
    assert herramientas.hacer_deporte(serie, AHORA).precip == 5.0
    assert herramientas.tender_ropa(serie, AHORA).precip == 0.0


# ---------------------------------------------------------------------------
# Lavar el auto
# ---------------------------------------------------------------------------


def test_lavar_coche_da_cinco_dias_con_un_solo_mejor() -> None:
    dias = herramientas.lavar_coche_dias(_serie())
    assert len(dias) == 5 and all(isinstance(d, CarWashDay) for d in dias)
    assert sum(1 for d in dias if d.is_best) == 1
    assert dias[0].date == "2026-09-19" and dias[0].day_label == "sábado"  # el nombre del día en español
    assert [d.day_label for d in dias] == ["sábado", "domingo", "lunes", "martes", "miércoles"]


def test_lavar_coche_el_dia_de_lluvia_puntua_menos_que_uno_limpio() -> None:
    dias = herramientas.lavar_coche_dias(_serie())
    domingo = next(d for d in dias if d.day_label == "domingo")  # llueve de 16 a 22 h
    sabado = next(d for d in dias if d.day_label == "sábado")
    assert domingo.score < sabado.score


def test_lavar_coche_con_una_serie_vacia_no_inventa_dias() -> None:
    assert herramientas.lavar_coche_dias(make_hourly(hours=0, start=DAY0)) == []


# ---------------------------------------------------------------------------
# Helpers de la tira (puros)
# ---------------------------------------------------------------------------


def _tira(*puntajes: int) -> list[HourlyScore]:
    return [
        HourlyScore(timestamp=i, hour_label=f"{i:02d}:00", score=p, is_best=False) for i, p in enumerate(puntajes)
    ]


def test_marcar_el_mejor_marca_solo_la_primera_ocurrencia_del_maximo() -> None:
    marcada = herramientas.mark_best(_tira(50, 80, 80, 60))
    assert [h.is_best for h in marcada] == [False, True, False, False]


def test_marcar_el_mejor_no_modifica_la_tira_original_y_acepta_una_vacia() -> None:
    original = _tira(10, 90)
    herramientas.mark_best(original)
    assert [h.is_best for h in original] == [False, False]
    assert herramientas.mark_best([]) == []


def test_la_mejor_ventana_es_la_racha_mas_larga_con_puntaje_alto() -> None:
    tira = _tira(10, 75, 80, 20, 90, 95, 85, 30)
    assert herramientas.best_window_consecutive(tira, min_score=70) == "04:00–06:00"


def test_la_mejor_ventana_es_none_si_ninguna_hora_llega_al_minimo() -> None:
    assert herramientas.best_window_consecutive(_tira(10, 20, 30), min_score=70) is None
    assert herramientas.best_window_consecutive([], min_score=70) is None


def test_la_mejor_hora_dice_a_las_hh_mm_y_es_none_bajo_el_minimo() -> None:
    assert herramientas.best_hour_label(_tira(10, 55, 30), min_score=40) == "A las 01:00"
    assert herramientas.best_hour_label(_tira(10, 20, 30), min_score=40) is None
    assert herramientas.best_hour_label([], min_score=40) is None


def test_los_limites_de_la_ventana_y_de_la_mejor_hora_son_inclusivos() -> None:
    assert herramientas.best_window_consecutive(_tira(70, 70), min_score=70) == "00:00–01:00"  # 70 cuenta
    assert herramientas.best_window_consecutive(_tira(69, 69), min_score=70) is None
    assert herramientas.best_hour_label(_tira(40, 10), min_score=40) == "A las 00:00"  # 40 cuenta
    assert herramientas.best_hour_label(_tira(39, 10), min_score=40) is None


def test_entre_dos_rachas_iguales_la_mejor_ventana_es_la_primera() -> None:
    assert herramientas.best_window_consecutive(_tira(80, 80, 10, 90, 90), min_score=70) == "00:00–01:00"


def _tira_fija(*puntajes: int):
    """Un reemplazo de `slot_scores` que devuelve una tira con esos puntajes (para probar los mínimos de cada herramienta)."""
    return lambda *_args, **_kwargs: _tira(*puntajes)


def test_tender_ropa_pide_70_puntos_para_nombrar_una_ventana_y_deporte_pide_40_para_nombrar_una_hora() -> None:
    serie = _serie()
    with patch("app.services.herramientas.slot_scores", _tira_fija(60, 65, 60)):
        assert herramientas.tender_ropa(serie, AHORA).best_window is None  # 60 y 65 no llegan a 70
    with patch("app.services.herramientas.slot_scores", _tira_fija(70, 75, 60)):
        assert herramientas.tender_ropa(serie, AHORA).best_window == "00:00–01:00"
    with patch("app.services.herramientas.slot_scores", _tira_fija(30, 35, 20)):
        assert herramientas.hacer_deporte(serie, AHORA).best_window is None  # 35 no llega a 40
    with patch("app.services.herramientas.slot_scores", _tira_fija(30, 45, 20)):
        assert herramientas.hacer_deporte(serie, AHORA).best_window == "A las 01:00"


# ---------------------------------------------------------------------------
# Los endpoints dan lo mismo que el servicio, y delegan en él
# ---------------------------------------------------------------------------


async def test_el_endpoint_de_tender_ropa_da_exactamente_lo_del_servicio(async_client: AsyncClient) -> None:
    serie = _serie()
    with patch(HOURLY, new_callable=AsyncMock, return_value=serie), patch("app.routers.tools.datetime", _AhoraFijo):
        respuesta = await async_client.get("/api/tools/tender-ropa?lat=-34.6&lon=-58.4")
    assert respuesta.status_code == 200
    assert respuesta.json() == herramientas.tender_ropa(serie, AHORA).model_dump(mode="json")


async def test_el_endpoint_de_hacer_deporte_da_exactamente_lo_del_servicio(async_client: AsyncClient) -> None:
    serie = _serie()
    with patch(HOURLY, new_callable=AsyncMock, return_value=serie), patch("app.routers.tools.datetime", _AhoraFijo):
        respuesta = await async_client.get("/api/tools/hacer-deporte?lat=-34.6&lon=-58.4")
    assert respuesta.status_code == 200
    assert respuesta.json() == herramientas.hacer_deporte(serie, AHORA).model_dump(mode="json")


async def test_el_endpoint_de_lavar_coche_da_exactamente_lo_del_servicio(async_client: AsyncClient) -> None:
    serie = _serie()
    with patch(HOURLY, new_callable=AsyncMock, return_value=serie):
        respuesta = await async_client.get("/api/tools/lavar-coche?lat=-34.6&lon=-58.4")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["source"] == SOURCE_OPENMETEO_FORECAST
    assert cuerpo["days"] == [d.model_dump(mode="json") for d in herramientas.lavar_coche_dias(serie)]


async def test_los_endpoints_delegan_en_el_servicio(async_client: AsyncClient) -> None:
    centinela = ToolResult(
        tool="tender-ropa", score=1, label="No apto", color="red", headline="CENTINELA", reason="r", best_window=None, hourly=[],
        temp=1.0, humidity=1.0, wind_speed=1.0, precip=0.0, source=SOURCE_OPENMETEO_FORECAST,
    )
    with (
        patch(HOURLY, new_callable=AsyncMock, return_value=_serie()),
        patch("app.services.herramientas.tender_ropa", return_value=centinela) as tender,
    ):
        respuesta = await async_client.get("/api/tools/tender-ropa?lat=-34.6&lon=-58.4")
    assert respuesta.status_code == 200 and respuesta.json()["headline"] == "CENTINELA"
    tender.assert_called_once()


async def test_el_endpoint_sigue_contestando_503_si_la_serie_no_llego(async_client: AsyncClient) -> None:
    with patch(HOURLY, new_callable=AsyncMock, return_value=None):
        for ruta in ("tender-ropa", "hacer-deporte", "lavar-coche"):
            respuesta = await async_client.get(f"/api/tools/{ruta}?lat=-34.6&lon=-58.4")
            assert respuesta.status_code == 503 and respuesta.json()["detail"] == "forecast_unavailable"


def test_el_horario_de_la_serie_de_prueba_es_el_de_argentina() -> None:
    assert DAY0.utcoffset() == timedelta(hours=-3)
