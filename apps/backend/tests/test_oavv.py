"""Tests unitarios para app.services.oavv."""
from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from app.schemas.volcanes import AlertLevel, VolcanesResponse, Volcan
from app.services.oavv import (
    _detect_alert_level,
    _fetch_alert_image,
    _fetch_all_volcanes,
    get_volcanes,
)


# ---------------------------------------------------------------------------
# Helpers de imagen
# ---------------------------------------------------------------------------

def _make_png(r: int, g: int, b: int, width: int = 200, height: int = 100) -> bytes:
    """Crea un PNG sólido del color dado, suficientemente grande para el sampler."""
    img = Image.new("RGB", (width, height), (r, g, b))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# Colores calibrados según los umbrales de _detect_alert_level
_GREEN_PNG  = _make_png(148, 205, 126)   # G dominante → verde
_YELLOW_PNG = _make_png(255, 220, 100)   # R>200, G>180, B<130 → amarillo
_ORANGE_PNG = _make_png(210, 130, 70)    # R>200, G<150, B<90 → naranja
_RED_PNG    = _make_png(240, 60, 50)     # R>220, G<80 → rojo


# ---------------------------------------------------------------------------
# _detect_alert_level — función pura
# ---------------------------------------------------------------------------

class TestDetectAlertLevel:

    def test_green_image_returns_verde(self):
        assert _detect_alert_level(_GREEN_PNG) == "verde"

    def test_yellow_image_returns_amarillo(self):
        assert _detect_alert_level(_YELLOW_PNG) == "amarillo"

    def test_orange_image_returns_naranja(self):
        assert _detect_alert_level(_ORANGE_PNG) == "naranja"

    def test_red_image_returns_rojo(self):
        assert _detect_alert_level(_RED_PNG) == "rojo"

    def test_corrupt_bytes_returns_verde(self):
        """Bytes no válidos → excepción interna → degradación a verde."""
        result = _detect_alert_level(b"not a png")
        assert result == "verde"

    def test_empty_bytes_returns_verde(self):
        result = _detect_alert_level(b"")
        assert result == "verde"

    def test_zero_width_image_returns_verde(self):
        """Imagen degenerada 0×100 no crashea — retorna verde."""
        # PIL no acepta 0 en dimensiones — generamos imagen muy pequeña (1×1)
        img = Image.new("RGB", (1, 1), (148, 205, 126))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        result = _detect_alert_level(buf.getvalue())
        assert result == "verde"

    def test_returns_valid_alert_level(self):
        valid = {"verde", "amarillo", "naranja", "rojo"}
        for png in [_GREEN_PNG, _YELLOW_PNG, _ORANGE_PNG, _RED_PNG]:
            assert _detect_alert_level(png) in valid

    def test_red_threshold_r220_g80(self):
        """Rojo exacto en el límite: R=221, G=79."""
        png = _make_png(221, 79, 50)
        assert _detect_alert_level(png) == "rojo"

    def test_not_red_when_g_not_below_80(self):
        """R>220 pero G>=80 → no debe ser rojo."""
        png = _make_png(240, 80, 50)   # g=80, no < 80
        result = _detect_alert_level(png)
        assert result != "rojo"


# ---------------------------------------------------------------------------
# _fetch_alert_image — función async con cliente inyectado
# ---------------------------------------------------------------------------

class TestFetchAlertImage:

    @pytest.mark.asyncio
    async def test_returns_content_on_success(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = _GREEN_PNG

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        result = await _fetch_alert_image(mock_client, volcan_id=2)

        assert result == _GREEN_PNG

    @pytest.mark.asyncio
    async def test_passes_correct_id_param(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = _GREEN_PNG

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        await _fetch_alert_image(mock_client, volcan_id=15)

        call_kwargs = mock_client.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params", {})
        assert params.get("id") == 15

    @pytest.mark.asyncio
    async def test_raises_on_http_error(self):
        from httpx import HTTPStatusError, Response
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 404

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=HTTPStatusError("404", request=MagicMock(), response=mock_response)
        )

        with pytest.raises(HTTPStatusError):
            await _fetch_alert_image(mock_client, volcan_id=99)


# ---------------------------------------------------------------------------
# _fetch_all_volcanes — fetcha en paralelo y maneja errores individuales
# ---------------------------------------------------------------------------

class TestFetchAllVolcanes:

    @pytest.mark.asyncio
    async def test_returns_list_of_volcan(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = _GREEN_PNG

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.services.oavv.get_client", return_value=mock_client):
            result = await _fetch_all_volcanes()

        assert isinstance(result, list)
        assert all(isinstance(v, Volcan) for v in result)

    @pytest.mark.asyncio
    async def test_count_matches_catalog(self):
        from app.services.oavv import _CATALOG

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = _GREEN_PNG

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.services.oavv.get_client", return_value=mock_client):
            result = await _fetch_all_volcanes()

        assert len(result) == len(_CATALOG)

    @pytest.mark.asyncio
    async def test_failed_image_degrades_to_verde(self):
        """Ante error en una imagen, el volcán queda en nivel verde (no falla todo)."""
        from httpx import TimeoutException

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=TimeoutException("timeout"))

        with patch("app.services.oavv.get_client", return_value=mock_client):
            result = await _fetch_all_volcanes()

        assert all(v.alert_level == "verde" for v in result)

    @pytest.mark.asyncio
    async def test_alert_color_hex_matches_level(self):
        from app.schemas.volcanes import ALERT_HEX

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = _GREEN_PNG

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.services.oavv.get_client", return_value=mock_client):
            result = await _fetch_all_volcanes()

        for v in result:
            assert v.alert_color_hex == ALERT_HEX[v.alert_level]

    @pytest.mark.asyncio
    async def test_segemar_url_contains_slug(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = _GREEN_PNG

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.services.oavv.get_client", return_value=mock_client):
            result = await _fetch_all_volcanes()

        for v in result:
            assert "oavv.segemar.gob.ar" in v.segemar_url

    @pytest.mark.asyncio
    async def test_rojo_detected_when_image_is_red(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = _RED_PNG

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.services.oavv.get_client", return_value=mock_client):
            result = await _fetch_all_volcanes()

        assert all(v.alert_level == "rojo" for v in result)


# ---------------------------------------------------------------------------
# get_volcanes — punto de entrada público con caché
# ---------------------------------------------------------------------------

class TestGetVolcanes:

    @pytest.mark.asyncio
    async def test_returns_volcanes_response(self):
        import app.services.oavv as oavv_module
        oavv_module._volcanes_cache.clear()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = _GREEN_PNG

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.services.oavv.get_client", return_value=mock_client):
            result = await get_volcanes()

        assert isinstance(result, VolcanesResponse)

    @pytest.mark.asyncio
    async def test_total_matches_catalog(self):
        from app.services.oavv import _CATALOG
        import app.services.oavv as oavv_module
        oavv_module._volcanes_cache.clear()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = _GREEN_PNG

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.services.oavv.get_client", return_value=mock_client):
            result = await get_volcanes()

        assert result.total == len(_CATALOG)

    @pytest.mark.asyncio
    async def test_has_active_alert_false_when_all_verde(self):
        import app.services.oavv as oavv_module
        oavv_module._volcanes_cache.clear()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = _GREEN_PNG

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.services.oavv.get_client", return_value=mock_client):
            result = await get_volcanes()

        assert result.has_active_alert is False

    @pytest.mark.asyncio
    async def test_has_active_alert_true_when_rojo(self):
        import app.services.oavv as oavv_module
        oavv_module._volcanes_cache.clear()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = _RED_PNG

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.services.oavv.get_client", return_value=mock_client):
            result = await get_volcanes()

        assert result.has_active_alert is True

    @pytest.mark.asyncio
    async def test_cache_hit_skips_http_calls(self):
        """Segunda llamada sin limpiar caché → no hace requests HTTP."""
        import app.services.oavv as oavv_module
        oavv_module._volcanes_cache.clear()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = _GREEN_PNG

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.services.oavv.get_client", return_value=mock_client):
            await get_volcanes()           # primera llamada → fetchea
            call_count_after_first = mock_client.get.call_count
            await get_volcanes()           # segunda → debe usar caché

        assert mock_client.get.call_count == call_count_after_first

    @pytest.mark.asyncio
    async def test_response_has_volcanes_list(self):
        import app.services.oavv as oavv_module
        oavv_module._volcanes_cache.clear()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = _GREEN_PNG

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.services.oavv.get_client", return_value=mock_client):
            result = await get_volcanes()

        assert len(result.volcanes) > 0
        assert all(isinstance(v, Volcan) for v in result.volcanes)
