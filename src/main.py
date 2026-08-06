"""Main CLI entrypoint. Orchestrates the full audit pipeline."""

import argparse
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from tqdm import tqdm

from .detector import detect_language, is_ignored, load_detector, load_ignore_phrases
from .parser import parse_page
from .reporter import generate_csv, generate_html
from .scraper import (
    fetch_pages_fast,
    fetch_pages_browser,
    fetch_sitemap_fast,
    fetch_sitemap_browser,
)


DEFAULT_CONFIDENCE = 0.7


def build_issues(
    url: str,
    html: str,
    detector: Any,
    ignore_phrases: Set[str],
    min_length: int,
    confidence_threshold: float = DEFAULT_CONFIDENCE,
) -> List[Dict[str, Any]]:
    """Analyse a single page and return any language-accessibility issues.

    Args:
        url: The page URL.
        html: Raw HTML content.
        detector: Loaded fasttext model.
        ignore_phrases: Set of phrases to skip.
        min_length: Minimum text length threshold.
        confidence_threshold: Minimum confidence (0.0-1.0) to trust a detection.

    Returns:
        List of issue dicts.
    """
    issues: List[Dict[str, Any]] = []
    parsed = parse_page(html, min_length=min_length)
    page_lang = parsed["page_lang"]
    text_blocks = parsed["text_blocks"]

    if not text_blocks:
        return issues

    # Run language detection once per block and cache the result so the
    # WU1 (dominant-language) pass and the WU2 (per-block) pass below don't
    # each invoke the fasttext model on the same text a second time.
    detections: Dict[int, Tuple[Optional[str], float]] = {}
    block_langs = []
    for index, block in enumerate(text_blocks):
        if is_ignored(block["text"], ignore_phrases):
            continue
        lang, conf = detect_language(detector, block["text"])
        detections[index] = (lang, conf)
        if lang and conf >= confidence_threshold:
            block_langs.append(lang)

    if not block_langs:
        return issues

    dominant_lang = Counter(block_langs).most_common(1)[0][0]

    # WU1: page-level mismatch
    if page_lang and dominant_lang != page_lang:
        issues.append(
            {
                "url": url,
                "declared_lang": page_lang,
                "detected_lang": dominant_lang,
                "issue_type": "WU1",
                "snippet": "",
                "element": "html",
                "suggested_fix": f'Change <html lang="{page_lang}"> to <html lang="{dominant_lang}">',
            }
        )

    # WU2: part-level missing lang
    for index, block in enumerate(text_blocks):
        if index not in detections:
            continue
        block_lang, conf = detections[index]
        if not block_lang or conf < confidence_threshold:
            continue
        if block_lang != dominant_lang:
            tag = block["tag"]
            classes = block["classes"]
            element_id = block["id"]
            element_str = tag
            if classes:
                element_str += f' class="{classes}"'
            if element_id:
                element_str += f' id="{element_id}"'
            snippet = block["text"][:200] + ("..." if len(block["text"]) > 200 else "")
            issues.append(
                {
                    "url": url,
                    "declared_lang": dominant_lang,
                    "detected_lang": block_lang,
                    "issue_type": "WU2",
                    "snippet": snippet,
                    "element": element_str,
                    "suggested_fix": f'Add lang="{block_lang}" to the element',
                }
            )

    return issues


def main() -> int:
    """Parse CLI arguments and run the audit."""
    arg_parser = argparse.ArgumentParser(
        description="Audit a website for WCAG 2.1 language accessibility issues."
    )
    arg_parser.add_argument(
        "--sitemap",
        required=True,
        help="URL or local path of the sitemap.xml to scan",
    )
    arg_parser.add_argument(
        "--output",
        default="./output",
        help="Directory for generated reports (default: ./output)",
    )
    arg_parser.add_argument(
        "--workers",
        type=int,
        default=5,
        help="Number of concurrent fetch workers (default: 5)",
    )
    arg_parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay in seconds between request batches (default: 0.5)",
    )
    arg_parser.add_argument(
        "--min-length",
        type=int,
        default=20,
        help="Minimum text length to analyse (default: 20)",
    )
    arg_parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit the number of URLs to scan (0 = no limit)",
    )
    arg_parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Skip the first N URLs in the sitemap before scanning (default: 0)",
    )
    arg_parser.add_argument(
        "--mode",
        choices=["fast", "browser"],
        default="browser",
        help=(
            "Scraping mode: 'fast' uses HTTP requests (no WAF support), "
            "'browser' uses Playwright (slower, but bypasses WAF). "
            "Default: browser"
        ),
    )
    arg_parser.add_argument(
        "--confidence",
        type=float,
        default=DEFAULT_CONFIDENCE,
        help=(
            "Minimum confidence threshold (0.0-1.0) for language detection. "
            "Detections below this value are ignored to reduce false positives. "
            f"Default: {DEFAULT_CONFIDENCE}"
        ),
    )
    args = arg_parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Loading language detector ...")
    detector = load_detector()
    ignore_phrases = load_ignore_phrases(output_dir)

    print(f"Fetching sitemap: {args.sitemap}")
    try:
        if args.mode == "fast":
            urls = fetch_sitemap_fast(args.sitemap)
        else:
            urls = fetch_sitemap_browser(args.sitemap)
    except Exception as exc:
        print(f"Failed to fetch sitemap: {exc}")
        return 1

    start = args.offset if args.offset > 0 else 0
    end = start + args.limit if args.limit and args.limit > 0 else len(urls)
    urls = urls[start:end]

    total_urls = len(urls)
    print(f"Scanning {total_urls} URLs (offset={start}). Starting crawl (mode={args.mode}) ...")

    if args.mode == "fast":
        pages = fetch_pages_fast(
            urls,
            max_workers=args.workers,
            delay=args.delay,
        )
    else:
        pages = fetch_pages_browser(
            urls,
            delay=args.delay,
        )

    all_issues: List[Dict[str, Any]] = []
    for url, status_code, html in tqdm(pages, desc="Analysing", total=len(pages)):
        if status_code == 0 or not html:
            continue
        page_issues = build_issues(
            url,
            html,
            detector,
            ignore_phrases,
            args.min_length,
            args.confidence,
        )
        all_issues.extend(page_issues)

    flagged_count = len({i["url"] for i in all_issues})
    scan_time = datetime.now().isoformat()

    print(f"Audit complete. {flagged_count} pages flagged.")
    print("Generating reports ...")

    template_dir = Path(__file__).parent.parent / "templates"
    csv_path = generate_csv(
        output_dir, args.sitemap, total_urls, all_issues, flagged_count, scan_time
    )
    html_path = generate_html(
        output_dir, args.sitemap, total_urls, all_issues, template_dir, flagged_count, scan_time
    )

    print(f"CSV report: {csv_path}")
    print(f"HTML report: {html_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
