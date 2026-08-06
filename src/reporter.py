"""Reporter module: generate CSV and HTML reports."""

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from jinja2 import Environment, FileSystemLoader, select_autoescape

# Leading characters that spreadsheet applications (Excel, Google Sheets,
# LibreOffice Calc) interpret as the start of a formula. If a CSV field
# scraped from a web page starts with one of these, prefix it with a
# single quote so the value is treated as plain text instead of being
# evaluated as a formula ("CSV/formula injection").
_CSV_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def _timestamp() -> str:
    """Return a filesystem-safe timestamp string."""
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def _sanitize_csv_field(value: Any) -> Any:
    """Neutralise potential CSV formula injection in a field value.

    Spreadsheet applications may execute a cell's contents as a formula
    if it begins with certain characters (e.g. ``=``, ``+``, ``-``, ``@``).
    Since report fields (URLs, snippets, suggested fixes) originate from
    scraped third-party web content, they are not trusted input. Prefixing
    a leading apostrophe forces spreadsheet apps to treat the value as text.

    Args:
        value: The raw field value.

    Returns:
        The sanitised value (unchanged if not a risky string).
    """
    if isinstance(value, str) and value.startswith(_CSV_FORMULA_TRIGGERS):
        return "'" + value
    return value


def generate_csv(
    output_dir: Path,
    sitemap_url: str,
    total_urls: int,
    issues: List[Dict[str, Any]],
    flagged_count: int,
    scan_time: str,
) -> Path:
    """Write a timestamped CSV report.

    Args:
        output_dir: Directory to write the file.
        sitemap_url: The sitemap URL that was scanned.
        total_urls: Total number of URLs processed.
        issues: Flat list of issue dictionaries.
        flagged_count: Number of unique URLs flagged with issues.
        scan_time: ISO-formatted scan timestamp.

    Returns:
        Path to the written CSV file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()
    csv_path = output_dir / f"report_{ts}.csv"

    fieldnames = [
        "sitemap_url",
        "total_urls",
        "flagged_urls",
        "scan_time",
        "url",
        "declared_lang",
        "detected_lang",
        "issue_type",
        "snippet",
        "element",
        "suggested_fix",
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for issue in issues:
            row = {
                "sitemap_url": sitemap_url,
                "total_urls": total_urls,
                "flagged_urls": flagged_count,
                "scan_time": scan_time,
                "url": issue["url"],
                "declared_lang": issue.get("declared_lang", ""),
                "detected_lang": issue.get("detected_lang", ""),
                "issue_type": issue["issue_type"],
                "snippet": issue.get("snippet", ""),
                "element": issue.get("element", ""),
                "suggested_fix": issue.get("suggested_fix", ""),
            }
            row = {key: _sanitize_csv_field(val) for key, val in row.items()}
            writer.writerow(row)

    return csv_path


def generate_html(
    output_dir: Path,
    sitemap_url: str,
    total_urls: int,
    issues: List[Dict[str, Any]],
    template_dir: Path,
    flagged_count: int,
    scan_time: str,
) -> Path:
    """Write a standalone HTML report.

    Args:
        output_dir: Directory to write the file.
        sitemap_url: The sitemap URL that was scanned.
        total_urls: Total number of URLs processed.
        issues: Flat list of issue dictionaries.
        template_dir: Directory containing Jinja2 templates.
        flagged_count: Number of unique URLs flagged with issues.
        scan_time: ISO-formatted scan timestamp.

    Returns:
        Path to the written HTML file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()
    html_path = output_dir / f"report_{ts}.html"

    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("report_standalone.html")

    # Escape "</" so that scraped content (e.g. a snippet literally
    # containing "</script>") cannot prematurely close the <script> tag
    # this JSON is embedded in and inject arbitrary markup/script.
    issues_json = json.dumps(issues, ensure_ascii=False).replace("</", "<\\/")

    rendered = template.render(
        sitemap_url=sitemap_url,
        total_urls=total_urls,
        flagged_urls=flagged_count,
        scan_time=scan_time,
        issues=issues,
        issues_json=issues_json,
    )

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(rendered)

    return html_path
