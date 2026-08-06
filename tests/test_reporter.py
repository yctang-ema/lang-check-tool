"""Tests for the reporter module."""

from src.reporter import _sanitize_csv_field


def test_sanitize_csv_leading_equals():
    assert _sanitize_csv_field("=cmd|'/C calc'!A0") == "'=cmd|'/C calc'!A0"


def test_sanitize_csv_leading_plus():
    assert _sanitize_csv_field("+1+1") == "'+1+1"


def test_sanitize_csv_leading_minus():
    assert _sanitize_csv_field("-123") == "'-123"


def test_sanitize_csv_leading_at():
    assert _sanitize_csv_field("@SUM(A1)") == "'@SUM(A1)"


def test_sanitize_csv_safe_text():
    assert _sanitize_csv_field("Hello world") == "Hello world"


def test_sanitize_csv_non_string():
    assert _sanitize_csv_field(42) == 42
    assert _sanitize_csv_field(None) is None
