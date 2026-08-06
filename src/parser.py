"""Parser module: extract text blocks and page language from HTML."""

import re
from typing import List, Optional, Dict, Any

from bs4 import BeautifulSoup, NavigableString


# Content-area selectors to try in order
CONTENT_SELECTORS = ["main", "article", ".content", "#content"]

# Tags to skip entirely
SKIP_TAGS = {"script", "style", "nav", "header", "footer"}

# Inline tags that should not prevent a parent from being treated as a text block
INLINE_TAGS = {
    "span", "a", "strong", "em", "b", "i", "small", "mark", "del", "ins",
    "sub", "sup", "code", "abbr", "dfn", "time", "q", "cite", "br", "wbr",
    "img", "picture", "source", "video", "audio", "label", "figcaption",
}


def get_page_lang(soup: BeautifulSoup) -> Optional[str]:
    """Extract the declared language from the <html> tag.

    Args:
        soup: Parsed BeautifulSoup object.

    Returns:
        The language code, or None if not present.
    """
    html_tag = soup.find("html")
    if not html_tag:
        return None
    lang = html_tag.get("lang") or html_tag.get("xml:lang")
    if lang:
        lang = lang.strip().lower()
        # fasttext often uses 2-letter codes; take first segment
        return lang.split("-")[0]
    return None


def _has_explicit_lang(element: Any) -> bool:
    """Check whether an element or one of its ancestors already declares a lang.

    Per HTML semantics, a `lang`/`xml:lang` attribute is inherited by all
    descendants until overridden. So if an ancestor of `element` (up to but
    not including `<html>`, which represents the page-level declaration
    checked separately by WU1) already declares its own lang, `element`'s
    text is already correctly marked up and should not be flagged as a
    WU2 (missing part-level lang) issue, even though `element` itself has
    no `lang` attribute of its own.

    Args:
        element: A BeautifulSoup Tag to check.

    Returns:
        True if `element` or a non-<html> ancestor has an explicit lang.
    """
    current = element
    while current is not None and getattr(current, "name", None) not in (None, "html"):
        if current.get("lang") or current.get("xml:lang"):
            return True
        current = current.parent
    return False


def find_content_root(soup: BeautifulSoup) -> BeautifulSoup:
    """Find the main content area, falling back to <body> or the whole soup.

    Args:
        soup: Parsed BeautifulSoup object.

    Returns:
        A Tag representing the content root.
    """
    for selector in CONTENT_SELECTORS:
        root = soup.select_one(selector)
        if root:
            return root
    return soup.find("body") or soup


def extract_text_blocks(
    soup: BeautifulSoup, min_length: int = 20
) -> List[Dict[str, Any]]:
    """Walk the DOM and extract text blocks that may need a lang attribute.

    Skips:
      - script, style, nav, header, footer tags
      - Elements that already have a lang or xml:lang attribute, or that
        are nested inside an ancestor which declares one (lang is
        inherited per HTML semantics, so such elements are already
        correctly marked up)
      - Very short text strings

    Args:
        soup: Parsed BeautifulSoup object.
        min_length: Minimum character length for a text block to be considered.

    Returns:
        List of dicts with keys: text, tag, classes, id, lang.
    """
    root = find_content_root(soup)
    blocks: List[Dict[str, Any]] = []

    for element in root.descendants:
        if isinstance(element, NavigableString):
            continue

        tag_name = element.name
        if not tag_name or tag_name in SKIP_TAGS:
            continue

        # Skip if this element or an ancestor already declares a lang
        # (the lang attribute is inherited by descendants until overridden).
        if _has_explicit_lang(element):
            continue

        # Gather full text (including descendants)
        text = element.get_text(strip=True, separator=" ")
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < min_length:
            continue

        # Skip if the element contains child elements that are not inline,
        # because those children will be processed independently.
        has_block_children = any(
            child.name and child.name not in INLINE_TAGS
            for child in element.find_all(recursive=False)
        )
        if has_block_children:
            continue

        classes = " ".join(element.get("class", []))
        element_id = element.get("id", "")

        blocks.append(
            {
                "text": text,
                "tag": tag_name,
                "classes": classes,
                "id": element_id,
                "lang": None,
            }
        )

    return blocks


def parse_page(html: str, min_length: int = 20) -> Dict[str, Any]:
    """Parse raw HTML into structured page data.

    Args:
        html: Raw HTML string.
        min_length: Minimum text block length.

    Returns:
        Dict with keys: page_lang, text_blocks.
    """
    soup = BeautifulSoup(html, "lxml")
    page_lang = get_page_lang(soup)
    text_blocks = extract_text_blocks(soup, min_length=min_length)
    return {"page_lang": page_lang, "text_blocks": text_blocks}
