"""In-memory AWC source for tests: serves canned JSON, never touches the network or the usage counter.

Install it with the `awc_fixtures` fixture of `conftest.py`, which swaps the active source and puts
the HTTP one back at the end of the test. Tests that must exercise the real HTTP adapter (headers,
params, counter) keep using `respx` instead.
"""
from __future__ import annotations

import copy
from typing import Any

from app.services.reportes_aeronauticos.awc import AwcError


class FixtureAwcSource:
    """`AwcSource` that answers from `metar={icao: json}` / `taf={icao: json}`.

    An ICAO without a fixture gets `[]` (what AWC sends when a station has no report).
    `fail=True` makes every call raise `AwcError`, like a network or HTTP failure.
    Every call is appended to `calls` as `(kind, icao, hours_or_None, timeout)`.
    """

    def __init__(
        self,
        metar: dict[str, Any] | None = None,
        taf: dict[str, Any] | None = None,
        fail: bool = False,
    ) -> None:
        self._metar = dict(metar or {})
        self._taf = dict(taf or {})
        self.fail = fail
        self.calls: list[tuple[str, str, int | None, float]] = []

    async def metar(self, icao: str, *, hours: int, timeout: float) -> Any:
        self.calls.append(("metar", icao, hours, timeout))
        return self._answer(self._metar, icao)

    async def taf(self, icao: str, *, timeout: float) -> Any:
        self.calls.append(("taf", icao, None, timeout))
        return self._answer(self._taf, icao)

    def _answer(self, fixtures: dict[str, Any], icao: str) -> Any:
        if self.fail:
            raise AwcError("FixtureAwcSource: forced failure")
        return copy.deepcopy(fixtures.get(icao, []))
