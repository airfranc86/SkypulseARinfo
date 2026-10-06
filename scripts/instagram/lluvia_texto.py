"""The single decision about what the report says of the rain (pure: no I/O, no formatting).

The plate and the caption both read it, so they can never disagree; each one only words it for its
medium. Same rule as the 7-day row of the web (`apps/frontend/src/lib/forecastRow.ts`):

- ``lluvia``: the day rains (more than 0.9 mm): probability, amount and, when there is one, the
  critical window ("más intensa de ..."). When the daily total and the ECMWF hours contradict each
  other the amount is the greater of the two, said as a bound: ``qualifier`` is "hasta".
- ``poca``: it does not reach 0.9 mm but the probability is above 15 %: "poca cantidad".
- ``seco``: it does not reach 0.9 mm and the probability is 15 % or less (or unknown): "Sin lluvia".
- ``None``: the amount is unknown, nothing is said.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from reglas import Assessment, round_half_up
from tipos import ReportData

RainKind = Literal["lluvia", "poca", "seco"]

# Like the 7-day row of the web: above this probability a dry day still mentions the rain.
RAIN_MIN_PROB = 15.0
SMALL_AMOUNT = "poca cantidad"
DRY = "Sin lluvia"
BOUND_WORD = "hasta"  # "hasta 25 mm": the amount is a bound, not an estimate


@dataclass(frozen=True)
class RainSummary:
    kind: RainKind
    prob_pct: int | None  # rounded probability; None on a dry day or when unknown
    mm: float | None  # only when it rains
    window: str | None  # "09:00 a 15:00 hs", only when it rains and there is a critical slot
    heavy: bool
    bound: bool = False
    qualifier: str | None = None  # word before the amount on plate and caption ("hasta"); None: as is


def rain_summary(data: ReportData, result: Assessment) -> RainSummary | None:
    """What the report says of the rain of one day; `result` is ``assess(data)``."""
    if result.rain is not None:
        rain = result.rain
        qualifier = BOUND_WORD if rain.bound else None
        return RainSummary("lluvia", rain.prob_pct, rain.mm, rain.window, rain.heavy, rain.bound, qualifier)
    if not result.dry:
        return None
    if data.precip_prob is not None and data.precip_prob > RAIN_MIN_PROB:
        return RainSummary("poca", round_half_up(data.precip_prob), None, None, False)
    return RainSummary("seco", None, None, None, False)
