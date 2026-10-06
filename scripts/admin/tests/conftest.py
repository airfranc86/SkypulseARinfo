"""Pytest bootstrap: make `scripts/admin` and `scripts/admin/tests` importable."""

from __future__ import annotations

import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_ADMIN_DIR = _TESTS_DIR.parent

for _path in (_ADMIN_DIR, _TESTS_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
