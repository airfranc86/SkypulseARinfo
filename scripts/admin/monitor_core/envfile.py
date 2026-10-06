"""Tiny `KEY=value` parser for credential files.

The monitor loads credentials at run time from a file passed with `--env-file`.
`load_env_values` keeps only the keys that were asked for, so nothing else from the
file stays in memory, and errors never quote file contents.
"""

from __future__ import annotations

import codecs
from collections.abc import Iterable
from pathlib import Path


class EnvFileError(Exception):
    """The credentials file could not be read. The message never includes contents."""


def _strip_value(raw: str) -> str:
    value = raw.strip()
    if value.startswith(('"', "'")):
        closing = value.find(value[0], 1)
        # Matching quote: take what is inside (anything after it is a comment).
        # Unbalanced quote: keep the value as typed.
        return value[1:closing] if closing != -1 else value
    hash_at = value.find(" #")
    if hash_at == -1:
        hash_at = value.find("\t#")
    return value[:hash_at].rstrip() if hash_at != -1 else value


def parse_env_text(text: str) -> dict[str, str]:
    """Parse `KEY=value` lines. Later duplicates win; malformed lines are skipped."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].lstrip()
        key, _, raw = stripped.partition("=")
        key = key.strip()
        if key:
            values[key] = _strip_value(raw)
    return values


def _decode(raw: bytes) -> str:
    """UTF-8 (BOM tolerated) or UTF-16 with BOM, which PowerShell 5 writes with `>`."""
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def load_env(path: Path, wanted: Iterable[str]) -> tuple[dict[str, str], int]:
    """Read `path`: the `wanted` keys that exist (case-insensitive) and how many variables it has."""
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise EnvFileError(
            f"no se pudo leer el archivo de credenciales {path} ({type(exc).__name__})"
        ) from None
    try:
        text = _decode(raw)
    except UnicodeDecodeError:
        raise EnvFileError(f"el archivo {path} no es UTF-8 ni UTF-16 válido") from None
    parsed = {key.upper(): value for key, value in parse_env_text(text).items()}
    found = {name: parsed[name.upper()] for name in wanted if name.upper() in parsed}
    return found, len(parsed)


def load_env_values(path: Path, wanted: Iterable[str]) -> dict[str, str]:
    """Only the `wanted` keys that exist; everything else in the file is discarded."""
    return load_env(path, wanted)[0]
