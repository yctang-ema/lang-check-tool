# Language Accessibility Checker

A local batch-auditing tool that checks web pages for WCAG 2.1 language accessibility issues:
- **SC 3.1.1 (Page-level):** Detects when a page's dominant language does not match its `<html lang>` attribute.
- **SC 3.1.2 (Part-level):** Detects text blocks within the main content that are in a different language but lack their own `lang` attribute.

## How It Works
1. Provide a sitemap URL via the command line.
2. The tool fetches the sitemap, crawls each page, and analyses the language of the main content.
3. It produces two timestamped reports in the `output/` directory:
   - A **CSV** file for spreadsheet action tracking.
   - A **standalone HTML** file with a searchable, sortable dashboard.

## Requirements
- Python 3.10 or higher

## Usage

### Installation

```bash
pip install -r requirements.txt
```

If you plan to use **browser mode** (default, required for WAF-protected sites), you also need to install Playwright's Chromium browser:

```bash
playwright install chromium
```

The tool will automatically download the `fasttext` language model (`lid.176.ftz`) on its first run if it is not present.

### Basic Scan

```bash
# Remote sitemap (browser mode — bypasses WAF)
python main.py --sitemap https://example.com/sitemap.xml

# Local sitemap file (browser mode)
python main.py --sitemap ./sitemap.xml

# Fast mode (HTTP requests, no WAF support)
python main.py --sitemap https://example.com/sitemap.xml --mode fast
```

### Options

```bash
python main.py --sitemap https://example.com/sitemap.xml \
               --output ./output \
               --workers 5 \
               --delay 0.5
```

| Flag | Description | Default |
|------|-------------|---------|
| `--sitemap` | URL or local path of the XML sitemap to scan | (required) |
| `--output` | Directory for generated reports | `./output` |
| `--workers` | Number of concurrent page requests (fast mode only) | `5` |
| `--delay` | Delay in seconds between request batches | `0.5` |
| `--min-length` | Minimum text length to analyse | `20` |
| `--limit` | Scan only the first N URLs from the sitemap | `0` (no limit) |
| `--offset` | Skip the first N URLs in the sitemap before scanning | `0` |
| `--mode` | Scraping engine: `fast` (HTTP requests) or `browser` (Playwright) | `browser` |
| `--confidence` | Minimum confidence (0.0-1.0) for language detection results | `0.7` |

### Resume from a Specific URL

If a scan is interrupted, you can resume from any position in the sitemap using `--offset`:

```bash
# Scan URLs 251–500
python main.py --sitemap ./sitemap.xml --offset 250 --limit 250 --output ./output
```

### Automated Batch Scanning

For large sitemaps (1000+ URLs), use the included `run_batches.py` helper to scan in chunks with rest periods between them. This is the safest way to avoid WAF rate limits.

```bash
python run_batches.py --sitemap ./sitemap.xml --batch-size 250 --delay 2.0 --rest 600
```

| Argument | Description | Default |
|----------|-------------|---------|
| `--sitemap` | Local path to sitemap.xml | (required) |
| `--batch-size` | URLs per batch | `250` |
| `--delay` | Delay between pages (seconds) | `2.0` |
| `--rest` | Rest time between batches (seconds) | `600` (10 min) |
| `--output` | Output directory | `./output` |
| `--confidence` | Detection confidence threshold | `0.7` |
| `--mode` | `fast` or `browser` | `browser` |

**Example:** Scan 5,387 URLs in batches of 250, with 2s page delay and 10-minute breaks:
```bash
python run_batches.py --sitemap ./sitemap.xml --batch-size 250 --delay 2.0 --rest 600
```

The script will:
1. Count total URLs in the sitemap.
2. Run batch 1 (URLs 1–250).
3. Rest for 10 minutes.
4. Run batch 2 (URLs 251–500).
5. Repeat until complete.

Each batch generates its own timestamped CSV/HTML report in `./output/`.

## Reports

Reports are saved with timestamps so consecutive runs do not overwrite previous audits:
- `output/report_YYYY-MM-DD_HHMMSS.csv`
- `output/report_YYYY-MM-DD_HHMMSS.html`

### Report Contents
Each report includes:
- The sitemap URL that was scanned.
- The total number of URLs crawled.
- The number of URLs flagged with issues.
- The date and time of the scan.
- For each flagged page:
  - Page URL
  - Declared page language (`<html lang>`)
  - Detected dominant language
  - Issue type (WU1 / WU2)
  - The specific text snippet flagged
  - The parent HTML element
  - Suggested fix (e.g., add `lang="fr"`)

## Suppressing False Positives

After running the tool, you may find recurring false positives (e.g., brand names misidentified as foreign text). You can create a local `output/ignore_phrases.txt` file. Each line should contain a phrase to skip during detection. This file is ignored by Git and never committed.

## Troubleshooting

### `ValueError: Unable to avoid copy while creating an array as requested`
This error occurs when `fasttext` is used with NumPy 2.x. **You must use NumPy 1.x.** The `requirements.txt` pins `numpy<2` to prevent this. If you already have NumPy 2 installed, run:
```bash
pip install "numpy<2" --force-reinstall
```

### Playwright browser not found
If you see an error like `Executable doesn't exist`, you forgot to install the browser. Run:
```bash
playwright install chromium
```

### Too many false positives
The language detector may occasionally misidentify short phrases, brand names, or text with special punctuation. The tool skips low-confidence detections by default, but you can tune it further:

1. **Raise the confidence threshold** — Only flag detections the model is highly confident about:
   ```bash
   python main.py --sitemap ./sitemap.xml --confidence 0.85
   ```
2. **Add phrases to the ignore list** — Create `output/ignore_phrases.txt` and add one phrase per line to skip.
3. **Increase `--min-length`** — Longer text blocks are more accurately detected:
   ```bash
   python main.py --sitemap ./sitemap.xml --min-length 40
   ```

## WAF & Rate-Limiting Considerations

### Browser Mode (Default)
**Browser mode** (`--mode browser`) uses a real headless Chromium browser to fetch **both the sitemap and every page**. This lets the tool pass most Web Application Firewall (WAF) challenges (e.g., Incapsula, Cloudflare) because it executes JavaScript and carries a realistic browser fingerprint.

### Fast Mode
**Fast mode** (`--mode fast`) uses lightweight HTTP requests and is ~3-5x faster, but it will almost certainly be blocked by any modern WAF.

### Rate Limiting
Even in browser mode, some advanced WAFs may still enforce **per-session or per-IP rate limits** after a certain number of requests. If you are scanning 1000+ pages and hit a block mid-scan:

- **Increase `--delay`** — Add more time between page loads (e.g., `--delay 2.0`)
- **Split into batches** — Use `--limit` to scan smaller chunks at a time:
  ```bash
  # Scan first 100 URLs
  python main.py --sitemap ./sitemap.xml --limit 100
  
  # Scan next 100 URLs
  python main.py --sitemap ./sitemap.xml --limit 100 --offset 100
  ```
- **Monitor progress** — If pages start failing mid-scan, stop and increase the delay before resuming.

### Sitemap Endpoint Protection
If the WAF still blocks the sitemap endpoint specifically, the tool will raise an explicit error. In that case, download the XML manually and pass a local file path: `--sitemap ./sitemap.xml`.

## Notes
- The tool focuses on **main content areas** (`<main>`, `<article>`, `.content`, `#content`, falling back to `<body>`). Navigation bars, headers, footers, scripts, and styles are excluded.
- Please be respectful to web servers. The default settings include polite delays and limited concurrency.
- **Do not commit any generated reports or local configuration to GitHub**, as they may contain sensitive site data.
