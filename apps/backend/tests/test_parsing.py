"""Tests for app/utils/parsing.py"""
import pytest
from app.utils.parsing import parse_float


@pytest.mark.parametrize("value,expected", [
    (None, None),
    (3.14, 3.14),
    ("2.5", 2.5),
    (0, 0.0),
    ("abc", None),      # ValueError branch
    ([1, 2], None),     # TypeError branch
])
def test_parse_float(value, expected):
    assert parse_float(value) == expected
