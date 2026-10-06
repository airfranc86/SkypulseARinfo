"""Shared pytest setup for the Instagram report scripts.

Makes the flat modules of ``scripts/instagram`` and the backend (``apps/backend``) importable, and
guarantees that no test can ever fire a real Windows notification or start a real browser (except
the ones marked ``navegador``).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PACKAGE_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = PACKAGE_DIR.parents[1] / "apps" / "backend"

for _path in (PACKAGE_DIR, BACKEND_DIR, Path(__file__).resolve().parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


@pytest.fixture(autouse=True)
def _block_real_notifications(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any test that reaches the real PowerShell runner fails loudly instead of notifying."""
    import aviso

    def _forbidden(argv: object) -> int:
        raise AssertionError(f"a test tried to fire a real notification: {argv!r}")

    monkeypatch.setattr(aviso, "_run_powershell", _forbidden)


@pytest.fixture(autouse=True)
def _block_real_browser(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Only tests marked ``navegador`` may start Chrome or Edge; any other one fails loudly."""
    if request.node.get_closest_marker("navegador") is not None:
        return
    import navegador

    def _forbidden(argv: object, timeout: float) -> object:
        raise AssertionError(f"a test tried to start a real browser without @pytest.mark.navegador: {argv!r}")

    monkeypatch.setattr(navegador, "_run_subprocess", _forbidden)
