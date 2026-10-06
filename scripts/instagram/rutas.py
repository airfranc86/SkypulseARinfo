"""Folder layout, file names and atomic writes of the daily report and of the night notice.

Layout: ``<root>/SkyPulse_Instagram_Reports/AAAA/MM_Mes/Semana_NN/`` where the year is the calendar
year of the FORECAST day and the week is its ISO week (the 6th of October 2026 is week 41). Around
New Year the ISO week can belong to the other year: 2027-01-01 lives in ``2027/01_Enero/Semana_53``.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from datetime import date
from pathlib import Path

from fechas import MONTH_NAMES
from reglas import VARIANT_LABEL, Variante

ROOT_FOLDER = "SkyPulse_Instagram_Reports"


def day_folder(root: Path, day: date) -> Path:
    """Folder of the forecast day under `root` (not created here)."""
    month = f"{day.month:02d}_{MONTH_NAMES[day.month - 1].capitalize()}"
    week = f"Semana_{day.isocalendar().week:02d}"
    return root / ROOT_FOLDER / str(day.year) / month / week


def plate_name(day: date, variant: Variante, slug: str) -> str:
    """``AAAA-MM-DD_Reporte_<Alerta|Estandar>_<slug>.png`` (the date is the forecast day)."""
    if variant not in VARIANT_LABEL:
        raise ValueError(f"unknown variant {variant!r}: expected one of {sorted(VARIANT_LABEL)}")
    return f"{day.isoformat()}_Reporte_{variant}_{slug}.png"


def caption_name(day: date) -> str:
    return f"{day.isoformat()}_Caption_Instagram.txt"


def night_plate_name(day: date, slug: str) -> str:
    """``AAAA-MM-DD_Aviso_Nocturno_<slug>.png``: never the name of a report plate."""
    return f"{day.isoformat()}_Aviso_Nocturno_{slug}.png"


def night_caption_name(day: date) -> str:
    return f"{day.isoformat()}_Caption_Aviso_Nocturno.txt"


def write_atomic(path: Path, content: bytes) -> Path:
    """Write `content` to `path` through a temp file in the same folder, then rename over it.

    The destination is either the old file or the complete new one, never a partial write; running
    again simply overwrites. Folders are created. The temp file is removed if anything fails.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f"{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_name)
        raise
    return path


def write_caption(root: Path, day: date, text: str) -> Path:
    """Write the caption (UTF-8) in the folder of the forecast day."""
    return write_atomic(day_folder(root, day) / caption_name(day), text.encode("utf-8"))


def write_plate(root: Path, day: date, variant: Variante, slug: str, png: bytes) -> Path:
    """Write one PNG plate in the folder of the forecast day."""
    return write_atomic(day_folder(root, day) / plate_name(day, variant, slug), png)


def write_night_caption(root: Path, day: date, text: str) -> Path:
    """Write the night-notice caption (UTF-8) in the folder of the forecast day."""
    return write_atomic(day_folder(root, day) / night_caption_name(day), text.encode("utf-8"))


def write_night_plate(root: Path, day: date, slug: str, png: bytes) -> Path:
    """Write one night-notice PNG plate in the folder of the forecast day."""
    return write_atomic(day_folder(root, day) / night_plate_name(day, slug), png)
