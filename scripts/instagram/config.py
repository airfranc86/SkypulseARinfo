"""Local configuration (``config.local.json``, git-ignored): where the daily report is saved.

Keys (both optional, at least one required):

- ``drive_dir``: the folder synchronised by Google Drive for desktop. Optional: when the backup
  folder is itself the one synchronised with Drive, it is simply left out.
- ``backup_dir``: local backup folder.

A missing key is skipped silently as long as there is at least one destination; with none the run
cannot save anything and fails with a clear error. Two keys pointing to the same folder (after
resolving it) are one destination, so every file is written once. No keys, secrets or personal paths
live in the repository.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.local.json"
_KEYS = ("drive_dir", "backup_dir")


class ConfigError(Exception):
    """The local configuration is missing, unreadable or invalid."""


@dataclass(frozen=True)
class Config:
    """Destination roots, in order: Drive first, then the backup."""

    roots: tuple[Path, ...]


def _read_object(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ConfigError(
            f"No existe {path.name}. Copiá config.example.json como {path.name} "
            "y completá las carpetas de destino."
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"No se pudo leer {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path.name} no es un JSON válido: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path.name} debe contener un objeto JSON con las claves {', '.join(_KEYS)}.")
    return raw


def _read_dir(raw: dict[str, object], key: str) -> Path | None:
    """The folder for `key`, or None when it is absent or empty."""
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"'{key}' debe ser un texto con la ruta de una carpeta.")
    if not value.strip():
        return None
    return Path(os.path.expandvars(value.strip())).expanduser()


def _same_folder_key(root: Path) -> str:
    """Identity of a folder: resolved (``..``, links) and case-folded like Windows compares it."""
    return os.path.normcase(str(root.resolve(strict=False)))


def load_config(path: Path | None = None) -> Config:
    """Read the configuration: the configured destinations, each folder once, in key order."""
    config_path = path if path is not None else DEFAULT_CONFIG_PATH
    raw = _read_object(config_path)
    roots: list[Path] = []
    seen: set[str] = set()
    for key in _KEYS:
        root = _read_dir(raw, key)
        if root is None:
            continue
        identity = _same_folder_key(root)
        if identity not in seen:
            seen.add(identity)
            roots.append(root)
    if not roots:
        raise ConfigError(
            f"{config_path.name} no define '{_KEYS[0]}' ni '{_KEYS[1]}': no hay dónde guardar el reporte."
        )
    return Config(roots=tuple(roots))
