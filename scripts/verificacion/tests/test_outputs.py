"""Tests for resumen.md, CSV files and metadatos.json."""

from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

import pytest

from outputs import build_metadata, render_summary, write_outputs

NOW = dt.datetime(2026, 10, 5, 12, 0, tzinfo=dt.UTC)


@pytest.fixture
def metadata(measurement):
    return build_metadata(
        measurement, http_calls=6, cache_hits=0, chunk_days=30, regtemp_file="regtemp.txt", now=NOW
    )


def test_summary_has_the_expected_sections_in_spanish(measurement, metadata) -> None:
    text = render_summary(measurement, metadata)

    for heading in (
        "# Verificación de Tmax/Tmin",
        "## Advertencias",
        "## Ventana horaria del SMN",
        "## Cobertura por estación",
        "## Resultados sin ajuste",
        "## Validación cruzada de 2 pliegues",
        "### Pliegue 1",
        "### Pliegue 2",
        "## Estaciones que mejoran frente a mean",
    ):
        assert heading in text
    assert "| Variable | Anticipación (días) | Modelo | Estación del año | n |" in text
    assert "MENDOZA AERO" in text and "parcial" in text.lower()
    assert "mean_bias_corrected" in text and "mean_inverse_mae" in text


def test_summary_reports_chosen_windows_and_model_agreement(measurement, metadata) -> None:
    text = render_summary(measurement, metadata)

    assert "03Z" in text and "D-1 21Z" in text
    assert "coinciden" in text.lower()


def test_metadata_content(measurement, metadata) -> None:
    assert metadata["fecha_corrida"] == "2026-10-05T12:00:00+00:00"
    assert metadata["ventanas"]["tmax"]["nombre"] == "03Z"
    assert metadata["ventanas"]["tmin"] == {
        "nombre": "D-1 21Z", "hora_inicio_utc": 21, "desfase_dias": -1,
        "horas": 24, "forzada": False,
    }  # fmt: skip
    assert metadata["modelos"] == {"ecmwf": "ecmwf_ifs025", "gfs": "gfs_global"}
    assert metadata["llamadas_http"] == 6 and metadata["llamadas_cache"] == 0
    assert metadata["periodo"] == {"inicio": "2026-01-01", "fin": "2026-03-31"}
    assert [e["icao"] for e in metadata["estaciones"]] == ["SAEZ", "SABE", "SAME"]
    assert metadata["estaciones"][2]["parcial"] is True
    assert "parametros_version" in metadata


def test_write_outputs_creates_all_files(tmp_path: Path, measurement, metadata) -> None:
    out = tmp_path / "resultados"

    paths = write_outputs(measurement, out, metadata)

    assert {p.name for p in paths} == {
        "resumen.md", "errores_por_caso.csv", "errores_por_estacion.csv", "metadatos.json",
    }  # fmt: skip
    assert json.loads((out / "metadatos.json").read_text(encoding="utf-8")) == json.loads(
        json.dumps(metadata)
    )


def test_case_csv_has_one_row_per_fold_record(tmp_path: Path, measurement, metadata) -> None:
    write_outputs(measurement, tmp_path, metadata)

    with (tmp_path / "errores_por_caso.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert list(rows[0]) == [
        "pliegue", "estacion", "fecha", "anticipacion_dias", "variable", "modelo",
        "pronostico", "observado", "error",
    ]  # fmt: skip
    assert len(rows) == sum(len(f.records) for f in measurement.folds)
    assert {r["pliegue"] for r in rows} == {"fold_1", "fold_2"}
    first = rows[0]
    assert float(first["error"]) == pytest.approx(
        float(first["pronostico"]) - float(first["observado"]), abs=2e-3
    )


def test_station_csv_columns_and_rows(tmp_path: Path, measurement, metadata) -> None:
    write_outputs(measurement, tmp_path, metadata)

    with (tmp_path / "errores_por_estacion.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert list(rows[0]) == [
        "pliegue", "estacion", "variable", "anticipacion_dias", "modelo", "n",
        "mae_modelo", "mae_mean", "diferencia", "mejora_umbral",
    ]  # fmt: skip
    expected = sum(len(s.by_lead.deltas) for s in measurement.fold_summaries)
    assert len(rows) == expected
    assert {r["mejora_umbral"] for r in rows} <= {"si", "no"}


def test_outputs_contain_no_absolute_paths_or_credentials(
    tmp_path: Path, measurement, metadata
) -> None:
    out = tmp_path / "salida"
    write_outputs(measurement, out, metadata)

    for path in out.iterdir():
        text = path.read_text(encoding="utf-8")
        assert str(tmp_path) not in text
        assert "C:\\" not in text and "G:\\" not in text and "/Users/" not in text
        assert "apikey" not in text.lower()
