from __future__ import annotations

import pytest
from monitor_core.quotas import (
    TRACKED,
    CounterReading,
    QuotaSpec,
    classify_usage,
    collect_quotas,
    counter_key,
    usage_pct,
)
from monitor_core.status import Status


def test_counter_key_matches_backend_format() -> None:
    assert (
        counter_key("open_meteo", "2026-10-05")
        == "skypulse:open_meteo:counter:2026-10-05"
    )
    assert counter_key("checkwx", "2026-01-31") == "skypulse:checkwx:counter:2026-01-31"


def test_tracked_services_and_configured_limits() -> None:
    by_service = {spec.service: spec.daily_limit for spec in TRACKED}
    assert by_service["open_meteo"] == 10_000
    assert by_service["checkwx"] == 198  # settings.checkwx_daily_limit in apps/backend
    assert by_service["smn_alertas"] is None
    assert by_service["metar_awc"] is None


def test_usage_pct() -> None:
    assert usage_pct(0, 10_000) == 0.0
    assert usage_pct(7_000, 10_000) == 70.0
    assert usage_pct(99, 198) == 50.0


def test_usage_pct_rejects_non_positive_limit() -> None:
    with pytest.raises(ValueError):
        usage_pct(1, 0)


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, Status.OK),
        (699, Status.OK),  # 69,9 %
        (700, Status.WARN),  # 70 %
        (899, Status.WARN),  # 89,9 %
        (900, Status.CRITICAL),  # 90 %
        (1000, Status.CRITICAL),
        (1500, Status.CRITICAL),  # over quota
    ],
)
def test_classify_usage_thresholds_on_a_limit_of_1000(
    count: int, expected: Status
) -> None:
    assert classify_usage(count, 1000) is expected


@pytest.mark.parametrize(
    ("count", "expected"),
    [(138, Status.OK), (139, Status.WARN), (178, Status.WARN), (179, Status.CRITICAL)],
)
def test_classify_usage_on_checkwx_limit(count: int, expected: Status) -> None:
    # 138/198 = 69,7 %; 139/198 = 70,2 %; 178/198 = 89,9 %; 179/198 = 90,4 %
    assert classify_usage(count, 198) is expected


def test_classify_usage_without_limit_is_always_ok() -> None:
    assert classify_usage(10**9, None) is Status.OK


class FakeReader:
    def __init__(self, readings: dict[str, CounterReading]) -> None:
        self._readings = readings
        self.keys: list[str] = []

    def read_counter(self, key: str) -> CounterReading:
        self.keys.append(key)
        return self._readings.get(
            key, CounterReading(count=0, present=False, error=None)
        )


def _key(service: str) -> str:
    return counter_key(service, "2026-10-05")


def test_collect_quotas_reads_one_key_per_tracked_service() -> None:
    reader = FakeReader({})
    section = collect_quotas(reader, "2026-10-05")
    assert reader.keys == [_key(spec.service) for spec in TRACKED]
    assert len(section.rows) == len(TRACKED)


def test_missing_keys_count_as_zero_and_stay_ok() -> None:
    section = collect_quotas(FakeReader({}), "2026-10-05")
    assert section.status is Status.OK
    assert all(row.count == 0 and not row.present for row in section.rows)
    assert not section.unavailable


def test_collect_quotas_flags_attention_and_critical() -> None:
    readings = {
        _key("open_meteo"): CounterReading(7_500, True, None),  # 75 %
        _key("checkwx"): CounterReading(190, True, None),  # 96 %
    }
    section = collect_quotas(FakeReader(readings), "2026-10-05")
    rows = {row.service: row for row in section.rows}
    assert rows["open_meteo"].status is Status.WARN
    assert rows["checkwx"].status is Status.CRITICAL
    assert section.status is Status.CRITICAL
    assert rows["open_meteo"].pct == 75.0


def test_unlimited_services_show_count_without_percentage() -> None:
    readings = {_key("metar_awc"): CounterReading(321, True, None)}
    section = collect_quotas(FakeReader(readings), "2026-10-05")
    row = next(r for r in section.rows if r.service == "metar_awc")
    assert row.count == 321
    assert row.pct is None
    assert row.status is Status.OK


def test_upstash_down_is_reported_not_raised() -> None:
    class DownReader:
        calls = 0

        def read_counter(self, key: str) -> CounterReading:
            DownReader.calls += 1
            return CounterReading(
                count=0, present=False, error="sin respuesta (TimeoutError)"
            )

    section = collect_quotas(DownReader(), "2026-10-05")
    assert section.unavailable
    assert section.status is Status.WARN
    assert "sin respuesta" in section.summary
    assert DownReader.calls == 1  # stops at the first failure: no pointless retries


def test_custom_specs_are_honoured() -> None:
    specs = (QuotaSpec("x", "Equis", 10),)
    section = collect_quotas(
        FakeReader({_key("x"): CounterReading(9, True, None)}), "2026-10-05", specs
    )
    assert section.rows[0].status is Status.CRITICAL
