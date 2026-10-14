"""Test doubles for the `alertas_vaciar` tests: constants, deletable-key builder and an in-memory Upstash.

Nothing here touches the network or real credentials.
"""

from __future__ import annotations

import fnmatch
import io
import json
from collections.abc import Mapping
from typing import Any

import alertas_vaciar
from alertas_vaciar_core.limpieza import UpstashError

TOKEN = "tok_TEST_0123456789_do_not_leak"
URL = "https://test-instance-1234.upstash.io"
ENV = {"UPSTASH_REDIS_REST_URL": URL, "UPSTASH_REDIS_REST_TOKEN": TOKEN}

SUB_IDS = ["AbCdEfGhIjKlMnOpQrStUv", "ZyXwVuTsRqPoNmLkJiHgFe", "0123456789abcdefghijkl"]
SLUGS = ["cordoba", "caba"]
ENDPOINT = "https://fcm.googleapis.com/fcm/send/secret-endpoint-token"
KILL_KEY = "alertas:apagado"
FOREIGN = [
    "skypulse:open_meteo:counter:2026-10-05",
    "otro:alertas:ids",
    "Alertas:ids",
    "alertas_ids",
    "sesion:abc",
]
UNKNOWN = ["alertas:futura:clave", "alertas:apagado:copia"]


def deletable_keys() -> list[str]:
    keys = ["alertas:ids", "alertas:zonas", "alertas:lock:evaluar"]
    keys += [f"alertas:sub:{i}" for i in SUB_IDS]
    keys += [f"alertas:zona:{s}" for s in SLUGS]
    keys += [f"alertas:enviado:{s}:2026-10-13" for s in SLUGS]
    keys += [f"alertas:prueba:{i}" for i in SUB_IDS]
    return keys


class FakeStore:
    """In-memory Upstash: understands SCAN (paginated) and DEL only; anything else raises."""

    def __init__(
        self,
        keys: list[str],
        *,
        page: int = 4,
        fail_on_del: int | None = None,
        fail_scan_after: int | None = None,
        sticky: tuple[str, ...] = (),
        endless: bool = False,
        duplicates: bool = False,
    ) -> None:
        self.data: dict[str, str] = {
            k: json.dumps({"endpoint": ENDPOINT}) for k in keys
        }
        self.commands: list[tuple[str, ...]] = []
        self.page = page
        self.fail_on_del = fail_on_del
        self.fail_scan_after = fail_scan_after
        self.sticky = set(sticky)
        self.endless = endless
        self.duplicates = duplicates
        self._dels = 0
        self._scans = 0

    def run(self, *command: str) -> Any:
        self.commands.append(command)
        name = command[0].upper()
        if name == "SCAN":
            return self._scan(command)
        if name == "DEL":
            return self._del(command[1:])
        raise AssertionError(f"unexpected command {name}")

    def _scan(self, command: tuple[str, ...]) -> Any:
        self._scans += 1
        if self._scans > 5000:  # an unbounded SCAN loop must fail the test, not hang it
            raise AssertionError("runaway SCAN loop")
        if self.fail_scan_after is not None and self._scans > self.fail_scan_after:
            raise UpstashError("HTTP 500")
        if self.endless:
            return ["17", []]
        options = {
            command[i].upper(): command[i + 1] for i in range(2, len(command), 2)
        }
        pattern = options["MATCH"]
        names = sorted(k for k in self.data if fnmatch.fnmatchcase(k, pattern))
        start = int(command[1])
        chunk = names[start : start + self.page]
        nxt = start + self.page
        if self.duplicates:
            chunk = chunk + chunk
        return ["0" if nxt >= len(names) else str(nxt), chunk]

    def _del(self, keys: tuple[str, ...]) -> int:
        self._dels += 1
        if self.fail_on_del == self._dels:
            self.fail_on_del = None
            raise UpstashError("HTTP 500")
        removed = 0
        for key in keys:
            if key in self.sticky:
                continue
            if self.data.pop(key, None) is not None:
                removed += 1
        return removed

    def dels(self) -> list[tuple[str, ...]]:
        return [c for c in self.commands if c[0].upper() == "DEL"]

    def deleted_args(self) -> set[str]:
        return {key for command in self.dels() for key in command[1:]}


def run(
    store: FakeStore | None,
    *argv: str,
    environ: Mapping[str, str] | None = None,
) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = alertas_vaciar.main(
        list(argv),
        environ=ENV if environ is None else environ,
        stdout=out,
        stderr=err,
        commander=store,
    )
    return code, out.getvalue(), err.getvalue()


def full_store(**kwargs: Any) -> FakeStore:
    return FakeStore(deletable_keys() + [KILL_KEY] + FOREIGN + UNKNOWN, **kwargs)


def survivors(store: FakeStore) -> set[str]:
    return set(store.data)


def assert_clean(text: str) -> None:
    for secret in (TOKEN, URL, "test-instance-1234", ENDPOINT, "secret-endpoint-token"):
        assert secret not in text
    for sub_id in SUB_IDS:
        assert sub_id not in text
    for slug in SLUGS:
        assert f":{slug}" not in text
    assert "https://" not in text and "Traceback" not in text
    for key in FOREIGN:
        assert key not in text
