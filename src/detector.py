"""Detector module: language detection using fasttext."""

import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Set, Tuple

import fasttext

if TYPE_CHECKING:
    # fasttext.load_model() actually returns an instance of the private
    # `_FastText` class (see fasttext/FastText.py). `fasttext.FastText` is
    # the *module* the class lives in, not the class itself, so using it
    # directly as a type annotation is incorrect and will be flagged by
    # static type checkers (Pylance/mypy). Import the real class only for
    # type-checking purposes, and expose it under a public-looking alias.
    from fasttext.FastText import _FastText as FastTextModel
else:
    FastTextModel = object

# fasttext small model (~1 MB)
MODEL_URL = "https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.ftz"
MODEL_FILENAME = "lid.176.ftz"


# Map typographic Unicode characters to ASCII equivalents
# This prevents false positives caused by smart quotes, em-dashes, etc.
_UNICODE_NORMALIZATION = str.maketrans(
    {
        "\u2018": "'",  # left single quotation mark
        "\u2019": "'",  # right single quotation mark
        "\u201a": "'",  # single low-9 quotation mark
        "\u201b": "'",  # single high-reversed-9 quotation mark
        "\u201c": '"',  # left double quotation mark
        "\u201d": '"',  # right double quotation mark
        "\u201e": '"',  # double low-9 quotation mark
        "\u201f": '"',  # double high-reversed-9 quotation mark
        "\u2013": "-",  # en dash
        "\u2014": "-",  # em dash
        "\u2026": "...",  # horizontal ellipsis
        "\u00a0": " ",  # non-breaking space
    }
)


def _normalize_text(text: str) -> str:
    """Normalize typographic Unicode characters to ASCII equivalents.

    Smart quotes and special dashes can trick language detectors into
    misidentifying English text as German, French, etc.
    """
    return text.translate(_UNICODE_NORMALIZATION)


def _get_model_path() -> Path:
    """Return the local path where the fasttext model is stored."""
    cache_dir = Path.home() / ".cache" / "lang-check-tool"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / MODEL_FILENAME


def _download_model(model_path: Path) -> None:
    """Download the fasttext model if it does not exist locally.

    Uses an atomic write (download to a temp file first, then rename)
    so that an interrupted download never leaves a corrupt file in the
    cache that would crash on the next run.
    """
    if model_path.exists():
        return
    temp_path = model_path.with_suffix(".tmp")
    print(f"Downloading fasttext model to {model_path} ...")
    try:
        urllib.request.urlretrieve(MODEL_URL, temp_path)
        temp_path.rename(model_path)
        print("Model downloaded.")
    except Exception:
        # Clean up partial download on failure so the next run retries.
        if temp_path.exists():
            temp_path.unlink()
        raise


def load_detector() -> "FastTextModel":
    """Load (and download if necessary) the fasttext language detector.

    Returns:
        A fasttext model instance.
    """
    model_path = _get_model_path()
    _download_model(model_path)
    return fasttext.load_model(str(model_path))


def detect_language(
    detector: "FastTextModel", text: str
) -> Tuple[Optional[str], float]:
    """Detect the language of a text snippet.

    Args:
        detector: Loaded fasttext model.
        text: The text to analyse.

    Returns:
        A tuple of (two-letter ISO language code, confidence score).
        Returns (None, 0.0) if detection fails.
    """
    if not text or not text.strip():
        return None, 0.0

    normalized = _normalize_text(text).replace("\n", " ")

    # fasttext expects a single string; labels are like __label__en
    predictions = detector.predict(normalized, k=1)
    label = predictions[0][0]
    prob = float(predictions[1][0])

    if isinstance(label, bytes):
        label = label.decode("utf-8")

    lang = label.replace("__label__", "").split("_")[0]
    return lang, prob


def load_ignore_phrases(output_dir: Path) -> Set[str]:
    """Load user-supplied phrases to ignore.

    Args:
        output_dir: Directory where ignore_phrases.txt may exist.

    Returns:
        Set of lower-cased phrases to skip during detection.
    """
    ignore_file = output_dir / "ignore_phrases.txt"
    if not ignore_file.exists():
        return set()
    phrases = set()
    with open(ignore_file, "r", encoding="utf-8") as f:
        for line in f:
            phrase = line.strip()
            if phrase:
                phrases.add(phrase.lower())
    return phrases


def is_ignored(text: str, ignore_phrases: Set[str]) -> bool:
    """Check whether the text exactly matches an ignored phrase.

    Args:
        text: The text block to check.
        ignore_phrases: Set of ignored phrases.

    Returns:
        True if the text should be skipped.
    """
    lowered = text.strip().lower()
    return lowered in ignore_phrases
