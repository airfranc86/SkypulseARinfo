"""CLI of the night notice (``--modo aviso-nocturno``): synthetic data, no network, no real notification."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest
from report_factories import AR_TZ, make_raw, make_visibility
from test_generar_reporte import Notifier, fake_fetcher, fake_png, files_under, write_config

from ciudades import City
from generar_reporte import main
from reglas import Fog
from tipos import ReportData

NOW = datetime(2026, 10, 6, 22, 0, tzinfo=AR_TZ)
DAY = "2026-10-07"
TARGET_INDEX = 2
FOLDER = "SkyPulse_Instagram_Reports/2026/10_Octubre/Semana_41"
NO_NOTICE = "Sin fenómenos intensos para mañana: no se genera aviso"


def calm_table() -> dict[str, tuple]:
    return {"Cordoba": make_raw(), "CABA": make_raw(), "Resistencia": make_raw()}


def stormy_table() -> dict[str, tuple]:
    """Córdoba: gust 62 km/h; Buenos Aires: calm; Resistencia: 20 mm of rain."""
    return {
        "Cordoba": make_raw(ecmwf_at={TARGET_INDEX: {"wind_gusts_max": 62.0, "wind_dir_dominant": 225.0}}),
        "CABA": make_raw(),
        "Resistencia": make_raw(ecmwf_at={TARGET_INDEX: {"precip_sum": 20.0, "precip_prob_max": 95.0}}),
    }


def visibility_fetcher(table: dict[str, object] | None = None):
    calls: list[str] = []

    async def fetcher(city: City):
        calls.append(city.slug)
        return (table or {}).get(city.slug, make_visibility())

    fetcher.calls = calls  # type: ignore[attr-defined]
    return fetcher


FOGGY_CABA = {"CABA": make_visibility(values={(TARGET_INDEX, h): 300.0 for h in range(4, 10)})}


class NightRenderer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Fog | None]] = []

    def __call__(self, data: ReportData, fog: Fog | None) -> bytes:
        self.calls.append((data.city.slug, fog))
        return f"NIGHT:{data.city.slug}".encode()


def run(argv: list[str], **kwargs):
    kwargs.setdefault("fetcher", fake_fetcher(data=stormy_table()))
    kwargs.setdefault("visibility_fetcher", visibility_fetcher())
    kwargs.setdefault("night_renderer", NightRenderer())
    kwargs.setdefault("now", NOW)
    kwargs.setdefault("notifier", Notifier())
    return main(["--modo", "aviso-nocturno", *argv], **kwargs)


# ---------------------------------------------------------------------------
# Nothing intense: nothing at all
# ---------------------------------------------------------------------------


def test_without_intense_phenomena_nothing_is_created_or_announced(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "salida"
    notifier, renderer = Notifier(), NightRenderer()
    code = run(
        ["--salida", str(out)], fetcher=fake_fetcher(data=calm_table()), notifier=notifier, night_renderer=renderer
    )
    assert code == 0
    assert not out.exists()  # not even the folder
    assert notifier.calls == [] and renderer.calls == []
    assert NO_NOTICE in capsys.readouterr().out


def test_without_intense_phenomena_the_configured_roots_stay_untouched(tmp_path: Path) -> None:
    backup = tmp_path / "backup"
    config = write_config(tmp_path, backup_dir=str(backup))
    assert run([], fetcher=fake_fetcher(data=calm_table()), config_path=config) == 0
    assert not backup.exists()


# ---------------------------------------------------------------------------
# Some cities affected
# ---------------------------------------------------------------------------


def test_one_plate_per_affected_city_and_one_caption(tmp_path: Path) -> None:
    renderer = NightRenderer()
    assert run(["--salida", str(tmp_path), "--sin-aviso"], night_renderer=renderer) == 0
    assert files_under(tmp_path) == [
        f"{FOLDER}/{DAY}_Aviso_Nocturno_Cordoba.png",
        f"{FOLDER}/{DAY}_Aviso_Nocturno_Resistencia.png",
        f"{FOLDER}/{DAY}_Caption_Aviso_Nocturno.txt",
    ]
    assert [slug for slug, _ in renderer.calls] == ["Cordoba", "Resistencia"]
    plate = tmp_path / FOLDER / f"{DAY}_Aviso_Nocturno_Cordoba.png"
    assert plate.read_bytes() == b"NIGHT:Cordoba"
    caption = (tmp_path / FOLDER / f"{DAY}_Caption_Aviso_Nocturno.txt").read_text(encoding="utf-8")
    assert "Aviso para mañana, miércoles 7 de octubre" in caption
    assert "Córdoba" in caption and "Resistencia" in caption and "Buenos Aires" not in caption


def test_fog_reaches_the_renderer_and_the_caption(tmp_path: Path) -> None:
    renderer = NightRenderer()
    code = run(
        ["--salida", str(tmp_path), "--sin-aviso"],
        fetcher=fake_fetcher(data=calm_table()),
        visibility_fetcher=visibility_fetcher(FOGGY_CABA),
        night_renderer=renderer,
    )
    assert code == 0
    assert renderer.calls == [("CABA", Fog(first_hour=4, last_hour=9, min_visibility_m=300))]
    caption = next(tmp_path.rglob("*_Caption_Aviso_Nocturno.txt")).read_text(encoding="utf-8")
    assert "Niebla densa posible de 04:00 a 09:00 hs" in caption


def test_the_iso_week_is_the_one_of_the_forecast_day(tmp_path: Path) -> None:
    # Sunday 4/10/2026 at 22:00 (ISO week 40): tomorrow is Monday 5/10, ISO week 41.
    now = datetime(2026, 10, 4, 22, 0, tzinfo=AR_TZ)
    table = {**calm_table(), "CABA": make_raw(ecmwf_at={0: {"weather_codes": 95}})}
    assert run(["--salida", str(tmp_path), "--sin-aviso"], now=now, fetcher=fake_fetcher(data=table)) == 0
    names = files_under(tmp_path)
    assert names == [
        "SkyPulse_Instagram_Reports/2026/10_Octubre/Semana_41/2026-10-05_Aviso_Nocturno_CABA.png",
        "SkyPulse_Instagram_Reports/2026/10_Octubre/Semana_41/2026-10-05_Caption_Aviso_Nocturno.txt",
    ]


def test_fecha_picks_the_day_to_check(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["--solo-datos", "--fecha", "2026-10-08"]) == 0
    assert json.loads(capsys.readouterr().out)["fecha"] == "2026-10-08"


def test_the_notification_counts_the_cities(tmp_path: Path) -> None:
    notifier = Notifier()
    assert run(["--salida", str(tmp_path)], notifier=notifier) == 0
    assert notifier.calls == [("Aviso nocturno listo: 2 ciudades", "Córdoba, Resistencia")]


def test_sin_aviso_skips_the_notification(tmp_path: Path) -> None:
    notifier = Notifier()
    assert run(["--salida", str(tmp_path), "--sin-aviso"], notifier=notifier) == 0
    assert notifier.calls == []


def test_a_failed_visibility_request_is_warned_in_the_run_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run(
        ["--salida", str(tmp_path), "--sin-aviso"],
        visibility_fetcher=visibility_fetcher({"CABA": None}),
    )
    assert code == 0  # a warning, not an error
    err = capsys.readouterr().err
    assert "Resumen de avisos de datos:" in err
    assert err.count("Buenos Aires: sin visibilidad horaria") == 1


def test_a_renderer_error_in_one_city_keeps_the_others_and_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def flaky(data: ReportData, fog: Fog | None) -> bytes:
        if data.city.slug == "Cordoba":
            raise RuntimeError("template exploded")
        return b"NIGHT"

    notifier = Notifier()
    code = run(["--salida", str(tmp_path)], night_renderer=flaky, notifier=notifier)
    assert code == 1
    names = [Path(n).name for n in files_under(tmp_path)]
    assert f"{DAY}_Aviso_Nocturno_Resistencia.png" in names
    assert f"{DAY}_Aviso_Nocturno_Cordoba.png" not in names
    assert "template exploded" in capsys.readouterr().err
    assert notifier.calls[0][0] == "Aviso nocturno listo: 1 de 2 ciudades"


def test_a_city_without_forecast_exits_1_but_the_others_are_checked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run(["--salida", str(tmp_path), "--sin-aviso"], fetcher=fake_fetcher(failing=("Cordoba",), data=stormy_table()))
    assert code == 1
    names = [Path(n).name for n in files_under(tmp_path)]
    assert names == [f"{DAY}_Aviso_Nocturno_Resistencia.png", f"{DAY}_Caption_Aviso_Nocturno.txt"]


# ---------------------------------------------------------------------------
# --solo-datos
# ---------------------------------------------------------------------------


def test_solo_datos_prints_the_phenomena_by_city_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    notifier = Notifier()
    code = run(
        ["--solo-datos"],
        visibility_fetcher=visibility_fetcher(FOGGY_CABA),
        config_path=tmp_path / "missing.json",
        notifier=notifier,
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["modo"] == "aviso-nocturno"
    assert payload["fecha"] == DAY
    assert payload["genera_aviso"] is True
    by_slug = {c["slug"]: c for c in payload["ciudades"]}
    assert {slug: c["motivos"] for slug, c in by_slug.items()} == {
        "Cordoba": ["rafaga"],
        "CABA": ["niebla"],
        "Resistencia": ["lluvia"],
    }
    assert by_slug["Cordoba"]["fenomenos"]["rafaga"]["gust_kmh"] == 62
    assert by_slug["CABA"]["fenomenos"]["niebla"] == {
        "desde": "04:00", "hasta": "09:00", "visibilidad_minima_m": 300, "texto": "04:00 a 09:00 hs"
    }
    assert by_slug["Resistencia"]["fenomenos"]["lluvia"]["mm"] == 20.0
    assert by_slug["CABA"]["fenomenos"]["rafaga"] is None
    assert list(tmp_path.iterdir()) == []
    assert notifier.calls == []


def test_solo_datos_when_nothing_is_intense(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["--solo-datos"], fetcher=fake_fetcher(data=calm_table())) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["genera_aviso"] is False
    assert all(c["motivos"] == [] for c in payload["ciudades"])


# ---------------------------------------------------------------------------
# Living next to the 19:00 report
# ---------------------------------------------------------------------------


def test_the_night_notice_never_overwrites_the_report(tmp_path: Path) -> None:
    report_now = datetime(2026, 10, 6, 19, 0, tzinfo=AR_TZ)
    assert main(
        ["--salida", str(tmp_path), "--sin-aviso"],
        fetcher=fake_fetcher(data=stormy_table()),
        renderer=fake_png,
        notifier=Notifier(),
        now=report_now,
    ) == 0
    before = {p: (tmp_path / p).read_bytes() for p in files_under(tmp_path)}
    assert run(["--salida", str(tmp_path), "--sin-aviso"]) == 0
    after = files_under(tmp_path)
    for path, content in before.items():
        assert (tmp_path / path).read_bytes() == content
    assert len(after) == len(before) + 3
    assert {Path(p).name for p in after} - {Path(p).name for p in before} == {
        f"{DAY}_Aviso_Nocturno_Cordoba.png",
        f"{DAY}_Aviso_Nocturno_Resistencia.png",
        f"{DAY}_Caption_Aviso_Nocturno.txt",
    }


def test_the_default_mode_is_the_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    visibility = visibility_fetcher()
    code = main(
        ["--solo-datos"], fetcher=fake_fetcher(data=stormy_table()), visibility_fetcher=visibility,
        now=NOW, notifier=Notifier(),
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "modo" not in payload and "variante" in payload["ciudades"][0]
    assert visibility.calls == []  # the report never asks for the visibility


def test_an_unknown_mode_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--modo", "otro"], now=NOW) == 2
    assert capsys.readouterr().err != ""


def test_same_drive_and_backup_folder_is_written_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "Instagram"
    config = write_config(tmp_path, drive_dir=str(folder), backup_dir=str(tmp_path / "otra" / ".." / "Instagram"))
    assert run(["--sin-aviso"], config_path=config) == 0
    out = capsys.readouterr().out
    assert out.count("Caption:") == 1
    assert out.count("Placa:") == 2


def test_target_constant() -> None:
    assert date.fromisoformat(DAY) == date(2026, 10, 7)
