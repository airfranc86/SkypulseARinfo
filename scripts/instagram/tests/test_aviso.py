"""Windows notification: command construction, graceful degradation, notice text."""

from __future__ import annotations

import base64
import logging
import subprocess
from collections.abc import Sequence
from datetime import date

import pytest

from aviso import CityResult, build_notice, encode_command, notify

TITLE = "SkyPulse: reporte de mañana listo"


class FakeRunner:
    """Records the argv it receives and returns a fixed exit code (never touches Windows)."""

    def __init__(self, code: int = 0, error: Exception | None = None) -> None:
        self.calls: list[list[str]] = []
        self._code = code
        self._error = error

    def __call__(self, argv: Sequence[str]) -> int:
        self.calls.append(list(argv))
        if self._error is not None:
            raise self._error
        return self._code


def decode(argv: Sequence[str]) -> str:
    encoded = argv[list(argv).index("-EncodedCommand") + 1]
    return base64.b64decode(encoded).decode("utf-16-le")


def test_notify_sends_an_encoded_command_with_title_and_body() -> None:
    runner = FakeRunner()
    assert notify(TITLE, "3 placas: Córdoba (Alerta)", runner=runner) is True
    assert len(runner.calls) == 1
    argv = runner.calls[0]
    assert argv[0].lower().startswith("powershell")
    assert "-NoProfile" in argv
    script = decode(argv)
    assert "Windows.UI.Notifications" in script
    assert TITLE in script
    assert "3 placas: Córdoba (Alerta)" in script


def test_encode_command_is_utf16le_base64() -> None:
    encoded = encode_command("Write-Output 'ñ'")
    assert base64.b64decode(encoded).decode("utf-16-le") == "Write-Output 'ñ'"


def test_special_characters_cannot_break_the_script() -> None:
    runner = FakeRunner()
    notify("a <b> & 'c'", 'x "y" $z `w`', runner=runner)
    script = decode(runner.calls[0])
    assert "a &lt;b&gt; &amp; ''c''" in script  # XML-escaped, quote doubled for PowerShell
    assert "$z `w`" in script  # inert inside a single-quoted PowerShell string
    assert "<b>" not in script


def test_nonzero_exit_is_logged_and_returns_false(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        assert notify(TITLE, "body", runner=FakeRunner(code=1)) is False
    assert "notification" in caplog.text.lower()


@pytest.mark.parametrize(
    "error",
    [OSError("no powershell"), subprocess.TimeoutExpired(cmd="powershell", timeout=30)],
)
def test_runner_failures_never_propagate(error: Exception, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        assert notify(TITLE, "body", runner=FakeRunner(error=error)) is False
    assert caplog.records


def test_default_runner_is_blocked_by_the_suite_guard() -> None:
    # The autouse fixture replaces the real runner: reaching it must fail loudly, never notify.
    with pytest.raises(AssertionError, match="real notification"):
        notify(TITLE, "body")


# ---------------------------------------------------------------------------
# Notice text
# ---------------------------------------------------------------------------

RESULTS = (
    CityResult("Córdoba", "Estandar", plate_written=True),
    CityResult("Buenos Aires", "Alerta", plate_written=True),
    CityResult("Resistencia", "Estandar", plate_written=True),
)


def test_notice_for_tomorrow_lists_every_city_and_variant() -> None:
    title, body = build_notice(date(2026, 10, 7), date(2026, 10, 6), RESULTS, total_cities=3)
    assert title == TITLE
    assert body == "3 placas: Córdoba (Estándar), Buenos Aires (Alerta), Resistencia (Estándar)"


def test_notice_titles_for_other_days() -> None:
    day_after = build_notice(date(2026, 10, 8), date(2026, 10, 6), RESULTS, total_cities=3)[0]
    assert day_after == "SkyPulse: reporte de pasado mañana listo"
    other = build_notice(date(2026, 10, 10), date(2026, 10, 6), RESULTS, total_cities=3)[0]
    assert other == "SkyPulse: reporte del 10/10 listo"


def test_notice_counts_only_written_plates() -> None:
    results = (
        CityResult("Córdoba", "Estandar", plate_written=True),
        CityResult("Buenos Aires", "Alerta", plate_written=False),
    )
    _, body = build_notice(date(2026, 10, 7), date(2026, 10, 6), results, total_cities=3)
    assert body == "1 de 3 placas: Córdoba (Estándar), Buenos Aires (Alerta)"


def test_notice_with_no_plates_yet_is_honest() -> None:
    results = tuple(CityResult(r.city_name, r.variante, plate_written=False) for r in RESULTS)
    _, body = build_notice(date(2026, 10, 7), date(2026, 10, 6), results, total_cities=3)
    assert body.startswith("0 de 3 placas:")
