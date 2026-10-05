"""Shared pytest setup: make the flat modules in ``scripts/verificacion`` importable."""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

PACKAGE_DIR = Path(__file__).resolve().parents[1]
if str(PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGE_DIR))

# Literal fragment of the real SMN ``regtemp`` file, with empty cells and negatives.
REGTEMP_SAMPLE = (
    "FECHA    TMAX  TMIN  NOMBRE\n"
    "-------- ----- ----- ----------------------------------------\n"
    "04102026  22.6  12.2 AEROPARQUE AERO\n"
    "04102026  21.9   5.3 BAHIA BLANCA AERO\n"
    "04102026   9.8   4.2 BARILOCHE AERO\n"
    "04102026 -13.5 -22.3 BASE BELGANO II\n"
    "04102026             BENITO JUAREZ AERO\n"
    "04102026         4.5 BOLIVAR AERO\n"
)


@pytest.fixture
def regtemp_sample() -> str:
    return REGTEMP_SAMPLE


TODAY = dt.date(2026, 10, 5)
SYNTHETIC_START = dt.date(2026, 1, 1)
SYNTHETIC_END = dt.date(2026, 3, 31)


@pytest.fixture(scope="session")
def synthetic_stations():
    from stations import STATIONS_BY_NAME

    names = ("EZEIZA AERO", "AEROPARQUE AERO", "MENDOZA AERO")  # Mendoza is partial_coverage
    return tuple(STATIONS_BY_NAME[n] for n in names)


@pytest.fixture(scope="session")
def synthetic_regtemp_text(synthetic_stations) -> str:
    from fakeworld import regtemp_text

    return regtemp_text(synthetic_stations, SYNTHETIC_START, SYNTHETIC_END)


@pytest.fixture(scope="session")
def measurement(tmp_path_factory, synthetic_stations, synthetic_regtemp_text):
    """Full measurement over the synthetic world (fake API, known windows and biases)."""
    from fakeworld import FakeOpenMeteo
    from openmeteo_client import ClientConfig, OpenMeteoClient
    from pipeline import RunConfig, run_measurement
    from regtemp import parse_regtemp

    config = ClientConfig(tmp_path_factory.mktemp("cache"), max_calls=100, pause_seconds=0.0)
    client = OpenMeteoClient(config, http_get=FakeOpenMeteo(), sleep=lambda _s: None)
    run = RunConfig(synthetic_stations, SYNTHETIC_START, SYNTHETIC_END, chunk_days=30)
    return run_measurement(client, parse_regtemp(synthetic_regtemp_text), run, today=TODAY)
