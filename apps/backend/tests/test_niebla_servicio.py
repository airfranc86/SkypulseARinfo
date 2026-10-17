"""Niebla (asistente 2d-3a-1): el análisis de Open-Meteo y el armado de la respuesta salen del router y de la red.

Antes `get_visibility_forecast` y `get_fog_inference_forecast` pedían a Open-Meteo y analizaban en la misma función, y el armado
de la respuesta vivía dentro del router. Ahora:
- `parse_visibility_forecast` y `parse_fog_inference` son puras (el JSON crudo y la hora entran por parámetro);
- `peek_niebla` lee ese JSON de la caché sin hacer ningún pedido;
- `services/niebla.armar_niebla` arma `NieblaResponse` con las fuentes ya obtenidas.
Mora (2d-3a-2) usa las tres sin red. La página no cambia: las pruebas de caracterización de Niebla siguen iguales y acá se
comparan el router y el servicio.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

import app.services.openmeteo as om_module
from app.schemas.niebla import NieblaResponse
from app.services import niebla as niebla_servicio
from app.services.openmeteo import (
    _AR_TZ,
    FogInferenceSlot,
    VisibilityData,
    get_fog_inference_forecast,
    get_visibility_forecast,
    parse_fog_inference,
    parse_visibility_forecast,
    peek_niebla,
)
from app.services.reportes_aeronauticos.metar import MetarVisibility
from app.services.reportes_aeronauticos.taf import TafHourlySlot
from app.services.visibilidad import classify_visibility
from tests.openmeteo_fake_source import LAT, LON, install  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit

AHORA = datetime(2026, 10, 19, 14, 20, tzinfo=_AR_TZ)  # la próxima hora redonda es las 15:00


def _payload(**por_hora) -> dict:
    """48 h desde las 00:00 del 19/10 (hora argentina), todo despejado salvo lo que se sobrescriba por índice de hora."""
    horas = [datetime(2026, 10, 19, tzinfo=_AR_TZ) + timedelta(hours=i) for i in range(48)]
    base = {
        "time": [h.strftime("%Y-%m-%dT%H:%M") for h in horas],
        "visibility": [20_000.0] * 48,
        "relative_humidity_2m": [50.0] * 48,
        "dew_point_2m": [5.0] * 48,
        "temperature_2m": [20.0] * 48,
        "wind_speed_10m": [10.0] * 48,
        "weather_code": [1] * 48,
    }
    for campo, valores in por_hora.items():
        for indice, valor in valores.items():
            base[campo][indice] = valor
    return {"current": {"time": "2026-10-19T14:00", "visibility": 15_000, "weather_code": 3}, "hourly": base}


# ---------------------------------------------------------------------------
# Los parsers puros
# ---------------------------------------------------------------------------


def test_la_visibilidad_se_lee_del_json_crudo_con_el_tope_fisico_y_empieza_en_la_proxima_hora() -> None:
    datos = parse_visibility_forecast(_payload(visibility={15: 800.0, 16: 4_000.0}), AHORA)
    assert isinstance(datos, VisibilityData)
    assert datos.current_m == 10_000.0  # 15 km se corta al tope de 10 km
    assert datos.weather_code == 3
    assert datos.hourly_labels[0] == "15:00" and len(datos.hourly_labels) == 12
    assert datos.hourly_m[:3] == [800.0, 4_000.0, 10_000.0]  # el 20 km de las horas siguientes también se corta
    assert (datos.fog_level, datos.fog_label) == classify_visibility(10_000.0)[:2]


def test_sin_datos_o_con_un_json_que_no_es_el_esperado_no_hay_visibilidad() -> None:
    assert parse_visibility_forecast(None, AHORA) is None
    assert parse_visibility_forecast({"hourly": {}}, AHORA) is None  # falta `current`
    assert parse_visibility_forecast({"current": {"visibility": 1}}, AHORA) is None  # falta `hourly`
    assert parse_visibility_forecast("no es un objeto", AHORA) is None  # type: ignore[arg-type]


def test_la_visibilidad_no_vuelve_a_horas_que_ya_pasaron_si_la_serie_se_queda_corta() -> None:
    corta = _payload()
    for campo in corta["hourly"]:
        corta["hourly"][campo] = corta["hourly"][campo][:10]  # la serie termina a las 09:00: nada por delante de las 14:20
    datos = parse_visibility_forecast(corta, AHORA)
    assert datos is not None and datos.hourly_m == [] and datos.hourly_labels == []


def test_la_inferencia_aplica_las_reglas_de_niebla_en_orden_de_prioridad() -> None:
    payload = _payload(
        weather_code={15: 45},  # niebla confirmada por el código WMO -> 300 m
        temperature_2m={16: 10.0, 17: 10.0, 18: 10.0},
        dew_point_2m={16: 9.0, 17: 8.0, 18: 6.0},  # depresión 1, 2, 4 grados
        relative_humidity_2m={16: 96.0, 17: 91.0, 18: 85.0},
        wind_speed_10m={16: 2.0, 17: 6.0, 18: 20.0},
    )
    slots = parse_fog_inference(payload, 5, AHORA)
    assert slots is not None
    assert [s.hour_label for s in slots] == ["15:00", "16:00", "17:00", "18:00", "19:00"]
    assert [s.visibility_m for s in slots] == [300.0, 300.0, 1_000.0, 3_000.0, 10_000.0]


def test_los_bordes_de_la_inferencia_son_estrictos() -> None:
    """Depresión del punto de rocío menor a 2 (no igual), humedad desde 95 (inclusive) y viento menor a 5 (no igual)."""
    payload = _payload(
        temperature_2m={15: 10.0, 16: 10.0, 17: 10.0, 18: 10.0},
        dew_point_2m={15: 8.0, 16: 9.0, 17: 9.0, 18: 9.0},  # depresión: 2 (justo en el borde), 1, 1, 1
        relative_humidity_2m={15: 96.0, 16: 95.0, 17: 94.9, 18: 96.0},
        wind_speed_10m={15: 2.0, 16: 2.0, 17: 2.0, 18: 5.0},  # 5 justo en el borde en la última
    )
    slots = parse_fog_inference(payload, 4, AHORA)
    assert slots is not None
    assert slots[0].visibility_m == 1_000.0   # depresión 2 justo: ya no es la regla de 300 m, cae a la de neblina de 1 km
    assert slots[1].visibility_m == 300.0     # humedad 95 justo: sí
    assert slots[2].visibility_m == 1_000.0   # humedad 94,9: cae a la regla de neblina
    assert slots[3].visibility_m == 1_000.0   # viento 5 justo: ya no es 300 m


def test_la_inferencia_respeta_la_cantidad_de_horas_y_los_datos_faltantes() -> None:
    assert len(parse_fog_inference(_payload(), 3, AHORA) or []) == 3
    con_hueco = _payload(relative_humidity_2m={15: None})
    slots = parse_fog_inference(con_hueco, 2, AHORA)
    assert slots is not None and slots[0].visibility_m is None  # sin humedad no se infiere nada: no es "despejado"
    assert slots[1].visibility_m == 10_000.0


def test_la_inferencia_sin_datos_o_sin_horas_por_delante_es_none() -> None:
    assert parse_fog_inference(None, 12, AHORA) is None
    assert parse_fog_inference({"current": {}}, 12, AHORA) is None
    assert parse_fog_inference(_payload(), 12, datetime(2026, 10, 21, 10, 0, tzinfo=_AR_TZ)) is None  # la serie ya terminó


# ---------------------------------------------------------------------------
# peek_niebla: lo que trajo la página de Niebla, sin otro pedido
# ---------------------------------------------------------------------------


async def test_antes_de_cualquier_pedido_no_hay_niebla_y_peek_no_llama_a_la_fuente(install) -> None:  # noqa: F811
    fuente = install(_payload())
    assert peek_niebla(LAT, LON) is None
    assert fuente.calls == []


async def test_lo_que_trajo_el_pedido_de_niebla_se_lee_con_peek_y_se_analiza_igual(install, monkeypatch) -> None:  # noqa: F811
    monkeypatch.setattr(om_module, "_ar_now", lambda: AHORA)
    fuente = install(_payload(visibility={15: 800.0}, weather_code={15: 45}))
    visibilidad = await get_visibility_forecast(LAT, LON)
    niebla = await get_fog_inference_forecast(LAT, LON, hours=12)
    crudo = peek_niebla(LAT, LON)
    assert crudo is not None and len(fuente.calls) == 1  # un solo pedido para las dos lecturas, y peek no hizo otro
    assert parse_visibility_forecast(crudo, AHORA) == visibilidad
    assert parse_fog_inference(crudo, 12, AHORA) == niebla


async def test_la_funcion_de_red_respeta_cuantas_horas_se_piden(install, monkeypatch) -> None:  # noqa: F811
    monkeypatch.setattr(om_module, "_ar_now", lambda: AHORA)
    install(_payload())
    assert len(await get_fog_inference_forecast(LAT, LON, hours=3) or []) == 3
    assert len(await get_fog_inference_forecast(LAT, LON, hours=12) or []) == 12


async def test_otras_coordenadas_no_encuentran_la_niebla(install) -> None:  # noqa: F811
    install(_payload())
    await get_visibility_forecast(LAT, LON)
    assert peek_niebla(-34.6, -58.4) is None


# ---------------------------------------------------------------------------
# armar_niebla: la respuesta de la página, con las fuentes ya obtenidas
# ---------------------------------------------------------------------------


def _metar(visibilidad: float | None = 800.0) -> MetarVisibility:
    return MetarVisibility(
        visibility_m=visibilidad, icao="SACO", station_name="Córdoba Aero", distance_km=12.3, observed_at=AHORA,
    )


def _visibilidad(actual: float | None = 9_000.0) -> VisibilityData:
    nivel, etiqueta, color = classify_visibility(actual)
    return VisibilityData(
        current_m=actual, weather_code=3, fog_level=nivel, fog_label=etiqueta, fog_color=color,
        hourly_m=[2_000.0, 6_000.0], hourly_labels=["15:00", "16:00"],
    )


def test_con_metar_la_visibilidad_de_ahora_es_la_del_metar_y_la_estacion_se_informa() -> None:
    r = niebla_servicio.armar_niebla(_metar(800.0), _visibilidad(9_000.0), None, None)
    assert r is not None and (r.source, r.visibility_m) == ("metar", 800.0)
    assert (r.fog_level, r.fog_label, r.fog_color) == classify_visibility(800.0)
    assert (r.metar_station, r.metar_station_name, r.metar_distance_km) == ("SACO", "Córdoba Aero", 12.3)
    assert r.weather_code == 3


def test_sin_metar_usable_la_visibilidad_de_ahora_es_la_de_open_meteo_pero_la_estacion_se_informa_igual() -> None:
    r = niebla_servicio.armar_niebla(_metar(None), _visibilidad(9_000.0), None, None)
    assert r is not None and (r.source, r.visibility_m) == ("openmeteo", 9_000.0)
    assert r.metar_station == "SACO" and r.metar_distance_km == 12.3


def test_sin_ninguna_fuente_de_visibilidad_actual_no_hay_respuesta() -> None:
    assert niebla_servicio.armar_niebla(_metar(None), None, None, None) is None
    assert niebla_servicio.armar_niebla(_metar(None), None, [TafHourlySlot("15:00", 5_000.0, False)], None) is None


def test_el_pronostico_horario_prefiere_el_taf_despues_la_inferencia_y_al_final_el_campo_de_open_meteo() -> None:
    taf = [TafHourlySlot("15:00", 300.0, True), TafHourlySlot("16:00", 9_000.0, False)]
    inferencia = [FogInferenceSlot("15:00", 1_000.0)]
    con_taf = niebla_servicio.armar_niebla(_metar(), _visibilidad(), taf, inferencia)
    assert con_taf is not None and con_taf.hourly_source == "taf" and len(con_taf.hourly) == 2
    assert [h.fog_level for h in con_taf.hourly] == [3, classify_visibility(9_000.0)[0]]  # 300 m es niebla (nivel 3)
    sin_taf = niebla_servicio.armar_niebla(_metar(), _visibilidad(), None, inferencia)
    assert sin_taf is not None and sin_taf.hourly_source == "openmeteo_inference" and sin_taf.hourly[0].visibility_m == 1_000.0
    solo_om = niebla_servicio.armar_niebla(_metar(), _visibilidad(), [], [])
    assert solo_om is not None and solo_om.hourly_source == "openmeteo"
    assert [h.hour_label for h in solo_om.hourly] == ["15:00", "16:00"]


def test_sin_pronostico_horario_de_ninguna_fuente_queda_vacio_y_lo_dice() -> None:
    sin_horas = VisibilityData(9_000.0, 3, *classify_visibility(9_000.0), hourly_m=[], hourly_labels=[])
    r = niebla_servicio.armar_niebla(_metar(), sin_horas, None, None)
    assert r is not None and r.hourly == [] and r.hourly_source == "openmeteo"
    sin_vis = niebla_servicio.armar_niebla(_metar(800.0), None, None, None)
    assert sin_vis is not None and sin_vis.hourly == [] and sin_vis.hourly_source == "none" and sin_vis.weather_code is None


# ---------------------------------------------------------------------------
# El router da lo mismo que el servicio y delega en él
# ---------------------------------------------------------------------------

_FUENTES = "app.routers.niebla"


async def test_el_endpoint_da_exactamente_lo_del_servicio(async_client: AsyncClient) -> None:
    taf = [TafHourlySlot("15:00", 300.0, True), TafHourlySlot("16:00", 5_000.0, False)]
    with (
        patch(f"{_FUENTES}.get_nearest_metar_visibility", AsyncMock(return_value=_metar(800.0))),
        patch(f"{_FUENTES}.get_visibility_forecast", AsyncMock(return_value=_visibilidad())),
        patch(f"{_FUENTES}.get_nearest_taf_hourly", AsyncMock(return_value=taf)),
        patch(f"{_FUENTES}.get_fog_inference_forecast", AsyncMock(return_value=None)),
    ):
        respuesta = await async_client.get("/api/niebla?lat=-31.4&lon=-64.2")
    assert respuesta.status_code == 200
    esperado = niebla_servicio.armar_niebla(_metar(800.0), _visibilidad(), taf, None)
    assert respuesta.json() == esperado.model_dump(mode="json")


async def test_el_endpoint_delega_en_el_servicio_y_traduce_la_falta_de_datos_a_503(async_client: AsyncClient) -> None:
    centinela = NieblaResponse(
        visibility_m=1.0, fog_level=3, fog_label="CENTINELA", fog_color="#000", weather_code=None, hourly=[],
    )
    base = [
        patch(f"{_FUENTES}.get_nearest_metar_visibility", AsyncMock(return_value=_metar(None))),
        patch(f"{_FUENTES}.get_visibility_forecast", AsyncMock(return_value=None)),
        patch(f"{_FUENTES}.get_nearest_taf_hourly", AsyncMock(return_value=None)),
        patch(f"{_FUENTES}.get_fog_inference_forecast", AsyncMock(return_value=None)),
    ]
    for parche in base:
        parche.start()
    try:
        with patch("app.services.niebla.armar_niebla", return_value=centinela) as armar:
            ok = await async_client.get("/api/niebla?lat=-31.4&lon=-64.2")
        assert ok.status_code == 200 and ok.json()["fog_label"] == "CENTINELA" and armar.call_count == 1
        sin_datos = await async_client.get("/api/niebla?lat=-31.4&lon=-64.2")  # el servicio real: ninguna fuente actual
        assert sin_datos.status_code == 503 and sin_datos.json()["detail"] == "visibility_unavailable"
    finally:
        for parche in base:
            parche.stop()
