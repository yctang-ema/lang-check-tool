#!/usr/bin/env python3
"""Batch runner for the Language Accessibility Checker.

Runs the audit in configurable chunks with rest periods between them.
This spreads traffic over time and reduces the chance of WAF rate limiting.

Usage:
    python run_batches.py --sitemap ./sitemap.xml --batch-size 250 --delay 2.0 --rest 600

Arguments:
    --sitemap           Path or URL to sitemap.xml
    --batch-size        Number of URLs per batch (default: 250)
    --delay             Page delay in seconds (default: 2.0)
    --rest              Rest time in seconds between batches (default: 600 = 10 min)
    --output            Output directory (default: ./output)
    --confidence        Detection confidence threshold (default: 0.7)
    --min-length        Minimum text length (default: 20)
    --mode              fast or browser (default: browser)
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path


def count_urls(sitemap_path: str) -> int:
    """Count URLs in a local sitemap file."""
    from defusedxml import ElementTree as ET

    with open(sitemap_path, "rb") as f:
        content = f.read()
    root = ET.fromstring(content)
    ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [loc.text for loc in root.findall(".//ns:loc", ns) if loc.text]
    return len(urls)


def run_batch(
    sitemap: str,
    offset: int,
    limit: int,
    delay: float,
    output: str,
    confidence: float,
    min_length: int,
    mode: str,
) -> int:
    """Run a single batch via subprocess. Returns exit code."""
    cmd = [
        sys.executable,
        "main.py",
        "--sitemap", sitemap,
        "--offset", str(offset),
        "--limit", str(limit),
        "--delay", str(delay),
        "--output", output,
        "--confidence", str(confidence),
        "--min-length", str(min_length),
        "--mode", mode,
    ]
    print(f"\n{'='*60}")
    print(f"Running batch: offset={offset}, limit={limit}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}\n")
    result = subprocess.run(cmd)
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Language Accessibility Checker in staggered batches."
    )
    parser.add_argument("--sitemap", required=True, help="Path or URL to sitemap.xml")
    parser.add_argument("--batch-size", type=int, default=250, help="URLs per batch")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between pages (seconds)")
    parser.add_argument("--rest", type=float, default=600, help="Rest between batches (seconds)")
    parser.add_argument("--output", default="./output", help="Output directory")
    parser.add_argument("--confidence", type=float, default=0.7, help="Confidence threshold")
    parser.add_argument("--min-length", type=int, default=20, help="Minimum text length")
    parser.add_argument("--mode", choices=["fast", "browser"], default="browser", help="Scraping mode")
    args = parser.parse_args()

    # Count URLs
    if args.sitemap.startswith("http://") or args.sitemap.startswith("https://"):
        print("Error: run_batches.py requires a local sitemap file path.")
        return 1

    total = count_urls(args.sitemap)
    print(f"Total URLs in sitemap: {total}")
    print(f"Batch size: {args.batch_size}")
    print(f"Delay between pages: {args.delay}s")
    print(f"Rest between batches: {args.rest}s ({args.rest/60:.1f} min)")
    print(f"Estimated total time: ~{((total/args.batch_size)*(args.rest + (args.batch_size*args.delay)))/3600:.1f} hours\n")

    batch_num = 0
    for offset in range(0, total, args.batch_size):
        batch_num += 1
        limit = min(args.batch_size, total - offset)
        print(f"\n>>> Batch {batch_num} of {(total + args.batch_size - 1) // args.batch_size} <<<")

        code = run_batch(
            sitemap=args.sitemap,
            offset=offset,
            limit=limit,
            delay=args.delay,
            output=args.output,
            confidence=args.confidence,
            min_length=args.min_length,
            mode=args.mode,
        )

        if code != 0:
            print(f"\nWARNING: Batch {batch_num} exited with code {code}. Stopping.")
            return code

        remaining = total - (offset + limit)
        if remaining > 0:
            print(f"\n{remaining} URLs remaining. Resting for {args.rest/60:.1f} minutes...")
            time.sleep(args.rest)
        else:
            print(f"\nAll {total} URLs processed. Batching complete.")

    print("\nDone. Check ./output/ for timestamped reports.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
