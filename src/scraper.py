"""Scraper module: fetch sitemap and page contents."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple

import requests
from defusedxml import ElementTree as ET
from tqdm import tqdm

# Maximum recursion depth when following <sitemapindex> references to child
# sitemaps. Guards against malformed or maliciously cyclic sitemap chains.
_MAX_SITEMAP_INDEX_DEPTH = 5

_SITEMAP_NS = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _local_tag(element) -> str:
    """Return an XML element's tag name with any namespace prefix stripped."""
    tag = element.tag
    return tag.split("}", 1)[1] if "}" in tag else tag


def _parse_sitemap_xml(content: bytes) -> Tuple[bool, List[str]]:
    """Parse sitemap XML bytes into a (is_index, locs) tuple.

    Supports both a standard `<urlset>` (a flat list of page URLs) and a
    `<sitemapindex>` (a list of URLs pointing to child sitemap files) —
    the latter is very common for large multilingual sites that split
    their sitemap by locale or section.

    Args:
        content: Raw XML bytes.

    Returns:
        A tuple of (is_index, locs) where `is_index` is True if the root
        element is a `<sitemapindex>` (meaning `locs` are child sitemap
        URLs to fetch and parse recursively) and False if it's a
        `<urlset>` (meaning `locs` are page URLs).
    """
    root = ET.fromstring(content)
    locs = [
        loc.text.strip()
        for loc in root.findall(".//ns:loc", _SITEMAP_NS)
        if loc.text and loc.text.strip()
    ]
    is_index = _local_tag(root) == "sitemapindex"
    return is_index, locs


def _read_local_sitemap(path: str) -> bytes:
    """Read a local sitemap file from disk.

    Args:
        path: Local filesystem path to the sitemap.xml file.

    Returns:
        Raw file bytes.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    with open(path, "rb") as f:
        return f.read()


def _is_remote(sitemap_source: str) -> bool:
    """Return True if `sitemap_source` looks like a remote http(s) URL."""
    return sitemap_source.startswith("http://") or sitemap_source.startswith("https://")


def fetch_sitemap_fast(
    sitemap_source: str, timeout: int = 30, _depth: int = 0
) -> List[str]:
    """Fetch or read a sitemap XML using HTTP requests (fast mode).

    Supports both remote URLs (http/https) and local file paths, and
    transparently follows `<sitemapindex>` references to child sitemaps
    (child sitemap `<loc>` entries are always fetched as URLs, per the
    sitemap protocol, even if the top-level sitemap was a local file).

    Args:
        sitemap_source: URL or local path to the sitemap.xml file.
        timeout: HTTP request timeout in seconds (for remote URLs).
        _depth: Internal recursion guard for nested sitemap indexes.

    Returns:
        List of page URLs found in the sitemap (flattened across any
        nested sitemap index files).

    Raises:
        requests.RequestException: If a remote sitemap cannot be fetched.
        FileNotFoundError: If a local sitemap file does not exist.
        RuntimeError: If sitemap index nesting exceeds the depth guard.
    """
    if _depth > _MAX_SITEMAP_INDEX_DEPTH:
        raise RuntimeError(
            f"Sitemap index nesting exceeded {_MAX_SITEMAP_INDEX_DEPTH} levels "
            f"while resolving '{sitemap_source}'. Possible malformed or "
            "cyclic sitemap index."
        )

    if _is_remote(sitemap_source):
        response = requests.get(sitemap_source, timeout=timeout)
        response.raise_for_status()
        content = response.content
    else:
        content = _read_local_sitemap(sitemap_source)

    is_index, locs = _parse_sitemap_xml(content)
    if not is_index:
        return locs

    urls: List[str] = []
    for child_loc in locs:
        urls.extend(fetch_sitemap_fast(child_loc, timeout=timeout, _depth=_depth + 1))
    return urls


def _fetch_sitemap_content_browser(page, sitemap_source: str, timeout: int) -> bytes:
    """Fetch a single sitemap URL's raw XML bytes using an open Playwright page.

    Args:
        page: An open Playwright page.
        sitemap_source: Remote http(s) URL of the sitemap to fetch.
        timeout: Navigation timeout in seconds.

    Returns:
        Raw XML bytes of the response body.

    Raises:
        RuntimeError: If the response is missing, an HTTP error, or does
            not look like XML (e.g. a WAF block page).
    """
    response = page.goto(sitemap_source, wait_until="networkidle")
    if response is None:
        raise RuntimeError(f"No response received for sitemap URL: {sitemap_source}")

    raw_body = response.body()
    status = response.status
    if status >= 400:
        raise RuntimeError(f"Sitemap returned HTTP {status}: {sitemap_source}")

    # Playwright's body() returns bytes; decode safely just for sniffing.
    try:
        content_text = raw_body.decode("utf-8")
    except UnicodeDecodeError:
        content_text = raw_body.decode("utf-8", errors="replace")

    # Guard against WAF block pages that return HTML instead of XML.
    # Accept both <urlset> (page list) and <sitemapindex> (nested sitemaps).
    stripped = content_text.strip()
    looks_like_xml = stripped.startswith("<?xml") or "<urlset" in stripped or "<sitemapindex" in stripped
    if not looks_like_xml:
        raise RuntimeError(
            f"Sitemap response does not look like XML: {sitemap_source}. "
            "The WAF may still be blocking the sitemap endpoint. "
            "Try downloading the sitemap manually and passing a local file path."
        )

    return raw_body


def _fetch_sitemap_urls_browser(page, sitemap_source: str, timeout: int, depth: int) -> List[str]:
    """Recursively resolve a sitemap (or sitemap index) using an open page.

    Args:
        page: An open Playwright page, reused across recursive calls.
        sitemap_source: URL or local path to the sitemap.xml file.
        timeout: Navigation timeout in seconds (for remote URLs).
        depth: Current recursion depth, guarded by `_MAX_SITEMAP_INDEX_DEPTH`.

    Returns:
        List of page URLs, flattened across any nested sitemap index files.
    """
    if depth > _MAX_SITEMAP_INDEX_DEPTH:
        raise RuntimeError(
            f"Sitemap index nesting exceeded {_MAX_SITEMAP_INDEX_DEPTH} levels "
            f"while resolving '{sitemap_source}'. Possible malformed or "
            "cyclic sitemap index."
        )

    if _is_remote(sitemap_source):
        content = _fetch_sitemap_content_browser(page, sitemap_source, timeout)
    else:
        # Local file — read it directly (only expected at depth 0; child
        # sitemap index entries are always URLs per the sitemap protocol).
        content = _read_local_sitemap(sitemap_source)

    is_index, locs = _parse_sitemap_xml(content)
    if not is_index:
        return locs

    urls: List[str] = []
    for child_loc in locs:
        urls.extend(
            _fetch_sitemap_urls_browser(page, child_loc, timeout, depth + 1)
        )
    return urls


def fetch_sitemap_browser(sitemap_source: str, timeout: int = 30) -> List[str]:
    """Fetch a remote sitemap XML using Playwright (browser mode).

    Falls back to reading from disk for local file paths. Transparently
    follows `<sitemapindex>` references to child sitemaps (a single
    browser/page is reused across all nested fetches).

    Args:
        sitemap_source: URL or local path to the sitemap.xml file.
        timeout: Navigation timeout in seconds (for remote URLs).

    Returns:
        List of page URLs found in the sitemap.

    Raises:
        Exception: If the browser cannot fetch or parse the sitemap.
    """
    if not _is_remote(sitemap_source):
        # Local file with no remote fetching needed at the top level, but
        # still resolve any nested (remote) sitemap index entries below it.
        content = _read_local_sitemap(sitemap_source)
        is_index, locs = _parse_sitemap_xml(content)
        if not is_index:
            return locs
        # Fall through to use the browser to resolve child sitemap URLs.
        sitemap_source_list = locs
        child_depth = 1
    else:
        sitemap_source_list = [sitemap_source]
        child_depth = 0

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()
        page.set_default_navigation_timeout(timeout * 1000)

        try:
            urls: List[str] = []
            for source in sitemap_source_list:
                urls.extend(
                    _fetch_sitemap_urls_browser(page, source, timeout, depth=child_depth)
                )
            return urls
        finally:
            page.close()
            context.close()
            browser.close()


def _fetch_page_fast(
    url: str, timeout: int = 30, retries: int = 3
) -> Tuple[str, int, str]:
    """Fetch a single page with retries using requests."""
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            if response.encoding == "ISO-8859-1":
                response.encoding = "utf-8"
            return url, response.status_code, response.text
        except requests.RequestException:
            if attempt == retries:
                return url, 0, ""
            time.sleep(2 ** attempt)
    return url, 0, ""


def fetch_pages_fast(
    urls: List[str],
    max_workers: int = 5,
    delay: float = 0.5,
    timeout: int = 30,
    retries: int = 3,
) -> List[Tuple[str, int, str]]:
    """Fetch multiple pages concurrently using requests (fast mode)."""
    results: List[Tuple[str, int, str]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for url in urls:
            future = executor.submit(_fetch_page_fast, url, timeout, retries)
            futures[future] = url
            time.sleep(delay)

        for future in tqdm(as_completed(futures), total=len(urls), desc="Fetching pages"):
            results.append(future.result())

    return results


def fetch_pages_browser(
    urls: List[str],
    delay: float = 0.5,
    timeout: int = 30,
    retries: int = 3,
    headless: bool = True,
) -> List[Tuple[str, int, str]]:
    """Fetch multiple pages using Playwright (browser mode).

    Launches a single browser instance and reuses it across all pages,
    opening/closing tabs to keep memory usage reasonable.

    Args:
        urls: List of page URLs to fetch.
        delay: Delay in seconds between page navigations.
        timeout: Navigation timeout in seconds.
        retries: Number of retries per page.
        headless: Whether to run the browser headlessly.

    Returns:
        List of (url, status_code, html_content) tuples.
    """
    from playwright.sync_api import sync_playwright

    results: List[Tuple[str, int, str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            )
        )

        for url in tqdm(urls, desc="Fetching pages (browser)"):
            html = ""
            status_code = 0
            for attempt in range(1, retries + 1):
                page = None
                try:
                    page = context.new_page()
                    page.set_default_navigation_timeout(timeout * 1000)
                    response = page.goto(url, wait_until="networkidle")
                    if response:
                        status_code = response.status
                    html = page.content()
                    break
                except Exception as exc:
                    print(f"  ⚠️  {url} attempt {attempt}/{retries} failed: {exc}")
                    if attempt == retries:
                        status_code = 0
                        html = ""
                    time.sleep(2 ** attempt)
                finally:
                    if page:
                        page.close()

            results.append((url, status_code, html))
            time.sleep(delay)

        context.close()
        browser.close()

    return results
