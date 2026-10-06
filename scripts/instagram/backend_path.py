"""Puts ``apps/backend`` on ``sys.path`` so the scripts reuse the backend forecast logic.

Importing this module is enough (the side effect is intentional and idempotent); the plates then
match the numbers of the web because they come from the same code.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "apps" / "backend"


def ensure_backend_on_path() -> Path:
    """Add the backend folder to ``sys.path`` once; fail clearly if it is not there."""
    if not (BACKEND_DIR / "app").is_dir():
        raise RuntimeError(f"No se encontró el backend en {BACKEND_DIR}")
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    return BACKEND_DIR


ensure_backend_on_path()
