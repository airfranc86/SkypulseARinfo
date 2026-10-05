"""Tests for the command line interface (injected client, no network)."""

from __future__ import annotations

import datetime as dt
import io
import json
import zipfile
from pathlib import Path

import pytest

from conftest import TODAY
from fakeworld import FakeOpenMeteo
from medir_tmax_tmin import build_parser, extract_regtemp_zip, main
from openmeteo_client import ClientConfig, HttpResponse, OpenMeteoClient

NOW = dt.datetime(2026, 10, 5, 12, 0, tzinfo=dt.UTC)
# 2 stations x 4 chunks: the padded range 2025-12-31..2026-04-01 (92 days) in 30-day chunks.
CALLS = 8


class Harness:
    """Runs ``main`` with a fake API, captured output and an isolated cache/output dir."""

    def __init__(self, tmp_path: Path, http=None) -> None:
        self.tmp = tmp_path
        self.http = http or FakeOpenMeteo()
        self.out: list[str] = []
        self.err: list[str] = []
        self.downloads: list[str] = []

    def factory(self, config: ClientConfig) -> OpenMeteoClient:
        return OpenMeteoClient(config, http_get=self.http, sleep=lambda _s: None)

    def downloader(self, url: str) -> bytes:
        self.downloads.append(url)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("regtemp.txt", "FECHA    TMAX  TMIN  NOMBRE\n".encode("latin-1"))
        return buffer.getvalue()

    def run(self, *args: str) -> int:
        return main(
            [*args],
            client_factory=self.factory,
            downloader=self.downloader,
            today=TODAY,
            now=NOW,
            out=self.out.append,
            err=self.err.append,
        )

    @property
    def text(self) -> str:
        return "\n".join(self.out)

    @property
    def errors(self) -> str:
        return "\n".join(self.err)


def real_args(h: Harness, regtemp: Path, *extra: str) -> list[str]:
    return [
        "--regtemp", str(regtemp),
        "--estaciones", "EZEIZA AERO,AEROPARQUE AERO",
        "--inicio", "2026-01-01", "--fin", "2026-03-31",
        "--chunk-dias", "30", "--max-calls", "20", "--pausa", "0",
        "--cache", str(h.tmp / "cache"), "--salida", str(h.tmp / "out"),
        *extra,
    ]  # fmt: skip


@pytest.fixture
def regtemp_file(tmp_path: Path, synthetic_stations, synthetic_regtemp_text) -> Path:
    path = tmp_path / "regtemp.txt"
    path.write_bytes(synthetic_regtemp_text.encode("latin-1"))
    return path


# --- parser ----------------------------------------------------------------------------------


def test_parser_defaults() -> None:
    args = build_parser().parse_args([])

    assert (args.inicio, args.fin) == (dt.date(2025, 10, 5), dt.date(2026, 10, 4))
    assert args.dry_run is False and args.descargar is False
    assert args.estaciones is None and args.ventana_tmax is None
    assert args.max_calls > 0 and args.chunk_dias == 92


# --- dry run ---------------------------------------------------------------------------------


def test_dry_run_with_defaults_reports_plan_and_never_calls_the_network(tmp_path: Path) -> None:
    class Forbidden:
        def __call__(self, *_args, **_kwargs):
            raise AssertionError("network used in --dry-run")

    h = Harness(tmp_path, http=Forbidden())

    code = h.run("--dry-run", "--cache", str(tmp_path / "cache"), "--salida", str(tmp_path / "out"))

    assert code == 0
    assert "56" in h.text  # HTTP calls
    assert "585.6" in h.text  # estimated weight
    assert "14" in h.text  # stations
    assert not (tmp_path / "out").exists()


def test_dry_run_does_not_download_or_need_the_regtemp_file(tmp_path: Path) -> None:
    h = Harness(tmp_path)

    code = h.run("--dry-run", "--descargar", "--cache", str(tmp_path / "cache"))

    assert code == 0
    assert h.downloads == [] and h.http.urls == []


def test_dry_run_counts_cached_requests(tmp_path: Path, regtemp_file: Path) -> None:
    h = Harness(tmp_path)
    assert h.run(*real_args(h, regtemp_file)) == 0
    h.out.clear()

    assert h.run(*real_args(h, regtemp_file), "--dry-run") == 0

    assert f"en cache: {CALLS}" in h.text and "pendientes: 0" in h.text


# --- full run --------------------------------------------------------------------------------


def test_full_run_writes_outputs_and_recovers_windows(tmp_path: Path, regtemp_file: Path) -> None:
    h = Harness(tmp_path)

    code = h.run(*real_args(h, regtemp_file))

    assert code == 0, h.errors
    out = tmp_path / "out"
    assert {p.name for p in out.iterdir()} == {
        "resumen.md", "errores_por_caso.csv", "errores_por_estacion.csv", "metadatos.json",
    }  # fmt: skip
    meta = json.loads((out / "metadatos.json").read_text(encoding="utf-8"))
    assert meta["ventanas"]["tmax"]["nombre"] == "03Z"
    assert meta["ventanas"]["tmin"]["nombre"] == "D-1 21Z"
    assert meta["llamadas_http"] == CALLS and meta["llamadas_cache"] == 0
    assert len(h.http.urls) == CALLS
    assert "03Z" in h.text  # ranking printed to the console


def test_second_run_is_served_entirely_from_cache(tmp_path: Path, regtemp_file: Path) -> None:
    h = Harness(tmp_path)
    assert h.run(*real_args(h, regtemp_file)) == 0
    calls_after_first = len(h.http.urls)

    assert h.run(*real_args(h, regtemp_file)) == 0

    assert len(h.http.urls) == calls_after_first
    meta = json.loads((tmp_path / "out" / "metadatos.json").read_text(encoding="utf-8"))
    assert meta["llamadas_http"] == 0 and meta["llamadas_cache"] == CALLS


def test_outputs_do_not_leak_local_paths(tmp_path: Path, regtemp_file: Path) -> None:
    h = Harness(tmp_path)
    h.run(*real_args(h, regtemp_file))

    for path in (tmp_path / "out").iterdir():
        assert str(tmp_path) not in path.read_text(encoding="utf-8")


def test_forced_window_flags_reach_the_metadata(tmp_path: Path, regtemp_file: Path) -> None:
    h = Harness(tmp_path)

    code = h.run(*real_args(h, regtemp_file, "--ventana-tmax", "06Z"))

    assert code == 0, h.errors
    meta = json.loads((tmp_path / "out" / "metadatos.json").read_text(encoding="utf-8"))
    assert meta["ventanas"]["tmax"]["nombre"] == "06Z"
    assert meta["ventanas"]["tmax"]["forzada"] is True
    assert meta["ventanas"]["tmin"]["forzada"] is False


def test_stations_can_be_given_by_icao_and_duplicates_are_merged(
    tmp_path: Path, regtemp_file: Path
) -> None:
    h = Harness(tmp_path)
    args = real_args(h, regtemp_file)
    args[args.index("--estaciones") + 1] = "SAEZ,EZEIZA AERO,SABE"

    assert h.run(*args) == 0

    meta = json.loads((tmp_path / "out" / "metadatos.json").read_text(encoding="utf-8"))
    assert [e["icao"] for e in meta["estaciones"]] == ["SAEZ", "SABE"]


# --- limits and errors -----------------------------------------------------------------------


def test_max_calls_below_the_plan_fails_fast(tmp_path: Path, regtemp_file: Path) -> None:
    h = Harness(tmp_path)
    args = real_args(h, regtemp_file)
    args[args.index("--max-calls") + 1] = "2"

    code = h.run(*args)

    assert code == 2
    assert "--max-calls" in h.errors
    assert h.http.urls == []


def test_persistent_429_aborts_the_run(tmp_path: Path, regtemp_file: Path) -> None:
    calls: list[str] = []

    def always_429(url, headers, timeout):  # type: ignore[no-untyped-def]
        calls.append(url)
        return HttpResponse(429, "{}", {})

    h = Harness(tmp_path, http=always_429)

    code = h.run(*real_args(h, regtemp_file))

    assert code == 2
    assert "429" in h.errors
    assert len(calls) == 5  # first attempt + 4 retries, then stop
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    ("flag", "value", "message"),
    [
        ("--estaciones", "NOWHERE AERO", "NOWHERE AERO"),
        ("--ventana-tmax", "99Z", "99Z"),
        ("--max-calls", "0", "max-calls"),
    ],
)
def test_invalid_arguments_exit_with_code_2(
    tmp_path: Path, regtemp_file: Path, flag: str, value: str, message: str
) -> None:
    h = Harness(tmp_path)
    args = real_args(h, regtemp_file)
    if flag in args:
        args[args.index(flag) + 1] = value
    else:
        args += [flag, value]

    assert h.run(*args) == 2
    assert message in h.errors
    assert h.http.urls == []


def test_start_after_end_is_rejected(tmp_path: Path, regtemp_file: Path) -> None:
    h = Harness(tmp_path)
    args = real_args(h, regtemp_file)
    args[args.index("--inicio") + 1] = "2026-05-01"

    assert h.run(*args) == 2
    assert "inicio" in h.errors.lower()


def test_missing_regtemp_file_suggests_download(tmp_path: Path) -> None:
    h = Harness(tmp_path)

    code = h.run("--regtemp", str(tmp_path / "missing.txt"), "--cache", str(tmp_path / "cache"))

    assert code == 2
    assert "--descargar" in h.errors


# --- download --------------------------------------------------------------------------------


def test_extract_regtemp_zip_writes_latin1_text(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("regtemp.txt", "04102026  10.0   2.0 PEÑA AERO\n".encode("latin-1"))

    target = extract_regtemp_zip(buffer.getvalue(), tmp_path / "regtemp.txt")

    assert target.read_bytes().decode("latin-1") == "04102026  10.0   2.0 PEÑA AERO\n"


def test_extract_regtemp_zip_rejects_empty_archive(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w"):
        pass

    with pytest.raises(ValueError, match="empty"):
        extract_regtemp_zip(buffer.getvalue(), tmp_path / "regtemp.txt")


def test_download_flag_fetches_zip_into_cache(tmp_path: Path, regtemp_file: Path) -> None:
    h = Harness(tmp_path)
    args = real_args(h, tmp_path / "cache" / "regtemp.txt", "--descargar")

    h.run(*args)  # the stub archive has no data rows: the run itself fails, the download must not

    assert h.downloads == ["https://ssl.smn.gob.ar/dpd/zipopendata.php?dato=regtemp"]
    assert (tmp_path / "cache" / "regtemp.zip").exists()
    assert (tmp_path / "cache" / "regtemp.txt").exists()
