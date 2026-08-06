"""Tests for the detector module."""

from src.detector import _normalize_text, is_ignored, load_ignore_phrases
from pathlib import Path


def test_normalize_smart_quotes():
    text = "World\u2019s Best Bank"
    assert _normalize_text(text) == "World's Best Bank"


def test_normalize_double_smart_quotes():
    text = '\u201cHello\u201d'
    assert _normalize_text(text) == '"Hello"'


def test_normalize_em_dash():
    text = "Hello\u2014World"
    assert _normalize_text(text) == "Hello-World"


def test_is_ignored_exact_match():
    phrases = {"world's best bank", "liberté"}
    assert is_ignored("World's Best Bank", phrases) is True
    assert is_ignored("Something else", phrases) is False


def test_load_ignore_phrases(tmp_path: Path):
    file = tmp_path / "ignore_phrases.txt"
    file.write_text("phrase one\nphrase two\n")
    phrases = load_ignore_phrases(tmp_path)
    assert "phrase one" in phrases
    assert "phrase two" in phrases
    assert "missing" not in phrases
