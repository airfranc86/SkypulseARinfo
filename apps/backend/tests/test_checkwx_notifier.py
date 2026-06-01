"""Tests del notifier de umbrales CheckWX.

N1 — count=159 (80%) primera vez → emite alerta Sentry, flag seteada
N2 — count=162, flag 80% ya enviada → NO emite segunda alerta (dedup)
N3 — count=189 (95%) → emite alerta 95, level="error"
N4 — count=50 (25%) → ningún umbral → sin alerta

Cálculo de umbrales: int(count * 100 / 198)
  80% → count >= 159  (158 → int(79.79) = 79, no cruza)
  95% → count >= 189  (188 → int(94.94) = 94, no cruza)
 100% → count >= 198
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.counter import MemoryCounter
from app.core.notifier import maybe_notify

_LIMIT = 198
_CYCLE = "2026-06"


@pytest.fixture
def counter() -> MemoryCounter:
    return MemoryCounter()


# ---------------------------------------------------------------------------
# N1 — primer cruce de 80%
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_n1_alert_emitted_at_80_percent(counter: MemoryCounter):
    with patch("app.core.notifier.sentry_sdk") as mock_sentry:
        await maybe_notify(_CYCLE, 159, counter, _LIMIT)

    mock_sentry.capture_message.assert_called_once()
    call_args = mock_sentry.capture_message.call_args
    assert "80" in call_args[0][0]
    assert call_args[1]["level"] == "warning"


@pytest.mark.asyncio
async def test_n1_flag_set_after_alert(counter: MemoryCounter):
    with patch("app.core.notifier.sentry_sdk"):
        await maybe_notify(_CYCLE, 159, counter, _LIMIT)

    assert await counter.alert_already_sent(_CYCLE, 80) is True


# ---------------------------------------------------------------------------
# N2 — dedup: segunda llamada con flag ya seteada
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_n2_no_duplicate_alert(counter: MemoryCounter):
    """Cuando el flag 80% ya está seteado, no se emite segunda alerta."""
    with patch("app.core.notifier.sentry_sdk") as mock_sentry:
        await maybe_notify(_CYCLE, 159, counter, _LIMIT)  # primera — emite
        await maybe_notify(_CYCLE, 162, counter, _LIMIT)  # segunda — dedup

    assert mock_sentry.capture_message.call_count == 1


# ---------------------------------------------------------------------------
# N3 — cruce de 95%
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_n3_alert_level_error_at_95_percent(counter: MemoryCounter):
    # Marcar 80% como ya enviado; la alerta nueva debe ser 95%
    await counter.mark_alert_sent(_CYCLE, 80, 86400)

    with patch("app.core.notifier.sentry_sdk") as mock_sentry:
        await maybe_notify(_CYCLE, 189, counter, _LIMIT)

    call_args = mock_sentry.capture_message.call_args
    assert call_args[1]["level"] == "error"
    assert "95" in call_args[0][0]


# ---------------------------------------------------------------------------
# N4 — bajo el umbral → sin alerta
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_n4_no_alert_below_threshold(counter: MemoryCounter):
    with patch("app.core.notifier.sentry_sdk") as mock_sentry:
        await maybe_notify(_CYCLE, 50, counter, _LIMIT)  # 25%

    mock_sentry.capture_message.assert_not_called()


# ---------------------------------------------------------------------------
# Tags Sentry correctos
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sentry_tags_correct(counter: MemoryCounter):
    with patch("app.core.notifier.sentry_sdk") as mock_sentry:
        await maybe_notify(_CYCLE, 159, counter, _LIMIT)

    # El scope se obtiene del context manager: push_scope().__enter__()
    scope = mock_sentry.push_scope.return_value.__enter__.return_value
    scope.set_tag.assert_any_call("alert_kind", "checkwx_quota")
    scope.set_tag.assert_any_call("alert_threshold", "80")
    scope.set_tag.assert_any_call("cycle", _CYCLE)
