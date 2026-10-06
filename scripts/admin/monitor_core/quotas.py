"""Section 1: today's upstream-call counters (written by the backend in Upstash).

The backend increments `skypulse:<service>:counter:YYYY-MM-DD` (UTC day) for each
upstream call (see apps/backend/app/core/usage_counter.py and counter.py). Here they
are only read.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from monitor_core.render import fmt_int, fmt_pct
from monitor_core.status import Status, worst

WARN_PCT = 70
CRITICAL_PCT = 90


@dataclass(frozen=True)
class QuotaSpec:
    service: str
    label: str
    daily_limit: int | None  # None: counted by the backend but with no quota of its own


# Open-Meteo free tier: fewer than 10,000 calls per day. CheckWX: 198 (checkwx_daily_limit in
# apps/backend/app/core/config.py; the free plan allows 200). The two others are informative.
TRACKED: tuple[QuotaSpec, ...] = (
    QuotaSpec("open_meteo", "Open-Meteo", 10_000),
    QuotaSpec("checkwx", "CheckWX", 198),
    QuotaSpec("smn_alertas", "SMN avisos", None),
    QuotaSpec("metar_awc", "AWC METAR", None),
)


@dataclass(frozen=True)
class CounterReading:
    """One counter read. A missing key is `count=0, present=False, error=None`."""

    count: int
    present: bool
    error: str | None


class CounterReader(Protocol):
    def read_counter(self, key: str) -> CounterReading: ...


@dataclass(frozen=True)
class QuotaRow:
    service: str
    label: str
    count: int
    limit: int | None
    pct: float | None
    status: Status
    present: bool
    error: str | None


@dataclass(frozen=True)
class QuotasSection:
    day: str
    rows: tuple[QuotaRow, ...]
    status: Status
    summary: str
    unavailable: bool


def counter_key(service: str, day: str) -> str:
    return f"skypulse:{service}:counter:{day}"


def usage_pct(count: int, limit: int) -> float:
    if limit <= 0:
        raise ValueError("limit must be positive")
    return count * 100 / limit


def classify_usage(count: int, limit: int | None) -> Status:
    """OK below 70 %, ATENCIÓN from 70 %, CRÍTICO from 90 % (integer math: no float edge cases)."""
    if limit is None:
        return Status.OK
    if limit <= 0:
        raise ValueError("limit must be positive")
    if count * 100 >= limit * CRITICAL_PCT:
        return Status.CRITICAL
    if count * 100 >= limit * WARN_PCT:
        return Status.WARN
    return Status.OK


def _row(spec: QuotaSpec, reading: CounterReading) -> QuotaRow:
    if reading.error is not None:
        return QuotaRow(
            spec.service,
            spec.label,
            0,
            spec.daily_limit,
            None,
            Status.WARN,
            False,
            reading.error,
        )
    limit = spec.daily_limit
    pct = usage_pct(reading.count, limit) if limit else None
    status = classify_usage(reading.count, limit)
    return QuotaRow(
        spec.service,
        spec.label,
        reading.count,
        limit,
        pct,
        status,
        reading.present,
        None,
    )


def _summary(rows: Sequence[QuotaRow], failure: str | None, unavailable: bool) -> str:
    if unavailable:
        return f"Upstash: {failure}"
    flagged = [
        f"{row.label} {fmt_pct(row.pct)}"
        if row.pct is not None
        else f"{row.label} sin lectura"
        for row in rows
        if row.status is not Status.OK
    ]
    if flagged:
        return "; ".join(flagged) + (f" · Upstash: {failure}" if failure else "")
    measured = sum(1 for row in rows if row.limit is not None)
    return f"{measured} servicios con cupo dentro de lo normal ({fmt_int(sum(r.count for r in rows))} llamadas hoy)"


def collect_quotas(
    reader: CounterReader, day: str, specs: Sequence[QuotaSpec] = TRACKED
) -> QuotasSection:
    """Read one counter per service; stop at the first Upstash failure (no pointless retries)."""
    rows: list[QuotaRow] = []
    failure: str | None = None
    for spec in specs:
        if failure is not None:
            rows.append(_row(spec, CounterReading(0, False, "no consultado")))
            continue
        reading = reader.read_counter(counter_key(spec.service, day))
        failure = reading.error
        rows.append(_row(spec, reading))
    unavailable = failure is not None and not any(r.error is None for r in rows)
    return QuotasSection(
        day=day,
        rows=tuple(rows),
        status=worst(row.status for row in rows),
        summary=_summary(rows, failure, unavailable),
        unavailable=unavailable,
    )
