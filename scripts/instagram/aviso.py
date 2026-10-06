"""Windows toast notification through PowerShell (nothing to install).

The script travels with ``-EncodedCommand`` (UTF-16LE base64) so quotes and accents in the text can
never break the command line. The runner is injectable: tests never fire a real notification, and a
failure only logs a warning (the report itself must not break because a toast did not show).
"""

from __future__ import annotations

import base64
import logging
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from xml.sax.saxutils import escape

from reglas import VARIANT_LABEL

logger = logging.getLogger(__name__)

Runner = Callable[[Sequence[str]], int]

# AppUserModelID of Windows PowerShell: it is registered on every Windows, so the toast shows
# without creating a shortcut or registering anything.
_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
_POWERSHELL = "powershell.exe"
_TIMEOUT_SECONDS = 30
# PowerShell also treats the typographic quotes as single quotes: all of them get doubled.
_PS_QUOTES = ("'", "‘", "’", "‚", "‛")


@dataclass(frozen=True)
class CityResult:
    """What happened to one city, for the notice text."""

    city_name: str
    variante: str
    plate_written: bool


def _ps_literal(text: str) -> str:
    """Body of a single-quoted PowerShell string: nothing inside is interpreted."""
    for quote in _PS_QUOTES:
        text = text.replace(quote, quote * 2)
    return text


def build_toast_script(title: str, body: str) -> str:
    """PowerShell that shows a toast with `title` and `body`."""
    xml = (
        '<toast><visual><binding template="ToastGeneric">'
        f"<text>{escape(title)}</text><text>{escape(body)}</text>"
        "</binding></visual></toast>"
    )
    return "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications,"
            " ContentType = WindowsRuntime] | Out-Null",
            "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument,"
            " ContentType = WindowsRuntime] | Out-Null",
            "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument",
            f"$xml.LoadXml('{_ps_literal(xml)}')",
            "$toast = New-Object Windows.UI.Notifications.ToastNotification $xml",
            "[Windows.UI.Notifications.ToastNotificationManager]"
            f"::CreateToastNotifier('{_APP_ID}').Show($toast)",
        ]
    )


def encode_command(script: str) -> str:
    """The value of ``powershell -EncodedCommand``: base64 of the UTF-16LE script."""
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def _run_powershell(argv: Sequence[str]) -> int:
    """Real runner: returns the exit code (raises OSError / TimeoutExpired)."""
    completed = subprocess.run(  # nosec B603 - fixed executable, no shell, text encoded in base64
        list(argv), capture_output=True, timeout=_TIMEOUT_SECONDS, check=False
    )
    return completed.returncode


def notify(title: str, body: str, *, runner: Runner | None = None) -> bool:
    """Show a Windows notification. True when PowerShell exited 0; never raises on failure."""
    run = runner if runner is not None else _run_powershell
    argv = [
        _POWERSHELL,
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-EncodedCommand",
        encode_command(build_toast_script(title, body)),
    ]
    try:
        code = run(argv)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Windows notification failed: %s", exc)
        return False
    if code != 0:
        logger.warning("Windows notification failed: powershell exited with code %s", code)
        return False
    return True


def build_notice(
    target: date, today: date, results: Sequence[CityResult], *, total_cities: int
) -> tuple[str, str]:
    """Title and body of the notification: plate count and the variant of each city."""
    when = {0: "de hoy", 1: "de mañana", 2: "de pasado mañana"}.get((target - today).days)
    title = f"SkyPulse: reporte {when or target.strftime('del %d/%m')} listo"
    written = sum(result.plate_written for result in results)
    noun = "placa" if total_cities == 1 else "placas"
    count = f"{written} {noun}" if written == total_cities else f"{written} de {total_cities} {noun}"
    cities = ", ".join(f"{r.city_name} ({VARIANT_LABEL[r.variante]})" for r in results)
    return title, f"{count}: {cities}"
