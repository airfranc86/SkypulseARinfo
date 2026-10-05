"""Archive the SMN daily ``datohorario`` zip (hourly observations incl. wind and pressure).

The endpoint ignores any date and always serves the latest day, so a day that is not
archived on time cannot be recovered later. Run it once a day. The file name comes from the
``Content-Disposition`` header (``DatosHorarios-AAAAMMDD.zip``) and is validated strictly.
Existing files are never overwritten: different bytes under the same name are stored as
``...rev2.zip``, ``...rev3.zip`` and so on. Every run appends a line to ``manifest.csv``.

Exit codes: 0 success (including "already archived"), 1 network or validation error,
2 invalid arguments.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import os
import re
import sys
import time
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from openmeteo_client import NetworkError

OFFICIAL_URL = "https://ssl.smn.gob.ar/dpd/zipopendata.php?dato=datohorario"
PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_DESTINATION = PACKAGE_DIR / "archivo_datohorario"
NAME_PATTERN = re.compile(r"^DatosHorarios-(\d{8})\.zip$")
_FILENAME_PARAM = re.compile(r'filename\s*=\s*"?([^";]*)"?', re.IGNORECASE)
USER_AGENT = "skypulse-fra321-archiver/1.0 (non-commercial open-data archive)"
MANIFEST_NAME = "manifest.csv"
MANIFEST_HEADER = ("archivado_utc", "nombre", "bytes", "sha256", "archivo_escrito", "estado")
MAX_RETRIES = 2
BACKOFF_SECONDS = 2.0
TIMEOUT_SECONDS = 60.0
MAX_REVISIONS = 1000
EXIT_OK, EXIT_ERROR, EXIT_ARGS = 0, 1, 2

STATUS_NEW = "nuevo"
STATUS_ALREADY = "ya_archivado"
STATUS_REVISION = "revision"

Say = Callable[[str], None]
Sleep = Callable[[float], None]


class ArchiveError(RuntimeError):
    """Network or validation failure: nothing is written."""


@dataclass(frozen=True)
class BinaryResponse:
    status: int
    content: bytes
    headers: Mapping[str, str] = field(default_factory=dict)


HttpGetBytes = Callable[[str, Mapping[str, str], float], BinaryResponse]


def httpx_get_bytes(url: str, headers: Mapping[str, str], timeout: float) -> BinaryResponse:
    """Default transport: GET with httpx, body kept as raw bytes."""
    import httpx

    try:
        response = httpx.get(url, headers=dict(headers), timeout=timeout, follow_redirects=True)
    except httpx.TransportError as exc:
        raise NetworkError(f"{type(exc).__name__}: {exc}") from exc
    return BinaryResponse(response.status_code, response.content, dict(response.headers))


def fetch(url: str, http_get: HttpGetBytes, sleep: Sleep) -> BinaryResponse:
    """GET with up to ``MAX_RETRIES`` retries (exponential backoff) on 5xx and network errors."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/zip"}
    problem = ""
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = http_get(url, headers, TIMEOUT_SECONDS)
        except NetworkError as exc:
            problem = f"network error: {exc}"
        else:
            if response.status == 200:
                return response
            if response.status < 500:
                raise ArchiveError(f"HTTP {response.status} from the server (not retried)")
            problem = f"HTTP {response.status}"
        if attempt < MAX_RETRIES:
            sleep(BACKOFF_SECONDS * 2**attempt)
    raise ArchiveError(f"{problem} persisted after {MAX_RETRIES + 1} attempts")


def parse_filename(headers: Mapping[str, str]) -> str:
    """Archive name from ``Content-Disposition``; strict ``DatosHorarios-AAAAMMDD.zip`` only."""
    value = next((v for k, v in headers.items() if k.lower() == "content-disposition"), None)
    if value is None:
        raise ArchiveError("response has no Content-Disposition header; refusing to guess a name")
    match = _FILENAME_PARAM.search(value)
    raw = match.group(1) if match else ""
    name_match = NAME_PATTERN.fullmatch(raw)
    if name_match is None:
        raise ArchiveError(f"unexpected filename {raw!r}; expected DatosHorarios-AAAAMMDD.zip")
    try:
        dt.datetime.strptime(name_match.group(1), "%Y%m%d")
    except ValueError:
        raise ArchiveError(f"filename {raw!r} has an invalid date") from None
    return raw


def validate_zip(content: bytes) -> None:
    """Raise ``ArchiveError`` unless ``content`` is a valid, non-empty zip archive."""
    if not content:
        raise ArchiveError("downloaded file is empty")
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise ArchiveError(
            f"downloaded file is not a zip archive (starts with {content[:40]!r})"
        ) from None
    with archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise ArchiveError(f"corrupt zip: bad CRC in member {bad_member!r}")
        if not any(not info.is_dir() for info in archive.infolist()):
            raise ArchiveError("zip archive contains no files")


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@dataclass(frozen=True)
class Plan:
    status: str  # nuevo | ya_archivado | revision
    target: str  # file name inside the destination folder


def revision_name(name: str, revision: int) -> str:
    return name if revision == 1 else f"{name[: -len('.zip')]}.rev{revision}.zip"


def plan_archive(dest: Path, name: str, digest: str) -> Plan:
    """Decide what to do: write new, skip identical, or store a new revision."""
    for revision in range(1, MAX_REVISIONS + 1):
        candidate = revision_name(name, revision)
        path = dest / candidate
        if not path.exists():
            return Plan(STATUS_NEW if revision == 1 else STATUS_REVISION, candidate)
        if sha256_hex(path.read_bytes()) == digest:
            return Plan(STATUS_ALREADY, candidate)
    raise ArchiveError(f"more than {MAX_REVISIONS} revisions of {name}")


def write_atomic(dest: Path, target: str, content: bytes) -> None:
    """Write via a temporary file and rename; never leaves the temporary file behind."""
    dest.mkdir(parents=True, exist_ok=True)
    tmp = dest / f".{target}.tmp"
    try:
        tmp.write_bytes(content)
        os.replace(tmp, dest / target)
    finally:
        tmp.unlink(missing_ok=True)


def append_manifest(
    dest: Path, now: dt.datetime, name: str, content: bytes, plan: Plan
) -> None:
    """Append one line (file names only, no absolute paths) to ``manifest.csv``."""
    path = dest / MANIFEST_NAME
    is_new = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if is_new:
            writer.writerow(MANIFEST_HEADER)
        writer.writerow(
            (
                now.isoformat(timespec="seconds"),
                name,
                len(content),
                sha256_hex(content),
                plan.target,
                plan.status,
            )
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Archiva el zip diario datohorario del SMN (no se puede recuperar después)."
    )
    parser.add_argument("--destino", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--url", default=OFFICIAL_URL)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="descarga y valida (solo lectura) e imprime qué haría; no escribe nada",
    )
    return parser


def _report(plan: Plan, name: str, dry_run: bool, say: Say, complain: Say) -> None:
    prefix = "[dry-run] " if dry_run else ""
    if plan.status == STATUS_ALREADY:
        say(f"{prefix}estado: {STATUS_ALREADY}; {plan.target} ya archivado, sin cambios")
    elif plan.status == STATUS_REVISION:
        complain(
            f"Aviso: {name} ya existía con contenido distinto; "
            f"{'se guardaría' if dry_run else 'guardado'} como {plan.target}"
        )
        say(f"{prefix}estado: {STATUS_REVISION}; {plan.target}")
    else:
        say(f"{prefix}estado: {STATUS_NEW}; {plan.target}")


def run(
    args: argparse.Namespace, http_get: HttpGetBytes, sleep: Sleep, now: dt.datetime,
    say: Say, complain: Say,
) -> None:  # fmt: skip
    response = fetch(args.url, http_get, sleep)
    name = parse_filename(response.headers)
    validate_zip(response.content)
    plan = plan_archive(args.destino, name, sha256_hex(response.content))
    _report(plan, name, args.dry_run, say, complain)
    if args.dry_run:
        return
    if plan.status != STATUS_ALREADY:
        write_atomic(args.destino, plan.target, response.content)
    append_manifest(args.destino, now, name, response.content, plan)


def main(
    argv: Sequence[str] | None = None,
    *,
    http_get: HttpGetBytes | None = None,
    sleep: Sleep = time.sleep,
    now: dt.datetime | None = None,
    out: Say | None = None,
    err: Say | None = None,
) -> int:
    say = out or (lambda m: sys.stdout.write(m + "\n"))
    complain = err or (lambda m: sys.stderr.write(m + "\n"))
    args = build_parser().parse_args(argv)
    if not args.url.startswith(("http://", "https://")):
        complain("Error: --url must start with http:// or https://")
        return EXIT_ARGS
    try:
        run(args, http_get or httpx_get_bytes, sleep, now or dt.datetime.now(dt.UTC), say, complain)
    except (ArchiveError, OSError) as exc:
        complain(f"Error: {exc}")
        return EXIT_ERROR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
