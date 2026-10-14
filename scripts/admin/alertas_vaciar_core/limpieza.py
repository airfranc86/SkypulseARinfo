"""Inventory and deletion of the push-alert subscription keys (pure logic, no I/O of its own).

Safety rules enforced here, independent of the CLI:

- Only keys that match an explicit allow-list of kinds are ever deleted. The kill key `alertas:apagado`,
  keys outside the `alertas:` prefix and unknown `alertas:*` keys are counted but never touched.
- `is_deletable` is checked again right before every DEL (defence in depth).
- SCAN is bounded (`MAX_SCAN_ITERATIONS`); `KEYS` does not exist in this module.
- Nothing here returns or logs a key name in a message: `Inventory` keeps the names out of `repr()`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

PREFIX = "alertas:"
KILL_KEY = "alertas:apagado"  # emergency switch: NEVER deleted
SCAN_MATCH = "alertas:*"
SCAN_COUNT = 500
MAX_SCAN_ITERATIONS = 1000
DEL_BATCH = 100

PROTECTED = "protegida"
UNKNOWN = "desconocida"
FOREIGN = "ajena"


class UpstashError(Exception):
    """Upstash did not answer as expected. The message is a fixed code, never a URL, key or secret."""


class ScanLimitError(UpstashError):
    """SCAN did not finish within `MAX_SCAN_ITERATIONS` calls."""


class DeletionInterrupted(Exception):
    """Upstash failed while deleting. `deleted` holds the counts per kind reached so far."""

    def __init__(self, deleted: Mapping[str, int], reason: str) -> None:
        super().__init__(reason)
        self.deleted = dict(deleted)
        self.reason = reason


class Commander(Protocol):
    def run(self, *command: str) -> Any:
        """Send one Redis command (as a list in the request body) and return its `result`."""
        ...


@dataclass(frozen=True)
class Kind:
    id: str
    label: str
    pattern: re.Pattern[str]


def _kind(kind_id: str, label: str, pattern: str) -> Kind:
    return Kind(kind_id, label, re.compile(pattern))


# Deletion order: the index sets first (nothing can be resolved to a subscriber any more), then the
# records, then the send marks and the evaluation lock.
KINDS: tuple[Kind, ...] = (
    _kind(
        "zonas", "conjunto de zonas con suscriptores (alertas:zonas)", r"alertas:zonas"
    ),
    _kind("ids", "conjunto de ids de suscripción (alertas:ids)", r"alertas:ids"),
    _kind("zona", "conjuntos por zona (alertas:zona:*)", r"alertas:zona:\S+"),
    _kind("sub", "registros de suscripción (alertas:sub:*)", r"alertas:sub:\S+"),
    _kind("enviado", "marcas de envío (alertas:enviado:*)", r"alertas:enviado:\S+"),
    _kind(
        "prueba", "cupos del aviso de prueba (alertas:prueba:*)", r"alertas:prueba:\S+"
    ),
    _kind("lock", "lock de evaluación (alertas:lock:evaluar)", r"alertas:lock:evaluar"),
)
DELETABLE_KINDS: frozenset[str] = frozenset(kind.id for kind in KINDS)


def classify(key: object) -> str:
    """The kind id of a deletable key, or `protegida` / `ajena` / `desconocida` (all three are never deleted)."""
    if not isinstance(key, str):
        return FOREIGN
    if key == KILL_KEY:
        return PROTECTED
    if not key.startswith(PREFIX):
        return FOREIGN
    for kind in KINDS:
        if kind.pattern.fullmatch(key):
            return kind.id
    return UNKNOWN


def is_deletable(key: object) -> bool:
    return classify(key) in DELETABLE_KINDS


@dataclass(frozen=True)
class Inventory:
    """What a SCAN found: the deletable keys by kind (names kept out of `repr`) and counts of the rest."""

    by_kind: Mapping[str, tuple[str, ...]] = field(repr=False)
    protected: int = 0
    unknown: int = 0

    def count(self, kind_id: str) -> int:
        return len(self.by_kind.get(kind_id, ()))

    def counts(self) -> dict[str, int]:
        return {kind.id: self.count(kind.id) for kind in KINDS}

    @property
    def total(self) -> int:
        return sum(self.counts().values())


def build_inventory(keys: Iterable[str]) -> Inventory:
    grouped: dict[str, list[str]] = {kind.id: [] for kind in KINDS}
    protected = unknown = 0
    for key in sorted(set(keys)):
        kind = classify(key)
        if kind in DELETABLE_KINDS:
            grouped[kind].append(key)
        elif kind == PROTECTED:
            protected += 1
        elif kind == UNKNOWN:
            unknown += 1
    return Inventory({k: tuple(v) for k, v in grouped.items()}, protected, unknown)


def _parse_scan(result: object) -> tuple[str, list[str]]:
    if (
        not isinstance(result, list)
        or len(result) != 2
        or not isinstance(result[0], (str, int))
        or isinstance(result[0], bool)
        or not isinstance(result[1], list)
        or not all(isinstance(key, str) for key in result[1])
    ):
        raise UpstashError("respuesta de SCAN inesperada")
    return str(result[0]), result[1]


def scan_inventory(commander: Commander) -> Inventory:
    """SCAN `alertas:*` to the end, with a hard cap on iterations. Never KEYS.

    Raises:
        UpstashError: Upstash failed or answered something unexpected.
        ScanLimitError: the cursor did not come back to 0 within `MAX_SCAN_ITERATIONS`.
    """
    cursor = "0"
    found: set[str] = set()
    for _ in range(MAX_SCAN_ITERATIONS):
        result = commander.run(
            "SCAN", cursor, "MATCH", SCAN_MATCH, "COUNT", str(SCAN_COUNT)
        )
        cursor, keys = _parse_scan(result)
        found.update(keys)
        if cursor == "0":
            return build_inventory(found)
    raise ScanLimitError("SCAN superó el tope de iteraciones")


def _batches(keys: tuple[str, ...]) -> Iterable[tuple[str, ...]]:
    for start in range(0, len(keys), DEL_BATCH):
        yield keys[start : start + DEL_BATCH]


def delete_inventory(commander: Commander, inventory: Inventory) -> dict[str, int]:
    """DEL the inventory's keys, kind by kind in batches. Returns how many were deleted per kind.

    Raises:
        DeletionInterrupted: Upstash failed part-way; `.deleted` says how far it got. Re-running is safe.
    """
    deleted = {kind.id: 0 for kind in KINDS}
    for kind in KINDS:
        for batch in _batches(inventory.by_kind.get(kind.id, ())):
            if not all(is_deletable(key) for key in batch):
                raise DeletionInterrupted(deleted, "clave no borrable en el plan")
            try:
                removed = commander.run("DEL", *batch)
            except UpstashError as exc:
                raise DeletionInterrupted(deleted, str(exc)) from None
            if isinstance(removed, bool) or not isinstance(removed, int):
                raise DeletionInterrupted(deleted, "respuesta de DEL inesperada")
            deleted[kind.id] += removed
    return deleted
