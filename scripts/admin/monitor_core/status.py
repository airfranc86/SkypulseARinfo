"""Severity levels and process exit codes."""

from __future__ import annotations

from collections.abc import Iterable
from enum import IntEnum

EXIT_OK = 0
EXIT_WARN = 1
EXIT_CRITICAL = 2
EXIT_USAGE = 3


class Status(IntEnum):
    """Ordered severity: a higher value is worse."""

    OK = 0
    WARN = 1
    CRITICAL = 2

    @property
    def label(self) -> str:
        return _LABELS[self]


_LABELS = {Status.OK: "OK", Status.WARN: "ATENCIÓN", Status.CRITICAL: "CRÍTICO"}


def worst(statuses: Iterable[Status | None]) -> Status:
    """Highest severity among the given ones; `None` (skipped sections) is ignored."""
    return max((s for s in statuses if s is not None), default=Status.OK)


def exit_code(status: Status) -> int:
    return {Status.OK: EXIT_OK, Status.WARN: EXIT_WARN, Status.CRITICAL: EXIT_CRITICAL}[
        status
    ]
