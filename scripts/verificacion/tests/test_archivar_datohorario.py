"""Tests for the daily datohorario archiver (no real network)."""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import threading
import zipfile
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

import archivar_datohorario as arch
from archivar_datohorario import (
    ArchiveError,
    BinaryResponse,
    NetworkError,
    main,
    parse_filename,
    plan_archive,
    validate_zip,
)

NAME = "DatosHorarios-20261004.zip"
NOW = dt.datetime(2026, 10, 5, 3, 0, tzinfo=dt.UTC)
LATER = dt.datetime(2026, 10, 6, 3, 0, tzinfo=dt.UTC)


def make_zip(files: Mapping[str, bytes] | None = None) -> bytes:
    files = {"datohorario.txt": b"FECHA HORA TEMP HUM PNM DD FF\n" * 20} if files is None else files
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def corrupt_zip() -> bytes:
    data = bytearray(make_zip({"a.txt": b"hello world " * 50}))
    data[data.find(b"hello")] ^= 0xFF  # stored (uncompressed): CRC no longer matches
    return bytes(data)


def reply(content: bytes, name: str | None = NAME, status: int = 200) -> BinaryResponse:
    headers = {} if name is None else {"Content-Disposition": f"attachment; filename={name}"}
    return BinaryResponse(status, content, headers)


class FakeSmn:
    """Serves scripted responses in order; the last one repeats."""

    def __init__(self, *responses: BinaryResponse | Exception) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.headers: list[Mapping[str, str]] = []

    def __call__(self, url: str, headers: Mapping[str, str], timeout: float) -> BinaryResponse:
        item = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        self.headers.append(headers)
        if isinstance(item, Exception):
            raise item
        return item


class Run:
    def __init__(self, tmp: Path, http: FakeSmn) -> None:
        self.dest = tmp / "archivo"
        self.http = http
        self.sleeps: list[float] = []
        self.out: list[str] = []
        self.err: list[str] = []

    def __call__(self, *args: str, now: dt.datetime = NOW) -> int:
        return main(
            ["--destino", str(self.dest), "--url", "https://smn.test/datohorario", *args],
            http_get=self.http,
            sleep=self.sleeps.append,
            now=now,
            out=self.out.append,
            err=self.err.append,
        )

    @property
    def stdout(self) -> str:
        return "\n".join(self.out)

    @property
    def stderr(self) -> str:
        return "\n".join(self.err)

    def files(self) -> list[str]:
        return sorted(p.name for p in self.dest.iterdir()) if self.dest.exists() else []

    def manifest(self) -> list[dict[str, str]]:
        with (self.dest / "manifest.csv").open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))


# --- pure functions ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "header",
    [
        f"attachment; filename={NAME}",
        f'attachment; filename="{NAME}"',
        f"attachment;filename={NAME};",
        f"inline; FILENAME={NAME}",
    ],
)
def test_parse_filename_accepts_real_header_shapes(header: str) -> None:
    assert parse_filename({"content-disposition": header}) == NAME


@pytest.mark.parametrize(
    "name",
    [
        "../x.zip",
        "a/b.zip",
        "..\\x.zip",
        "/etc/passwd",
        "DatosHorarios-2026100.zip",
        "DatosHorarios-20261004.zip.exe",
        "DatosHorarios-20261004.rev2.zip",
        "datoshorarios-20261004.zip",
        "DatosHorarios-20269999.zip",
        "x.zip",
    ],
)
def test_parse_filename_rejects_unsafe_or_unexpected_names(name: str) -> None:
    with pytest.raises(ArchiveError, match="filename"):
        parse_filename({"Content-Disposition": f"attachment; filename={name}"})


def test_parse_filename_requires_the_header() -> None:
    with pytest.raises(ArchiveError, match="Content-Disposition"):
        parse_filename({})


def test_validate_zip_accepts_a_good_archive() -> None:
    validate_zip(make_zip())


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"", "empty"),
        (b"<html><body>403 Forbidden</body></html>", "zip"),
        (corrupt_zip(), "corrupt"),
        (make_zip({}), "no files"),
    ],
)
def test_validate_zip_rejects_bad_content(content: bytes, message: str) -> None:
    with pytest.raises(ArchiveError, match=message):
        validate_zip(content)


def test_plan_archive_new_then_identical_then_revisions(tmp_path: Path) -> None:
    digest = hashlib.sha256(b"one").hexdigest()
    assert plan_archive(tmp_path, NAME, digest) == arch.Plan("nuevo", NAME)

    (tmp_path / NAME).write_bytes(b"one")
    assert plan_archive(tmp_path, NAME, digest) == arch.Plan("ya_archivado", NAME)

    other = hashlib.sha256(b"two").hexdigest()
    assert plan_archive(tmp_path, NAME, other) == arch.Plan(
        "revision", "DatosHorarios-20261004.rev2.zip"
    )
    (tmp_path / "DatosHorarios-20261004.rev2.zip").write_bytes(b"two")
    assert plan_archive(tmp_path, NAME, other) == arch.Plan(
        "ya_archivado", "DatosHorarios-20261004.rev2.zip"
    )
    third = hashlib.sha256(b"three").hexdigest()
    assert plan_archive(tmp_path, NAME, third).target == "DatosHorarios-20261004.rev3.zip"


# --- archiving ---------------------------------------------------------------------------------


def test_new_file_is_written_and_recorded_in_the_manifest(tmp_path: Path) -> None:
    content = make_zip()
    run = Run(tmp_path, FakeSmn(reply(content)))

    assert run() == 0

    assert (run.dest / NAME).read_bytes() == content
    assert run.files() == [NAME, "manifest.csv"]
    (row,) = run.manifest()
    assert row == {
        "archivado_utc": "2026-10-05T03:00:00+00:00",
        "nombre": NAME,
        "bytes": str(len(content)),
        "sha256": hashlib.sha256(content).hexdigest(),
        "archivo_escrito": NAME,
        "estado": "nuevo",
    }
    assert str(tmp_path) not in (run.dest / "manifest.csv").read_text(encoding="utf-8")


def test_request_is_identifiable_and_has_no_credentials(tmp_path: Path) -> None:
    run = Run(tmp_path, FakeSmn(reply(make_zip())))

    run()

    headers = run.http.headers[0]
    assert "skypulse" in headers["User-Agent"].lower()
    assert not {k.lower() for k in headers} & {"authorization", "cookie", "x-api-key"}


def test_second_identical_run_does_nothing_and_succeeds(tmp_path: Path) -> None:
    content = make_zip()
    run = Run(tmp_path, FakeSmn(reply(content)))
    assert run() == 0
    before = (run.dest / NAME).stat().st_mtime_ns

    assert run(now=LATER) == 0

    assert run.files() == [NAME, "manifest.csv"]
    assert (run.dest / NAME).stat().st_mtime_ns == before
    assert [r["estado"] for r in run.manifest()] == ["nuevo", "ya_archivado"]
    assert run.manifest()[1]["archivado_utc"] == "2026-10-06T03:00:00+00:00"
    assert "ya archivado" in run.stdout.lower()


def test_same_name_with_different_bytes_creates_a_revision(tmp_path: Path) -> None:
    first = make_zip()
    second = make_zip({"x.txt": b"changed"})
    third = make_zip({"y.txt": b"again"})
    run = Run(tmp_path, FakeSmn(reply(first)))
    run()

    run.http = FakeSmn(reply(second))
    assert run(now=LATER) == 0
    run.http = FakeSmn(reply(third))
    assert run(now=LATER) == 0

    assert (run.dest / NAME).read_bytes() == first  # original untouched
    assert (run.dest / "DatosHorarios-20261004.rev2.zip").read_bytes() == second
    assert (run.dest / "DatosHorarios-20261004.rev3.zip").read_bytes() == third
    assert [r["estado"] for r in run.manifest()] == ["nuevo", "revision", "revision"]
    assert run.manifest()[1]["archivo_escrito"] == "DatosHorarios-20261004.rev2.zip"
    assert "rev2" in run.stderr

    run.http = FakeSmn(reply(second))
    assert run(now=LATER) == 0
    assert run.manifest()[-1]["estado"] == "ya_archivado"
    assert run.manifest()[-1]["archivo_escrito"] == "DatosHorarios-20261004.rev2.zip"


@pytest.mark.parametrize("name", ["../x.zip", "a/b.zip", "DatosHorarios-1.zip", None])
def test_malicious_or_missing_filename_is_rejected_without_writing(
    tmp_path: Path, name: str | None
) -> None:
    run = Run(tmp_path, FakeSmn(reply(make_zip(), name=name)))

    assert run() == 1

    assert run.files() == []
    assert run.stderr
    assert not (tmp_path / "x.zip").exists()


@pytest.mark.parametrize(
    "response",
    [
        reply(b"<html>Attention Required! Cloudflare</html>"),
        reply(b"<html>403</html>", status=403),
        reply(b""),
        reply(corrupt_zip()),
        reply(make_zip({})),
    ],
)
def test_non_zip_or_corrupt_responses_are_rejected_without_leaving_files(
    tmp_path: Path, response: BinaryResponse
) -> None:
    run = Run(tmp_path, FakeSmn(response))

    assert run() == 1

    assert run.files() == []
    assert "Error" in run.stderr


# --- retries -----------------------------------------------------------------------------------


def test_5xx_is_retried_with_backoff_then_succeeds(tmp_path: Path) -> None:
    run = Run(tmp_path, FakeSmn(reply(b"", status=503), reply(b"", status=502), reply(make_zip())))

    assert run() == 0

    assert run.http.calls == 3
    assert run.sleeps == [2.0, 4.0]
    assert NAME in run.files()


def test_persistent_5xx_gives_up_after_two_retries(tmp_path: Path) -> None:
    run = Run(tmp_path, FakeSmn(reply(b"", status=503)))

    assert run() == 1

    assert run.http.calls == 3
    assert "503" in run.stderr and run.files() == []


def test_timeouts_are_retried(tmp_path: Path) -> None:
    run = Run(tmp_path, FakeSmn(NetworkError("timeout"), reply(make_zip())))

    assert run() == 0
    assert run.sleeps == [2.0]


def test_4xx_is_not_retried(tmp_path: Path) -> None:
    run = Run(tmp_path, FakeSmn(reply(b"forbidden", status=403)))

    assert run() == 1

    assert run.http.calls == 1 and run.sleeps == []
    assert "403" in run.stderr


# --- dry run, atomicity, arguments ----------------------------------------------------------------


def test_dry_run_reports_the_plan_and_writes_nothing(tmp_path: Path) -> None:
    run = Run(tmp_path, FakeSmn(reply(make_zip())))

    assert run("--dry-run") == 0

    assert not run.dest.exists()
    assert NAME in run.stdout and "nuevo" in run.stdout


def test_dry_run_detects_an_already_archived_file(tmp_path: Path) -> None:
    run = Run(tmp_path, FakeSmn(reply(make_zip())))
    run()
    run.out.clear()
    files_before = run.files()
    manifest_before = (run.dest / "manifest.csv").read_text(encoding="utf-8")

    assert run("--dry-run") == 0

    assert "ya_archivado" in run.stdout
    assert run.files() == files_before
    assert (run.dest / "manifest.csv").read_text(encoding="utf-8") == manifest_before


def test_failed_write_leaves_no_temporary_or_final_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_replace(src: object, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(arch.os, "replace", broken_replace)
    run = Run(tmp_path, FakeSmn(reply(make_zip())))

    assert run() == 1

    assert run.files() == []
    assert "disk full" in run.stderr


@pytest.mark.parametrize("url", ["ftp://smn.test/x", "smn.test/x", ""])
def test_invalid_url_exits_with_code_2(tmp_path: Path, url: str) -> None:
    http = FakeSmn(reply(make_zip()))
    code = main(
        ["--destino", str(tmp_path / "a"), "--url", url],
        http_get=http,
        out=lambda _m: None,
        err=lambda _m: None,
    )

    assert code == 2 and http.calls == 0


def test_unknown_argument_exits_with_code_2() -> None:
    with pytest.raises(SystemExit) as info:
        main(["--no-such-flag"])

    assert info.value.code == 2


def test_defaults_point_to_the_official_endpoint_and_a_local_folder() -> None:
    args = arch.build_parser().parse_args([])

    assert args.url == "https://ssl.smn.gob.ar/dpd/zipopendata.php?dato=datohorario"
    assert args.destino == Path(arch.__file__).resolve().parent / "archivo_datohorario"
    assert args.dry_run is False


# --- real httpx transport against a local server -------------------------------------------------

SERVED = make_zip({"datohorario.txt": b"served by the local test server\n"})


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - http.server API
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f"attachment; filename={NAME}")
        self.send_header("Content-Length", str(len(SERVED)))
        self.end_headers()
        self.wfile.write(SERVED)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


def test_end_to_end_with_the_real_transport_against_a_local_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    out: list[str] = []
    try:
        code = main(
            ["--destino", str(tmp_path / "a"), "--url", f"http://127.0.0.1:{server.server_port}/x"],
            now=NOW,
            out=out.append,
            err=out.append,
        )
    finally:
        server.shutdown()
        server.server_close()

    assert code == 0, out
    assert (tmp_path / "a" / NAME).read_bytes() == SERVED


def test_default_transport_wraps_connection_failures() -> None:
    with pytest.raises(NetworkError):
        arch.httpx_get_bytes("http://127.0.0.1:1/unreachable", {}, 1.0)
