"""Folder layout, file names and atomic idempotent writes."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

import rutas
from rutas import (
    ROOT_FOLDER,
    caption_name,
    day_folder,
    plate_name,
    write_atomic,
    write_caption,
    write_plate,
)

# ---------------------------------------------------------------------------
# Folder layout
# ---------------------------------------------------------------------------


def test_day_folder_for_the_first_report() -> None:
    folder = day_folder(Path("raiz"), date(2026, 10, 7))
    assert folder == Path("raiz") / ROOT_FOLDER / "2026" / "10_Octubre" / "Semana_41"


def test_iso_week_of_the_6th_of_october_is_41() -> None:
    assert day_folder(Path("r"), date(2026, 10, 6)).name == "Semana_41"


@pytest.mark.parametrize(
    ("month", "folder"),
    [
        (1, "01_Enero"), (2, "02_Febrero"), (3, "03_Marzo"), (4, "04_Abril"),
        (5, "05_Mayo"), (6, "06_Junio"), (7, "07_Julio"), (8, "08_Agosto"),
        (9, "09_Septiembre"), (10, "10_Octubre"), (11, "11_Noviembre"), (12, "12_Diciembre"),
    ],
)
def test_month_folders_are_spanish_and_numbered(month: int, folder: str) -> None:
    assert day_folder(Path("r"), date(2026, month, 15)).parent.name == folder


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 1, 5), "2026/01_Enero/Semana_02"),  # week number is zero padded
        (date(2026, 12, 31), "2026/12_Diciembre/Semana_53"),
        (date(2027, 1, 1), "2027/01_Enero/Semana_53"),  # ISO week of the old year, calendar year folder
        (date(2027, 1, 4), "2027/01_Enero/Semana_01"),
    ],
)
def test_year_end_and_padding(day: date, expected: str) -> None:
    assert day_folder(Path("r"), day) == Path("r") / ROOT_FOLDER / Path(expected)


# ---------------------------------------------------------------------------
# File names
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("variant", "slug", "expected"),
    [
        ("Alerta", "Cordoba", "2026-10-07_Reporte_Alerta_Cordoba.png"),
        ("Estandar", "CABA", "2026-10-07_Reporte_Estandar_CABA.png"),
        ("Estandar", "Resistencia", "2026-10-07_Reporte_Estandar_Resistencia.png"),
    ],
)
def test_plate_names(variant: str, slug: str, expected: str) -> None:
    assert plate_name(date(2026, 10, 7), variant, slug) == expected  # type: ignore[arg-type]


def test_plate_name_rejects_an_unknown_variant() -> None:
    with pytest.raises(ValueError, match="variant"):
        plate_name(date(2026, 10, 7), "Estándar", "CABA")  # type: ignore[arg-type]


def test_caption_name() -> None:
    assert caption_name(date(2026, 10, 7)) == "2026-10-07_Caption_Instagram.txt"
    assert caption_name(date(2027, 1, 1)) == "2027-01-01_Caption_Instagram.txt"


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def test_write_caption_creates_folders_and_writes_utf8(tmp_path: Path) -> None:
    text = "Pronóstico para mañana ⛈️ 💨\n"
    path = write_caption(tmp_path, date(2026, 10, 7), text)
    assert path == day_folder(tmp_path, date(2026, 10, 7)) / "2026-10-07_Caption_Instagram.txt"
    assert path.read_bytes() == text.encode("utf-8")
    assert path.read_text(encoding="utf-8") == text


def test_write_plate_writes_the_bytes_untouched(tmp_path: Path) -> None:
    png = b"\x89PNG\r\n\x1a\n" + bytes(range(256))
    path = write_plate(tmp_path, date(2026, 10, 7), "Alerta", "Cordoba", png)
    assert path.name == "2026-10-07_Reporte_Alerta_Cordoba.png"
    assert path.read_bytes() == png


def test_running_again_overwrites_instead_of_duplicating(tmp_path: Path) -> None:
    write_caption(tmp_path, date(2026, 10, 7), "primero\n")
    path = write_caption(tmp_path, date(2026, 10, 7), "segundo\n")
    assert path.read_text(encoding="utf-8") == "segundo\n"
    assert sorted(p.name for p in path.parent.iterdir()) == ["2026-10-07_Caption_Instagram.txt"]


def test_plate_variant_change_keeps_both_files(tmp_path: Path) -> None:
    write_plate(tmp_path, date(2026, 10, 7), "Estandar", "CABA", b"a")
    write_plate(tmp_path, date(2026, 10, 7), "Alerta", "CABA", b"b")
    names = sorted(p.name for p in day_folder(tmp_path, date(2026, 10, 7)).iterdir())
    assert names == ["2026-10-07_Reporte_Alerta_CABA.png", "2026-10-07_Reporte_Estandar_CABA.png"]


def test_failed_replace_keeps_the_old_file_and_leaves_no_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "out" / "file.txt"
    write_atomic(target, b"old")

    def broken_replace(src: object, dst: object) -> None:
        raise OSError("disk says no")

    with monkeypatch.context() as patch:
        patch.setattr(rutas.os, "replace", broken_replace)
        with pytest.raises(OSError, match="disk says no"):
            write_atomic(target, b"new")
    assert target.read_bytes() == b"old"
    assert [p.name for p in target.parent.iterdir()] == ["file.txt"]


def test_failed_write_never_creates_the_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "file.bin"

    def broken_fsync(fd: int) -> None:
        raise OSError("fsync failed")

    with monkeypatch.context() as patch:
        patch.setattr(rutas.os, "fsync", broken_fsync)
        with pytest.raises(OSError, match="fsync failed"):
            write_atomic(target, b"data")
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_write_atomic_uses_a_temp_file_in_the_same_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, str]] = []
    real_replace = os.replace

    def spy(src: str, dst: str) -> None:
        seen.append((str(Path(src).parent), str(Path(dst).parent)))
        real_replace(src, dst)

    monkeypatch.setattr(rutas.os, "replace", spy)
    write_atomic(tmp_path / "x.txt", b"x")
    assert seen == [(str(tmp_path), str(tmp_path))]
