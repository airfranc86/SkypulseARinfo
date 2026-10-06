"""FRA-343 — si OAVV falla, el volcán queda en "sin_datos" (nunca en "verde").

Antes, un volcán cuya imagen de alerta no se podía descargar o interpretar se
mostraba como "verde": un falso negativo en una alerta de seguridad. Estos tests
fijan el contrato nuevo de ``GET /api/volcanes``:

- cada volcán sin dato lleva ``alert_level == "sin_datos"`` y un color neutro;
- ``available`` es False si falló al menos un volcán;
- ``total`` y ``has_active_alert`` cuentan solo volcanes con dato;
- un resultado con fallos se cachea con un TTL corto para recuperarse rápido.

Todo el tráfico HTTP se intercepta con respx: no hay llamadas reales a OAVV.
"""
from __future__ import annotations

import io

import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient
from PIL import Image

import app.services.oavv as oavv_module
from app.core.config import settings
from app.main import app
from app.schemas.volcanes import ALERT_HEX
from app.services.oavv import _CATALOG, get_volcanes

_ALERT_URL = "https://oavv.segemar.gob.ar/scripts/show_alerta.php"
_ALL_IDS = [entry["id"] for entry in _CATALOG]


def _make_png(rgb: tuple[int, int, int], width: int = 200, height: int = 100) -> bytes:
    img = Image.new("RGB", (width, height), rgb)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


_GREEN_PNG = _make_png((148, 205, 126))
_RED_PNG = _make_png((240, 60, 50))
_YELLOW_PNG = _make_png((255, 220, 100))
# Fondo gris neutro: la imagen llegó pero no muestra ninguna banda de alerta reconocible.
_GRAY_PNG = _make_png((128, 128, 128))


def _route(mock: respx.MockRouter, responses: dict[int, httpx.Response | Exception]) -> None:
    """Responde cada id del catálogo con lo indicado (por defecto, imagen verde)."""

    def _handler(request: httpx.Request) -> httpx.Response:
        volcan_id = int(request.url.params["id"])
        outcome = responses.get(volcan_id, httpx.Response(200, content=_GREEN_PNG))
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    mock.get(_ALERT_URL).mock(side_effect=_handler)


@pytest.fixture(autouse=True)
def _clear_volcanes_cache():
    oavv_module._volcanes_cache.clear()
    yield
    oavv_module._volcanes_cache.clear()


def _by_id(response) -> dict[int, object]:
    return {v.id: v for v in response.volcanes}


# ---------------------------------------------------------------------------
# Fuente sana: igual que antes, más available=True
# ---------------------------------------------------------------------------

class TestFuenteSana:

    @pytest.mark.asyncio
    async def test_niveles_detectados_y_available_true(self):
        with respx.mock(assert_all_called=False) as mock:
            _route(mock, {2: httpx.Response(200, content=_RED_PNG), 1: httpx.Response(200, content=_YELLOW_PNG)})
            result = await get_volcanes()

        volcanes = _by_id(result)
        assert result.available is True
        assert volcanes[2].alert_level == "rojo"
        assert volcanes[1].alert_level == "amarillo"
        assert volcanes[3].alert_level == "verde"
        assert result.total == len(_CATALOG)
        assert result.has_active_alert is True

    @pytest.mark.asyncio
    async def test_todo_verde_sin_alerta(self):
        with respx.mock(assert_all_called=False) as mock:
            _route(mock, {})
            result = await get_volcanes()

        assert result.available is True
        assert result.has_active_alert is False
        assert all(v.alert_level == "verde" for v in result.volcanes)


# ---------------------------------------------------------------------------
# Fuente caída para todos
# ---------------------------------------------------------------------------

class TestFuenteCaida:

    @pytest.mark.asyncio
    async def test_error_de_conexion_deja_todos_sin_datos(self):
        failures = {i: httpx.ConnectError("connection reset") for i in _ALL_IDS}
        with respx.mock(assert_all_called=False) as mock:
            _route(mock, failures)
            result = await get_volcanes()

        assert all(v.alert_level == "sin_datos" for v in result.volcanes)
        assert result.available is False
        assert result.has_active_alert is False
        assert result.total == 0
        assert len(result.volcanes) == len(_CATALOG)

    @pytest.mark.asyncio
    async def test_http_5xx_deja_todos_sin_datos(self):
        failures = {i: httpx.Response(503) for i in _ALL_IDS}
        with respx.mock(assert_all_called=False) as mock:
            _route(mock, failures)
            result = await get_volcanes()

        assert all(v.alert_level == "sin_datos" for v in result.volcanes)
        assert result.available is False
        assert result.has_active_alert is False

    @pytest.mark.asyncio
    async def test_sin_datos_usa_color_neutro_distinto_del_verde(self):
        failures = {i: httpx.ConnectError("down") for i in _ALL_IDS}
        with respx.mock(assert_all_called=False) as mock:
            _route(mock, failures)
            result = await get_volcanes()

        hexes = {v.alert_color_hex for v in result.volcanes}
        assert hexes == {ALERT_HEX["sin_datos"]}
        assert ALERT_HEX["sin_datos"] not in {ALERT_HEX[lvl] for lvl in ("verde", "amarillo", "naranja", "rojo")}

    @pytest.mark.asyncio
    async def test_endpoint_http_expone_available_y_sin_datos(self):
        failures = {i: httpx.ConnectError("down") for i in _ALL_IDS}
        with respx.mock(assert_all_called=False) as mock:
            _route(mock, failures)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/volcanes")

        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is False
        assert body["has_active_alert"] is False
        assert {v["alert_level"] for v in body["volcanes"]} == {"sin_datos"}
        # Los campos existentes siguen presentes (contrato compatible).
        assert {"total", "has_active_alert", "volcanes"} <= set(body)


# ---------------------------------------------------------------------------
# Fallo parcial
# ---------------------------------------------------------------------------

class TestFalloParcial:

    @pytest.mark.asyncio
    async def test_solo_los_afectados_quedan_sin_datos(self):
        failures = {
            2: httpx.ConnectError("reset"),
            15: httpx.Response(500),
            1: httpx.Response(200, content=_YELLOW_PNG),
        }
        with respx.mock(assert_all_called=False) as mock:
            _route(mock, failures)
            result = await get_volcanes()

        volcanes = _by_id(result)
        assert volcanes[2].alert_level == "sin_datos"
        assert volcanes[15].alert_level == "sin_datos"
        assert volcanes[1].alert_level == "amarillo"
        assert volcanes[3].alert_level == "verde"
        assert result.available is False
        assert result.total == len(_CATALOG) - 2

    @pytest.mark.asyncio
    async def test_rojo_con_dato_y_otros_caidos_sigue_siendo_alerta(self):
        failures = {i: httpx.ConnectError("down") for i in _ALL_IDS if i != 2}
        failures[2] = httpx.Response(200, content=_RED_PNG)
        with respx.mock(assert_all_called=False) as mock:
            _route(mock, failures)
            result = await get_volcanes()

        assert _by_id(result)[2].alert_level == "rojo"
        assert result.has_active_alert is True
        assert result.available is False
        assert result.total == 1

    @pytest.mark.asyncio
    async def test_sin_datos_no_cuenta_como_alerta(self):
        failures = {2: httpx.ConnectError("down")}
        with respx.mock(assert_all_called=False) as mock:
            _route(mock, failures)
            result = await get_volcanes()

        assert result.has_active_alert is False


# ---------------------------------------------------------------------------
# Imagen que llega pero no se puede interpretar
# ---------------------------------------------------------------------------

class TestImagenIlegible:

    @pytest.mark.asyncio
    async def test_bytes_que_no_son_imagen_dan_sin_datos(self):
        failures = {2: httpx.Response(200, content=b"<html>error</html>")}
        with respx.mock(assert_all_called=False) as mock:
            _route(mock, failures)
            result = await get_volcanes()

        assert _by_id(result)[2].alert_level == "sin_datos"
        assert result.available is False

    @pytest.mark.asyncio
    async def test_imagen_sin_banda_reconocible_da_sin_datos(self):
        failures = {2: httpx.Response(200, content=_GRAY_PNG)}
        with respx.mock(assert_all_called=False) as mock:
            _route(mock, failures)
            result = await get_volcanes()

        assert _by_id(result)[2].alert_level == "sin_datos"

    def test_detector_puro_no_devuelve_verde_ante_basura(self):
        assert oavv_module._detect_alert_level(b"not a png") == "sin_datos"
        assert oavv_module._detect_alert_level(b"") == "sin_datos"
        assert oavv_module._detect_alert_level(_GRAY_PNG) == "sin_datos"
        assert oavv_module._detect_alert_level(_GREEN_PNG) == "verde"


# ---------------------------------------------------------------------------
# Caché: TTL corto con fallos, normal sin fallos
# ---------------------------------------------------------------------------

class _FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


class TestCacheTtl:

    def test_ttl_corto_es_una_constante_menor_que_el_normal(self):
        assert oavv_module.PARTIAL_CACHE_TTL_SECONDS == 60
        assert oavv_module.PARTIAL_CACHE_TTL_SECONDS < settings.cache_ttl_volcanes_seconds

    @pytest.mark.asyncio
    async def test_resultado_con_fallos_expira_rapido(self, monkeypatch):
        clock = _FakeClock()
        monkeypatch.setattr(oavv_module, "_now", clock)
        failures = {i: httpx.ConnectError("down") for i in _ALL_IDS}

        with respx.mock(assert_all_called=False) as mock:
            _route(mock, failures)
            first = await get_volcanes()
            assert first.available is False

            # Dentro del TTL corto: usa la caché, no vuelve a pedir.
            calls_after_first = mock.calls.call_count
            clock.now += oavv_module.PARTIAL_CACHE_TTL_SECONDS - 1
            await get_volcanes()
            assert mock.calls.call_count == calls_after_first

        # Pasado el TTL corto, la fuente volvió: se recupera.
        clock.now += 2
        with respx.mock(assert_all_called=False) as mock:
            _route(mock, {})
            recovered = await get_volcanes()

        assert recovered.available is True
        assert all(v.alert_level == "verde" for v in recovered.volcanes)

    @pytest.mark.asyncio
    async def test_resultado_completo_usa_el_ttl_normal(self, monkeypatch):
        clock = _FakeClock()
        monkeypatch.setattr(oavv_module, "_now", clock)

        with respx.mock(assert_all_called=False) as mock:
            _route(mock, {})
            await get_volcanes()
            calls_after_first = mock.calls.call_count

            clock.now += oavv_module.PARTIAL_CACHE_TTL_SECONDS + 10
            await get_volcanes()
            assert mock.calls.call_count == calls_after_first

            clock.now += settings.cache_ttl_volcanes_seconds
            await get_volcanes()
            assert mock.calls.call_count == calls_after_first * 2
