# Execution Plan: Language Accessibility Checker

## Goal
Build a local batch-auditing tool that checks web pages for WCAG 2.1 language accessibility issues, producing timestamped CSV and standalone HTML reports.

## Architecture
- **Local Engine:** Pure Python CLI.
- **No GitHub Pages:** Reports are generated locally and never committed.
- **No external services:** All scraping and detection happens on the user's machine.

## Key Decisions
1. **Sitemap Input:** Passed via CLI (`--sitemap`). Never hardcoded.
2. **Language Detection:** `fasttext` with pre-trained `lid.176.ftz` model.
3. **Content Scope:** Main content area only (`<main>`, `<article>`, `.content`, `#content`, fallback `<body>`). Skips nav, header, footer, script, style.
4. **Two Flags:**
   - **WU1:** Page-level language mismatch (`<html lang>` vs dominant content language).
   - **WU2:** Part-level missing `lang` attribute on foreign-language text blocks.
5. **Noise Reduction:** Minimum text length 20 characters. Local `ignore_phrases.txt` for suppressing false positives.
6. **Polite Scraping:** 5 concurrent workers, 0.5s delay, exponential backoff retries.
7. **Timestamped Outputs:** `report_YYYY-MM-DD_HHMMSS.csv` and `.html` in `output/`.
8. **Sanitisation:** No domains, org names, or real URLs in any committed file.

## Execution Steps
1. Create project scaffolding and sanitized documentation.
2. Implement `scraper.py`: sitemap fetch, URL extraction, concurrent page fetch with retries.
3. Implement `parser.py`: HTML parsing, main-content extraction, text-block enumeration.
4. Implement `detector.py`: fasttext model loading/download, language detection, ignore-phrase filtering.
5. Implement `reporter.py`: CSV generation, HTML dashboard generation via Jinja2.
6. Implement `main.py`: CLI argument parsing, pipeline orchestration, progress bars.
7. Test on a live sitemap subset and review false positives.
8. Finalise README.md with setup and usage instructions.

## Risks & Mitigations
- **Rate limiting:** Mitigated by polite delays, limited concurrency, and retries.
- **False positives:** Mitigated by min-length threshold, content-area scoping, and local ignore lists.
- **Model download:** Auto-download on first run with clear console messaging.
