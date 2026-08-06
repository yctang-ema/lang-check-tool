# Language Accessibility Checker - Agent Context

## Background
This tool audits large multilingual websites for WCAG 2.1 language accessibility issues:
- **SC 3.1.1:** Page-level language mismatch between `<html lang>` and the dominant content language.
- **SC 3.1.2:** Missing `lang` attributes on parts of a page written in a different language.

## Architecture
- **Local Engine:** Pure Python CLI tool. Fetches a sitemap.xml, scrapes each page, detects language changes, and generates timestamped reports.
- **Reports:** Two outputs per run — a CSV file and a self-contained HTML dashboard. Both are saved locally and never committed.

## Tech Stack
- Python 3.10+
- `requests` (HTTP)
- `beautifulsoup4` + `lxml` (HTML parsing)
- `fasttext` (language detection)
- `jinja2` (HTML report templating)
- `tqdm` (CLI progress bars)

## Project Structure
```
lang-check-tool/
├── .gitignore
├── AGENTS.md
├── plan.md
├── README.md
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── scraper.py
│   ├── parser.py
│   ├── detector.py
│   └── reporter.py
└── templates/
    └── report_standalone.html
```

## Coding Conventions
- Follow PEP8.
- Use type hints for public function signatures.
- Document functions with docstrings.
- Keep dependencies minimal.
- Handle network errors gracefully with retries.
- Respect server load: use polite delays and limited concurrency.
- **Sanitisation rule:** No domain names, organisation names, or real URLs may be hardcoded in any committed file.

## Build & Run
1. `pip install -r requirements.txt`
2. `python main.py --sitemap https://<website>/sitemap.xml`
3. Check `./output/` for timestamped `report_*.csv` and `report_*.html`.

The package can also be run as a module: `python -m src.main --sitemap ...`
