"""Tests for `alertas_vaciar.py`: the script that empties the push-alert subscriptions in Upstash.

It DELETES production data when run with `--confirmar`, so these tests pin the safety rules: dry-run by
default, the kill key and foreign keys survive, only counts are printed, SCAN is bounded and never KEYS,
commands travel in the body, and a re-run after a mid-way failure finishes the job.

No network: an in-memory fake of the Upstash REST commands (`SCAN`, `DEL`) and a loopback HTTP server.
"""

from __future__ import annotations

import io
from typing import Any

import alertas_vaciar
import pytest
from alertas_vaciar_core import limpieza
from fakes_alertas import (
    ENV,
    FOREIGN,
    KILL_KEY,
    SUB_IDS,
    TOKEN,
    UNKNOWN,
    URL,
    FakeStore,
    assert_clean,
    deletable_keys,
    full_store,
    run,
    survivors,
)

# ---------------------------------------------------------------- classification


def test_classify_deletable_kinds_and_protected_key() -> None:
    assert limpieza.classify("alertas:ids") == "ids"
    assert limpieza.classify("alertas:zonas") == "zonas"
    assert limpieza.classify("alertas:zona:cordoba") == "zona"
    assert limpieza.classify(f"alertas:sub:{SUB_IDS[0]}") == "sub"
    assert limpieza.classify("alertas:enviado:cordoba:2026-10-13") == "enviado"
    assert limpieza.classify(f"alertas:prueba:{SUB_IDS[0]}") == "prueba"
    assert limpieza.classify("alertas:lock:evaluar") == "lock"
    assert limpieza.classify(KILL_KEY) == "protegida"


@pytest.mark.parametrize(
    "key", FOREIGN + UNKNOWN + ["alertas:", "alertas:sub:", "alertas:ids "]
)
def test_classify_never_marks_other_keys_as_deletable(key: str) -> None:
    assert limpieza.classify(key) not in limpieza.DELETABLE_KINDS


# ---------------------------------------------------------------- dry run


def test_default_is_dry_run_and_deletes_nothing() -> None:
    store = full_store()
    before = survivors(store)
    code, out, _ = run(store)
    assert code == 0
    assert survivors(store) == before
    assert store.dels() == []
    assert "SIMULACRO" in out and "--confirmar" in out


def test_dry_run_reports_counts_per_kind() -> None:
    _, out, _ = run(full_store())

    def count_of(label: str) -> str:
        line = next(line for line in out.splitlines() if label in line)
        return line.rsplit(":", 1)[1].strip()

    assert count_of("alertas:sub:*") == "3"
    assert count_of("alertas:zona:*") == "2"
    assert count_of("alertas:enviado:*") == "2"
    assert count_of("alertas:prueba:*") == "3"
    assert count_of("alertas:lock:evaluar") == "1"
    assert count_of("alertas:ids)") == "1"
    assert count_of("alertas:zonas)") == "1"


def test_dry_run_total_matches_the_deletable_keys() -> None:
    _, out, _ = run(full_store())
    assert f"total a borrar: {len(deletable_keys())}" in out


# ---------------------------------------------------------------- confirmar


def test_confirmar_deletes_every_planned_key() -> None:
    store = full_store()
    code, out, _ = run(store, "--confirmar")
    assert code == 0
    assert not any(limpieza.classify(k) in limpieza.DELETABLE_KINDS for k in store.data)
    assert store.deleted_args() == set(deletable_keys())
    assert "BORRADO" in out


def test_kill_key_and_foreign_keys_survive() -> None:
    store = full_store()
    run(store, "--confirmar")
    assert survivors(store) == {KILL_KEY, *FOREIGN, *UNKNOWN}


def test_no_del_command_ever_names_a_non_deletable_key() -> None:
    store = full_store()
    run(store, "--confirmar")
    forbidden = {KILL_KEY, *FOREIGN, *UNKNOWN}
    assert store.deleted_args().isdisjoint(forbidden)
    assert all(
        limpieza.classify(key) in limpieza.DELETABLE_KINDS
        for command in store.dels()
        for key in command[1:]
    )


def test_delete_inventory_refuses_a_plan_with_a_non_deletable_key() -> None:
    store = FakeStore([KILL_KEY, *FOREIGN])
    plan = limpieza.Inventory({"ids": (KILL_KEY,), "sub": (FOREIGN[0],)})
    assert KILL_KEY not in repr(plan)  # key names stay out of repr
    with pytest.raises(limpieza.DeletionInterrupted):
        limpieza.delete_inventory(store, plan)
    assert store.dels() == [] and KILL_KEY in store.data


def test_del_is_batched() -> None:
    ids = [f"alertas:sub:{n:022d}" for n in range(250)]
    store = FakeStore(ids, page=100)
    code, _, _ = run(store, "--confirmar")
    assert code == 0 and store.data == {}
    batches = [len(c) - 1 for c in store.dels()]
    assert len(batches) >= 3 and max(batches) <= limpieza.DEL_BATCH


def test_only_scan_and_del_are_ever_sent_and_scan_is_bounded() -> None:
    store = full_store()
    run(store, "--confirmar")
    assert {c[0].upper() for c in store.commands} == {"SCAN", "DEL"}
    for command in (c for c in store.commands if c[0].upper() == "SCAN"):
        options = {
            command[i].upper(): command[i + 1] for i in range(2, len(command), 2)
        }
        assert options["MATCH"] == "alertas:*"
        assert 1 <= int(options["COUNT"]) <= 1000


def test_endless_cursor_stops_with_error_and_deletes_nothing() -> None:
    store = full_store(endless=True)
    code, _, err = run(store, "--confirmar")
    assert code == 2
    assert store.dels() == []
    scans = [c for c in store.commands if c[0].upper() == "SCAN"]
    assert len(scans) <= limpieza.MAX_SCAN_ITERATIONS
    assert "tope" in err


def test_duplicate_keys_from_scan_are_counted_once() -> None:
    store = full_store(duplicates=True)
    _, out, _ = run(store)
    assert f"total a borrar: {len(deletable_keys())}" in out


def test_final_recount_runs_after_deleting_and_shows_zero() -> None:
    store = full_store()
    code, out, _ = run(store, "--confirmar")
    assert code == 0
    assert (
        store.commands[-1][0].upper() == "SCAN"
    )  # the recount comes after the last DEL
    last_del = max(i for i, c in enumerate(store.commands) if c[0].upper() == "DEL")
    assert any(c[0].upper() == "SCAN" for c in store.commands[last_del + 1 :])
    assert "Recuento final" in out and "quedan por borrar: 0" in out


def test_leftovers_after_deleting_give_nonzero_exit() -> None:
    store = full_store(sticky=("alertas:ids",))
    code, out, _ = run(store, "--confirmar")
    assert code == 1
    assert "quedan por borrar: 1" in out


def test_empty_database_is_ok() -> None:
    store = FakeStore([KILL_KEY] + FOREIGN)
    code, out, _ = run(store, "--confirmar")
    assert code == 0 and store.dels() == []
    assert "total a borrar: 0" in out


# ---------------------------------------------------------------- failures and re-run


def test_midway_failure_reports_progress_exits_2_and_rerun_finishes() -> None:
    ids = [f"alertas:sub:{n:022d}" for n in range(250)] + [
        "alertas:ids",
        "alertas:zonas",
    ]
    store = FakeStore(ids + [KILL_KEY], page=100, fail_on_del=2)
    code, _, err = run(store, "--confirmar")
    assert code == 2
    assert "alcanzaron a borrar: zonas 1" in err
    assert KILL_KEY in store.data and 0 < len(store.data) < len(ids) + 1
    left = len(store.data) - 1

    code2, out2, _ = run(
        store, "--confirmar"
    )  # idempotent: same command finishes the job
    assert code2 == 0
    assert set(store.data) == {KILL_KEY}
    assert f"total a borrar: {left}" in out2


def test_midway_failure_message_has_no_secrets_or_ids() -> None:
    store = full_store(fail_on_del=1)
    _, out, err = run(store, "--confirmar")
    for text in (out, err):
        assert_clean(text)


def test_scan_failure_exits_2_without_secrets() -> None:
    store = full_store(fail_scan_after=0)
    code, out, err = run(store, "--confirmar")
    assert code == 2 and store.dels() == []
    assert_clean(out + err)


def test_recount_failure_exits_2_and_says_it_could_not_verify() -> None:
    probe = full_store()
    first_scans = 0
    run(probe)
    first_scans = len([c for c in probe.commands if c[0].upper() == "SCAN"])
    store = full_store(fail_scan_after=first_scans)
    code, _, err = run(store, "--confirmar")
    assert code == 2
    assert "recuento" in err.lower()


# ---------------------------------------------------------------- privacy


@pytest.mark.parametrize("args", [(), ("--confirmar",)])
def test_output_has_counts_only(args: tuple[str, ...]) -> None:
    _, out, err = run(full_store(), *args)
    assert_clean(out + err)


# ---------------------------------------------------------------- configuration and usage


@pytest.mark.parametrize(
    "environ",
    [
        {},
        {"UPSTASH_REDIS_REST_URL": URL},
        {"UPSTASH_REDIS_REST_TOKEN": TOKEN},
        {"UPSTASH_REDIS_REST_URL": "  ", "UPSTASH_REDIS_REST_TOKEN": TOKEN},
    ],
)
def test_missing_environment_is_a_clear_error_without_traceback(
    environ: dict[str, str],
) -> None:
    code, out, err = run(None, "--confirmar", environ=environ)
    assert code == 3 and out == ""
    assert "UPSTASH_REDIS_REST" in err and "Traceback" not in err
    assert TOKEN not in err and URL not in err


@pytest.mark.parametrize(
    "url",
    ["http://test-instance-1234.upstash.io", "ftp://x.io", "no-es-url", "https://"],
)
def test_non_https_url_is_rejected_without_echoing_it(url: str) -> None:
    code, _, err = run(None, environ={**ENV, "UPSTASH_REDIS_REST_URL": url})
    assert code == 3 and url not in err and TOKEN not in err


def test_does_not_read_a_dotenv_file(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text(
        f"UPSTASH_REDIS_REST_URL={URL}\nUPSTASH_REDIS_REST_TOKEN={TOKEN}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    code, _, err = run(None, environ={})
    assert code == 3 and "UPSTASH_REDIS_REST" in err


def test_default_environment_is_the_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)
    out, err = io.StringIO(), io.StringIO()
    assert alertas_vaciar.main([], stdout=out, stderr=err) == 3


@pytest.mark.parametrize("flag", ["--confirm", "--conf", "-c", "--yes", "confirmar"])
def test_near_miss_flags_never_delete(flag: str) -> None:
    store = full_store()
    code, _, _ = run(store, flag)
    assert code == 3 and store.dels() == [] and store.commands == []
