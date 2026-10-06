"""Report container, JSON conversion and the last-line secret redaction."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from monitor_core.status import Status, worst
from monitor_core.status import exit_code as exit_code_for

JSON_DECIMALS = 3
MIN_SECRET_LENGTH = 4
REDACTED = "***"


def to_jsonable(obj: Any) -> Any:
    """Dataclasses, enums, datetimes and tuples -> plain JSON types (enums as lowercase names)."""
    if hasattr(obj, "__json__"):
        return obj.__json__()
    if isinstance(obj, Enum):
        return obj.name.lower()
    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, float):
        return round(obj, JSON_DECIMALS)
    if isinstance(obj, Mapping):
        return {str(key): to_jsonable(value) for key, value in obj.items()}
    if isinstance(obj, list | tuple | set | frozenset):
        return [to_jsonable(item) for item in obj]
    return obj


def redact(text: str, secrets: Iterable[str]) -> str:
    """Replace every occurrence of each secret (longest first); ignores very short ones."""
    usable = sorted(
        {s for s in secrets if len(s) >= MIN_SECRET_LENGTH}, key=len, reverse=True
    )
    for secret in usable:
        text = text.replace(secret, REDACTED)
    return text


@dataclass(frozen=True)
class SectionEntry:
    """One report section: its outcome plus the structured detail (None when skipped)."""

    key: str
    title: str
    status: Status | None
    summary: str
    skipped: bool = False
    detail: Any | None = None

    def __json__(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "title": self.title,
            "skipped": self.skipped,
            "status": to_jsonable(self.status),
            "summary": self.summary,
        }
        if self.detail is not None:
            data.update(
                {k: v for k, v in to_jsonable(self.detail).items() if k not in data}
            )
        return data


def skipped_section(key: str, title: str, reason: str) -> SectionEntry:
    return SectionEntry(key, title, None, reason, skipped=True)


def section_entry(key: str, title: str, detail: Any) -> SectionEntry:
    """Wrap a section result that exposes `.status` and `.summary`."""
    return SectionEntry(key, title, detail.status, detail.summary, detail=detail)


@dataclass(frozen=True)
class Report:
    generated_at: datetime
    sections: tuple[SectionEntry, ...]

    @property
    def overall(self) -> Status:
        return worst(section.status for section in self.sections)

    @property
    def exit_code(self) -> int:
        return exit_code_for(self.overall)

    def __json__(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "overall": to_jsonable(self.overall),
            "exit_code": self.exit_code,
            "sections": {
                section.key: to_jsonable(section) for section in self.sections
            },
        }
