"""End-to-end CLI behaviour with synthetic data: no network, no real notification."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from report_factories import AR_TZ, make_daily, make_daily_multi, make_ecmwf_rain, make_hourly, make_raw

from ciudades import City
from fuente_datos import DatosNoDisponibles
from generar_reporte import main
from rutas import day_folder
from tipos import ReportData

NOW = datetime(2026, 10, 6, 19, 0, tzinfo=AR_TZ)
FOLDER_DAY = "2026-10-07"


def raws() -> dict[str, tuple]:
    return {
        # Gust 62 km/h from the south-west -> Alerta
        "Cordoba": make_raw(
            ecmwf_at={2: {"wind_gusts_max": 62.0, "wind_dir_dominant": 225.0}},
            hourly=make_hourly(gust={(2, 16): 62.0}),
        ),
        # Calm -> Estandar
        "CABA": make_raw(),
        # 20 mm of rain -> Alerta
        "Resistencia": make_raw(
            ecmwf_at={2: {"precip_sum": 20.0, "precip_prob_max": 95.0, "weather_codes": 65}},
            hourly=make_hourly(rain={(2, 8): 6.0, (2, 11): 3.0}),
            # ECMWF hourly, coherent with its 20 mm: 13 mm in 06-09 and 7 mm in 09-12
            ecmwf_rain=make_ecmwf_rain(rain={(2, 8): 13.0, (2, 11): 7.0}),
        ),
    }


def fake_fetcher(failing: tuple[str, ...] = (), data: dict[str, tuple] | None = None):
    table = data or raws()

    async def fetcher(city: City):
        if city.slug in failing:
            raise DatosNoDisponibles(f"{city.slug}: sin datos de prueba")
        return table[city.slug]

    return fetcher


class Notifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, title: str, body: str) -> bool:
        self.calls.append((title, body))
        return True


def fake_png(data: ReportData, variante: str) -> bytes:
    return f"PNG:{data.city.slug}:{variante}".encode()


def run(argv: list[str], **kwargs):
    kwargs.setdefault("fetcher", fake_fetcher())
    kwargs.setdefault("now", NOW)
    kwargs.setdefault("notifier", Notifier())
    return main(argv, **kwargs)


def files_under(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)).replace("\\", "/") for p in root.rglob("*") if p.is_file())


# ---------------------------------------------------------------------------
# --solo-datos
# ---------------------------------------------------------------------------


def test_solo_datos_prints_json_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    notifier = Notifier()
    code = run(["--solo-datos"], config_path=tmp_path / "missing.json", notifier=notifier)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["fecha"] == FOLDER_DAY
    assert payload["errores"] == []
    by_slug = {c["slug"]: c for c in payload["ciudades"]}
    assert list(by_slug) == ["Cordoba", "CABA", "Resistencia"]
    assert {slug: c["variante"] for slug, c in by_slug.items()} == {
        "Cordoba": "Alerta",
        "CABA": "Estandar",
        "Resistencia": "Alerta",
    }
    cordoba = by_slug["Cordoba"]
    assert cordoba["datos"]["wind_gust_max"] == 62.0
    assert cordoba["evaluacion"]["wind"]["origin"] == "del sudoeste"
    assert by_slug["Resistencia"]["evaluacion"]["rain"]["window"] == "06:00 a 12:00 hs"
    assert list(tmp_path.iterdir()) == []
    assert notifier.calls == []


def test_solo_datos_with_a_failing_city_reports_it_and_exits_1(capsys: pytest.CaptureFixture[str]) -> None:
    code = run(["--solo-datos"], fetcher=fake_fetcher(failing=("CABA",)))
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 1
    assert [c["slug"] for c in payload["ciudades"]] == ["Cordoba", "Resistencia"]
    assert payload["errores"] == [{"slug": "CABA", "message": "CABA: sin datos de prueba"}]
    assert "CABA" in captured.err


def test_dias_2_targets_the_day_after_tomorrow(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["--solo-datos", "--dias", "2"]) == 0
    assert json.loads(capsys.readouterr().out)["fecha"] == "2026-10-08"


def test_fecha_overrides_dias(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["--solo-datos", "--dias", "2", "--fecha", "2026-10-09"]) == 0
    assert json.loads(capsys.readouterr().out)["fecha"] == "2026-10-09"


def test_a_model_fallback_is_warned_on_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    gfs_only = (make_daily_multi(gfs=make_daily()), make_hourly(), make_ecmwf_rain())
    data = {**raws(), "CABA": gfs_only}
    assert run(["--solo-datos"], fetcher=fake_fetcher(data=data)) == 0
    err = capsys.readouterr().err
    assert "Buenos Aires" in err
    assert "GFS" in err
    assert "Córdoba" not in err


def test_no_data_warnings_when_every_source_is_coherent(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["--solo-datos"]) == 0
    captured = capsys.readouterr()
    assert "franja" not in captured.err
    assert all(c["datos"]["avisos"] == [] for c in json.loads(captured.out)["ciudades"])


def test_a_missing_ecmwf_hourly_rain_is_warned_in_the_run_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    daily, hourly, _ = raws()["Resistencia"]
    data = {**raws(), "Resistencia": (daily, hourly, None)}
    code = run(["--salida", str(tmp_path), "--sin-aviso"], fetcher=fake_fetcher(data=data), renderer=no_plate)
    assert code == 0  # a warning, not an error: the plate keeps the total and the probability
    err = capsys.readouterr().err
    assert "Resistencia" in err and "franja" in err
    caption = next(tmp_path.rglob("*_Caption_Instagram.txt")).read_text(encoding="utf-8")
    assert "20 mm" in caption
    assert "más intensa" not in caption


def test_solo_datos_carries_the_data_warnings(capsys: pytest.CaptureFixture[str]) -> None:
    daily, hourly, _ = raws()["Resistencia"]
    data = {**raws(), "Resistencia": (daily, hourly, None)}
    assert run(["--solo-datos"], fetcher=fake_fetcher(data=data)) == 0
    by_slug = {c["slug"]: c for c in json.loads(capsys.readouterr().out)["ciudades"]}
    assert len(by_slug["Resistencia"]["datos"]["avisos"]) == 1
    assert by_slug["Resistencia"]["evaluacion"]["rain"]["window"] is None
    assert by_slug["CABA"]["datos"]["avisos"] == []


def test_a_data_warning_is_printed_exactly_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    caplog.set_level(logging.WARNING)
    daily, hourly, _ = raws()["Resistencia"]
    data = {**raws(), "Resistencia": (daily, hourly, None)}
    assert run(["--solo-datos"], fetcher=fake_fetcher(data=data)) == 0
    err = capsys.readouterr().err
    assert err.count("sin lluvia horaria de ECMWF") == 1
    # the CLI shows WARNING records on the console: none may repeat the summary
    assert not [r for r in caplog.records if "sin lluvia horaria de ECMWF" in r.getMessage()]


def test_an_incoherent_day_shows_the_bound_in_caption_and_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    daily, hourly, _ = make_raw(ecmwf_at={2: {"precip_sum": 1.8, "precip_prob_max": 90.0}})
    incoherent = make_ecmwf_rain(rain={(2, 22): 7.9, (2, 23): 7.9, (3, 0): 7.9})
    data = {**raws(), "Resistencia": (daily, hourly, incoherent)}
    assert run(["--salida", str(tmp_path), "--sin-aviso"], fetcher=fake_fetcher(data=data), renderer=no_plate) == 0
    err = capsys.readouterr().err
    assert err.count("usando la cota horaria") == 1
    caption = next(tmp_path.rglob("*_Caption_Instagram.txt")).read_text(encoding="utf-8")
    assert "hasta 24 mm, más intensa de 21:00 a 00:00 hs" in caption
    assert "Lluvia fuerte en Resistencia" in caption


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def no_plate(data: ReportData, variante: str) -> None:
    return None


def test_writes_the_caption_under_the_override_root(tmp_path: Path) -> None:
    notifier = Notifier()
    code = run(["--salida", str(tmp_path), "--sin-aviso"], notifier=notifier, renderer=no_plate)
    assert code == 0
    folder = day_folder(tmp_path, datetime(2026, 10, 7).date())
    assert files_under(tmp_path) == [
        f"SkyPulse_Instagram_Reports/2026/10_Octubre/Semana_41/{FOLDER_DAY}_Caption_Instagram.txt"
    ]
    caption = (folder / f"{FOLDER_DAY}_Caption_Instagram.txt").read_text(encoding="utf-8")
    assert "Pronóstico para mañana, miércoles 7 de octubre" in caption
    assert "62 km/h del sudoeste" in caption
    assert "Datos: SkyPulse" in caption
    assert notifier.calls == []


def test_a_renderer_that_returns_nothing_writes_no_plates_and_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(["--salida", str(tmp_path), "--sin-aviso"], renderer=no_plate) == 0
    assert not any(name.endswith(".png") for name in files_under(tmp_path))
    assert "render" in capsys.readouterr().err.lower()


def test_rendered_plates_are_written_with_the_variant_in_the_name(tmp_path: Path) -> None:
    assert run(["--salida", str(tmp_path), "--sin-aviso"], renderer=fake_png) == 0
    names = [Path(n).name for n in files_under(tmp_path)]
    assert names == [
        f"{FOLDER_DAY}_Caption_Instagram.txt",
        f"{FOLDER_DAY}_Reporte_Alerta_Cordoba.png",
        f"{FOLDER_DAY}_Reporte_Alerta_Resistencia.png",
        f"{FOLDER_DAY}_Reporte_Estandar_CABA.png",
    ]
    folder = day_folder(tmp_path, datetime(2026, 10, 7).date())
    assert (folder / f"{FOLDER_DAY}_Reporte_Alerta_Cordoba.png").read_bytes() == b"PNG:Cordoba:Alerta"


def test_running_twice_is_idempotent(tmp_path: Path) -> None:
    run(["--salida", str(tmp_path), "--sin-aviso"], renderer=fake_png)
    first = files_under(tmp_path)
    assert run(["--salida", str(tmp_path), "--sin-aviso"], renderer=fake_png) == 0
    assert files_under(tmp_path) == first


def test_a_renderer_error_in_one_city_does_not_stop_the_others(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def flaky(data: ReportData, variante: str) -> bytes:
        if data.city.slug == "CABA":
            raise RuntimeError("template exploded")
        return fake_png(data, variante)

    code = run(["--salida", str(tmp_path), "--sin-aviso"], renderer=flaky)
    assert code == 1
    names = [Path(n).name for n in files_under(tmp_path)]
    assert f"{FOLDER_DAY}_Reporte_Alerta_Cordoba.png" in names
    assert f"{FOLDER_DAY}_Reporte_Alerta_Resistencia.png" in names
    assert not any("CABA" in n for n in names)
    assert "template exploded" in capsys.readouterr().err


def test_a_failing_city_keeps_going_and_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    notifier = Notifier()
    code = run(
        ["--salida", str(tmp_path)],
        fetcher=fake_fetcher(failing=("CABA",)),
        renderer=fake_png,
        notifier=notifier,
    )
    assert code == 1
    names = [Path(n).name for n in files_under(tmp_path)]
    assert f"{FOLDER_DAY}_Reporte_Alerta_Cordoba.png" in names
    assert f"{FOLDER_DAY}_Caption_Instagram.txt" in names
    caption_path = next(p for p in tmp_path.rglob("*.txt"))
    caption = caption_path.read_text(encoding="utf-8")
    assert "Córdoba" in caption and "Resistencia" in caption
    assert "Buenos Aires" not in caption
    assert "CABA" in capsys.readouterr().err
    (title, body), = notifier.calls
    assert body.startswith("2 de 3 placas:")


def test_if_every_city_fails_nothing_is_written_or_announced(tmp_path: Path) -> None:
    notifier = Notifier()
    code = run(
        ["--salida", str(tmp_path)],
        fetcher=fake_fetcher(failing=("Cordoba", "CABA", "Resistencia")),
        notifier=notifier,
    )
    assert code == 1
    assert files_under(tmp_path) == []
    assert notifier.calls == []


def test_notification_is_sent_once_with_count_and_variants(tmp_path: Path) -> None:
    notifier = Notifier()
    assert run(["--salida", str(tmp_path)], renderer=fake_png, notifier=notifier) == 0
    (title, body), = notifier.calls
    assert title == "SkyPulse: reporte de mañana listo"
    assert body == "3 placas: Córdoba (Alerta), Buenos Aires (Estándar), Resistencia (Alerta)"


def test_sin_aviso_skips_the_notification(tmp_path: Path) -> None:
    notifier = Notifier()
    run(["--salida", str(tmp_path), "--sin-aviso"], renderer=fake_png, notifier=notifier)
    assert notifier.calls == []


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def write_config(tmp_path: Path, **roots: str) -> Path:
    path = tmp_path / "config.local.json"
    path.write_text(json.dumps(roots), encoding="utf-8")
    return path


def test_without_override_it_writes_to_every_configured_root(tmp_path: Path) -> None:
    drive, backup = tmp_path / "drive", tmp_path / "backup"
    config = write_config(tmp_path, drive_dir=str(drive), backup_dir=str(backup))
    assert run(["--sin-aviso"], renderer=fake_png, config_path=config) == 0
    assert files_under(drive) == files_under(backup)
    assert len(files_under(drive)) == 4


def test_an_unwritable_root_does_not_stop_the_other_and_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    blocked = tmp_path / "not_a_folder"
    blocked.write_text("I am a file", encoding="utf-8")
    backup = tmp_path / "backup"
    config = write_config(tmp_path, drive_dir=str(blocked), backup_dir=str(backup))
    assert run(["--sin-aviso"], renderer=fake_png, config_path=config) == 1
    assert len(files_under(backup)) == 4
    assert str(blocked) in capsys.readouterr().err


def test_missing_config_fails_before_touching_the_network(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    async def never(city: City):
        raise AssertionError("the data must not be fetched without a valid config")

    code = run(["--sin-aviso"], fetcher=never, config_path=tmp_path / "missing.json")
    assert code == 1
    assert "config.example.json" in capsys.readouterr().err


def test_config_with_no_root_is_an_error(tmp_path: Path) -> None:
    config = write_config(tmp_path, drive_dir="", backup_dir="")
    assert run(["--sin-aviso"], config_path=config) == 1


# ---------------------------------------------------------------------------
# Invalid arguments -> exit code 2
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["--dias", "3"],
        ["--dias", "0"],
        ["--dias", "uno"],
        ["--fecha", "2026-13-01"],
        ["--fecha", "07/10/2026"],
        ["--fecha", "2026-10-05"],  # in the past
        ["--fecha", "2026-12-25"],  # beyond the forecast window
        ["--no-existe"],
    ],
)
def test_invalid_arguments_exit_with_2(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["--solo-datos", *argv]) == 2
    assert capsys.readouterr().err != ""


def test_help_exits_with_0(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["--help"]) == 0
    assert "--solo-datos" in capsys.readouterr().out
