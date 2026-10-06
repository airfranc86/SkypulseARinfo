from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from monitor_core.report import Report, redact, skipped_section, to_jsonable
from monitor_core.status import (
    EXIT_CRITICAL,
    EXIT_OK,
    EXIT_USAGE,
    EXIT_WARN,
    Status,
    exit_code,
    worst,
)


def test_worst_picks_the_highest_severity_and_ignores_none() -> None:
    assert worst([Status.OK, None, Status.WARN]) is Status.WARN
    assert worst([Status.OK, Status.CRITICAL, Status.WARN]) is Status.CRITICAL
    assert worst([]) is Status.OK
    assert worst([None]) is Status.OK


def test_exit_codes() -> None:
    assert (EXIT_OK, EXIT_WARN, EXIT_CRITICAL, EXIT_USAGE) == (0, 1, 2, 3)
    assert exit_code(Status.OK) == 0
    assert exit_code(Status.WARN) == 1
    assert exit_code(Status.CRITICAL) == 2


@dataclass(frozen=True)
class _Inner:
    when: datetime
    status: Status
    values: tuple[int, ...]
    missing: str | None = None


def test_to_jsonable_handles_dataclasses_enums_dates_and_tuples() -> None:
    obj = _Inner(datetime(2026, 10, 5, 14, 0, tzinfo=UTC), Status.WARN, (1, 2))
    data = to_jsonable(obj)
    assert data == {
        "when": "2026-10-05T14:00:00+00:00",
        "status": "warn",
        "values": [1, 2],
        "missing": None,
    }
    json.dumps(data)  # must be serialisable


def test_to_jsonable_rounds_floats_to_three_decimals() -> None:
    assert to_jsonable({"latency_s": 0.4444989000003261, "pct": 69.9}) == {
        "latency_s": 0.444,
        "pct": 69.9,
    }


def test_redact_replaces_every_occurrence() -> None:
    text = "token=SECRET-ABCDEF and again SECRET-ABCDEF"
    cleaned = redact(text, ["SECRET-ABCDEF"])
    assert "SECRET-ABCDEF" not in cleaned
    assert cleaned.count("***") == 2


def test_redact_ignores_empty_and_very_short_secrets() -> None:
    assert redact("a b c", ["", "a"]) == "a b c"


def test_redact_longest_secret_first() -> None:
    cleaned = redact("xx-SECRETLONG-yy", ["SECRET", "SECRETLONG"])
    assert "SECRET" not in cleaned


def test_skipped_section_marks_reason() -> None:
    section = skipped_section("quotas", "Cupos del día", "falta --env-file")
    assert section.skipped and section.status is None
    assert "falta --env-file" in section.summary
    assert to_jsonable(section)["skipped"] is True


def test_report_overall_ignores_skipped_sections() -> None:
    skipped = skipped_section("quotas", "Cupos", "x")
    report = Report(datetime(2026, 10, 5, tzinfo=UTC), (skipped,))
    assert report.overall is Status.OK
    assert to_jsonable(report)["exit_code"] == 0
