"""Tests para el cliente de alertas SMN — parsing tolerante, fallback, cache."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.services.smn_alertas import (
    _find_field,
    _parse_alert_datetime,
    _parse_alert_item,
    get_smn_alertas,
)

_AL_URL = "https://ws.smn.gob.ar/alerts/type/AL"
_AC_URL = "https://ws.smn.gob.ar/alerts/type/AC"


@pytest.fixture(autouse=True)
def _clear_cache():
    """El cache es un TTLCache module-level — limpiarlo entre tests."""
    import app.services.smn_alertas as mod
    mod._cache.clear()
    yield
    mod._cache.clear()


# ---------------------------------------------------------------------------
# _find_field / _parse_alert_datetime — helpers puros
# ---------------------------------------------------------------------------

class TestFindField:
    def test_returns_first_matching_key(self):
        assert _find_field({"nivel": "rojo"}, ("level", "nivel")) == "rojo"

    def test_skips_empty_string(self):
        assert _find_field({"level": "", "nivel": "rojo"}, ("level", "nivel")) == "rojo"

    def test_returns_none_when_no_candidate_present(self):
        assert _find_field({"other": "x"}, ("level", "nivel")) is None


class TestParseAlertDatetime:
    def test_none_is_none(self):
        assert _parse_alert_datetime(None) is None

    def test_unix_timestamp_int(self):
        dt = _parse_alert_datetime(1735689600)
        assert dt is not None
        assert dt.year == 2025

    def test_unix_timestamp_as_string(self):
        dt = _parse_alert_datetime("1735689600")
        assert dt is not None
        assert dt.year == 2025

    def test_iso_string(self):
        dt = _parse_alert_datetime("2026-01-15T14:00:00Z")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 1

    def test_garbage_string_is_none(self):
        assert _parse_alert_datetime("no es una fecha") is None

    def test_empty_string_is_none(self):
        assert _parse_alert_datetime("") is None


class TestParseAlertItem:
    def test_full_item_with_common_field_names(self):
        item = {
            "level": "naranja",
            "phenomenon": "Viento",
            "description": "Vientos fuertes en la zona serrana",
            "from": "2026-01-15T00:00:00Z",
            "to": "2026-01-16T00:00:00Z",
        }
        alerta = _parse_alert_item(item)
        assert alerta is not None
        assert alerta.nivel == "naranja"
        assert alerta.tipo == "Viento"
        assert alerta.descripcion == "Vientos fuertes en la zona serrana"
        assert alerta.fecha_desde is not None
        assert alerta.fecha_hasta is not None

    def test_alt_field_names_spanish(self):
        item = {"nivel": "amarillo", "tipo": "Tormenta", "descripcion": "Tormentas aisladas"}
        alerta = _parse_alert_item(item)
        assert alerta is not None
        assert alerta.nivel == "amarillo"
        assert alerta.tipo == "Tormenta"

    def test_missing_descripcion_is_discarded(self):
        """Sin descripción no hay nada útil que mostrar — se descarta, no crashea."""
        assert _parse_alert_item({"level": "rojo"}) is None

    def test_missing_nivel_tipo_falls_back_to_placeholder(self):
        alerta = _parse_alert_item({"description": "Algo pasa"})
        assert alerta is not None
        assert alerta.nivel == "sin especificar"
        assert alerta.tipo == "sin especificar"

    def test_non_dict_item_is_discarded(self):
        assert _parse_alert_item("not a dict") is None  # type: ignore[arg-type]

    def test_unexpected_type_for_field_does_not_crash(self):
        """Si 'description' viene como dict anidado en vez de string, no debe tirar excepción."""
        alerta = _parse_alert_item({"description": {"nested": "weird"}})
        assert alerta is not None  # str({"nested": "weird"}) es válido, no crashea


# ---------------------------------------------------------------------------
# get_smn_alertas — integración con fetch + fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_smn_alertas_combines_both_types():
    al_payload = [{"level": "rojo", "phenomenon": "Tormenta", "description": "Tormenta severa"}]
    ac_payload = [{"level": "amarillo", "phenomenon": "Viento", "description": "Ráfagas fuertes"}]
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_AL_URL).mock(return_value=httpx.Response(200, json=al_payload))
        mock.get(_AC_URL).mock(return_value=httpx.Response(200, json=ac_payload))
        result = await get_smn_alertas()

    assert result.available is True
    assert len(result.alertas) == 2
    niveles = {a.nivel for a in result.alertas}
    assert niveles == {"rojo", "amarillo"}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_smn_alertas_both_endpoints_fail_returns_unavailable():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_AL_URL).mock(return_value=httpx.Response(503))
        mock.get(_AC_URL).mock(side_effect=httpx.TimeoutException("timeout"))
        result = await get_smn_alertas()

    assert result.available is False
    assert result.alertas == []


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_smn_alertas_partial_failure_still_available():
    """Si AL falla pero AC responde, seguimos mostrando lo que sí llegó."""
    ac_payload = [{"level": "amarillo", "phenomenon": "Viento", "description": "Ráfagas"}]
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_AL_URL).mock(return_value=httpx.Response(503))
        mock.get(_AC_URL).mock(return_value=httpx.Response(200, json=ac_payload))
        result = await get_smn_alertas()

    assert result.available is True
    assert len(result.alertas) == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_smn_alertas_malformed_item_is_skipped_not_fatal():
    al_payload = [
        {"level": "rojo", "description": "Alerta válida"},
        {"unexpected_shape": True},  # sin descripcion en ningún candidato → se descarta
    ]
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_AL_URL).mock(return_value=httpx.Response(200, json=al_payload))
        mock.get(_AC_URL).mock(return_value=httpx.Response(200, json=[]))
        result = await get_smn_alertas()

    assert result.available is True
    assert len(result.alertas) == 1
    assert result.alertas[0].descripcion == "Alerta válida"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_smn_alertas_uses_cache_on_second_call():
    al_payload = [{"level": "rojo", "description": "Alerta"}]
    with respx.mock(assert_all_called=False) as mock:
        route_al = mock.get(_AL_URL).mock(return_value=httpx.Response(200, json=al_payload))
        route_ac = mock.get(_AC_URL).mock(return_value=httpx.Response(200, json=[]))
        await get_smn_alertas()
        await get_smn_alertas()

    assert route_al.call_count == 1
    assert route_ac.call_count == 1
