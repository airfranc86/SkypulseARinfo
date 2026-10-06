"""Local configuration: optional roots, clear errors, no personal data in the repo."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from config import DEFAULT_CONFIG_PATH, ConfigError, load_config

PACKAGE_DIR = Path(__file__).resolve().parents[1]


def write_config(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "config.local.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_both_roots_in_order_drive_then_backup(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_config(tmp_path, {"drive_dir": str(tmp_path / "drive"), "backup_dir": str(tmp_path / "bk")})
    config = load_config(path)
    assert config.roots == (tmp_path / "drive", tmp_path / "bk")
    assert capsys.readouterr().err == ""


def test_drive_dir_is_optional_and_silent_when_the_backup_is_set(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = load_config(write_config(tmp_path, {"backup_dir": str(tmp_path / "bk")}))
    assert config.roots == (tmp_path / "bk",)
    assert capsys.readouterr().err == ""  # the user syncs the backup folder with Drive: nothing to warn


def test_backup_dir_is_optional_and_silent_when_drive_is_set(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = load_config(write_config(tmp_path, {"drive_dir": str(tmp_path / "drive")}))
    assert config.roots == (tmp_path / "drive",)
    assert capsys.readouterr().err == ""


def test_the_same_folder_twice_is_one_destination(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    same = str(tmp_path / "otra" / ".." / "Instagram")
    config = load_config(write_config(tmp_path, {"drive_dir": str(tmp_path / "Instagram"), "backup_dir": same}))
    assert config.roots == (tmp_path / "Instagram",)
    assert capsys.readouterr().err == ""


def test_different_folders_stay_two_destinations(tmp_path: Path) -> None:
    config = load_config(write_config(tmp_path, {"drive_dir": str(tmp_path / "a"), "backup_dir": str(tmp_path / "b")}))
    assert len(config.roots) == 2


@pytest.mark.parametrize("empty", ["", "   ", None])
def test_empty_values_count_as_missing(tmp_path: Path, empty: object) -> None:
    config = load_config(write_config(tmp_path, {"drive_dir": empty, "backup_dir": str(tmp_path / "bk")}))
    assert config.roots == (tmp_path / "bk",)


def test_both_missing_is_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="drive_dir.*backup_dir"):
        load_config(write_config(tmp_path, {"drive_dir": "", "backup_dir": ""}))
    with pytest.raises(ConfigError, match="drive_dir.*backup_dir"):
        load_config(write_config(tmp_path, {}))


def test_missing_file_points_to_the_example(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"config\.example\.json"):
        load_config(tmp_path / "nope.json")


def test_invalid_json_is_a_config_error(tmp_path: Path) -> None:
    path = tmp_path / "config.local.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="JSON"):
        load_config(path)


@pytest.mark.parametrize("payload", [[], "texto", 3])
def test_top_level_must_be_an_object(tmp_path: Path, payload: object) -> None:
    with pytest.raises(ConfigError, match="objeto"):
        load_config(write_config(tmp_path, payload))


def test_a_non_string_path_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="backup_dir"):
        load_config(write_config(tmp_path, {"backup_dir": 42, "drive_dir": ""}))


def test_the_default_path_is_the_local_file_next_to_the_scripts() -> None:
    assert DEFAULT_CONFIG_PATH == PACKAGE_DIR / "config.local.json"


def test_example_config_is_valid_and_has_no_personal_data() -> None:
    example = json.loads((PACKAGE_DIR / "config.example.json").read_text(encoding="utf-8"))
    # drive_dir is optional (the backup folder is the one synchronised with Drive) and personal: not in the example
    assert example == {"backup_dir": r"G:\Developer\AgenciaAssests\MARKETING\SkyPulse\Instagram"}


def test_local_config_and_output_are_gitignored() -> None:
    lines = (PACKAGE_DIR / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert {"config.local.json", "salida/", "__pycache__/"} <= set(lines)
