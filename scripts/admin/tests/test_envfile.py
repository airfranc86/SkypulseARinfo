from __future__ import annotations

from pathlib import Path

import pytest
from fakes import OTHER_SECRET, TEST_TOKEN, TEST_UPSTASH_URL
from monitor_core.envfile import (
    EnvFileError,
    load_env,
    load_env_values,
    parse_env_text,
)


def test_parses_plain_pairs() -> None:
    assert parse_env_text("A=1\nB=dos") == {"A": "1", "B": "dos"}


def test_skips_comments_and_blank_lines() -> None:
    text = "# comment\n\n   \nA=1\n  # indented comment\nB=2\n"
    assert parse_env_text(text) == {"A": "1", "B": "2"}


def test_value_may_contain_equals_signs() -> None:
    assert parse_env_text("TOKEN=abc==\nURL=https://x.io/?a=1&b=2") == {
        "TOKEN": "abc==",
        "URL": "https://x.io/?a=1&b=2",
    }


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('K="valor con espacios"', "valor con espacios"),
        ("K='valor simple'", "valor simple"),
        ('K="con # numeral"', "con # numeral"),
        ('K="', '"'),
        ('K="sin cierre', '"sin cierre'),
        ('K=""', ""),
        ("K=", ""),
    ],
)
def test_quotes_are_stripped_only_when_they_match(line: str, expected: str) -> None:
    assert parse_env_text(line) == {"K": expected}


def test_unquoted_inline_comment_is_dropped() -> None:
    assert parse_env_text("K=valor  # nota") == {"K": "valor"}
    assert parse_env_text("K=abc#sinespacio") == {"K": "abc#sinespacio"}


def test_export_prefix_and_spaces_around_equals() -> None:
    assert parse_env_text("export A=1\nB = 2") == {"A": "1", "B": "2"}


def test_lines_without_equals_are_ignored() -> None:
    assert parse_env_text("basura\nA=1") == {"A": "1"}


def test_windows_line_endings() -> None:
    assert parse_env_text("A=1\r\nB=2\r\n") == {"A": "1", "B": "2"}


def test_last_duplicate_wins() -> None:
    assert parse_env_text("A=1\nA=2") == {"A": "2"}


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "creds.env"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_returns_only_wanted_keys_uppercased(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        f"upstash_redis_rest_url={TEST_UPSTASH_URL}\n"
        f"UPSTASH_REDIS_REST_TOKEN={TEST_TOKEN}\n"
        f"OTHER={OTHER_SECRET}\n",
    )
    values = load_env_values(
        path, ("UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN")
    )
    assert values == {
        "UPSTASH_REDIS_REST_URL": TEST_UPSTASH_URL,
        "UPSTASH_REDIS_REST_TOKEN": TEST_TOKEN,
    }
    assert OTHER_SECRET not in str(values)


def test_load_tolerates_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "bom.env"
    path.write_bytes(b"\xef\xbb\xbfA=1\n")
    assert load_env_values(path, ("A",)) == {"A": "1"}


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-16-be"])
def test_load_decodes_utf16_files_saved_by_powershell(
    tmp_path: Path, encoding: str
) -> None:
    # PowerShell 5 `>` / Out-File writes UTF-16 with a BOM; "utf-16-le/be" get one added here.
    path = tmp_path / "ps.env"
    raw = "A=1\r\nB=dos\r\n".encode(encoding)
    if encoding != "utf-16":
        raw = {"utf-16-le": b"\xff\xfe", "utf-16-be": b"\xfe\xff"}[encoding] + raw
    path.write_bytes(raw)
    assert load_env_values(path, ("A", "B")) == {"A": "1", "B": "dos"}


def test_load_env_also_reports_how_many_variables_the_file_has(tmp_path: Path) -> None:
    path = _write(tmp_path, "A=1\n# nota\nB=2\nC=3\n")
    values, total = load_env(path, ("A",))
    assert values == {"A": "1"}
    assert total == 3


def test_load_missing_file_raises_without_leaking_anything(tmp_path: Path) -> None:
    with pytest.raises(EnvFileError) as info:
        load_env_values(tmp_path / "no-existe.env", ("A",))
    assert "no-existe.env" in str(info.value)


def test_load_omits_wanted_keys_that_are_absent(tmp_path: Path) -> None:
    path = _write(tmp_path, "A=1\n")
    assert load_env_values(path, ("A", "B")) == {"A": "1"}


def test_load_directory_raises_env_file_error(tmp_path: Path) -> None:
    with pytest.raises(EnvFileError):
        load_env_values(tmp_path, ("A",))
