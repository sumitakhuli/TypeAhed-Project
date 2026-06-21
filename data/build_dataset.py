"""
build_dataset.py — Download Wikipedia pageview dumps and build queries.csv.

Usage:
    python build_dataset.py          # uses default settings
    python build_dataset.py --hours 4  # download 4 hourly files

The script:
1. Scrapes the Wikimedia pageviews dump index for recent hourly files.
2. Downloads 2–3 gzipped dump files.
3. Parses, filters (English desktop), cleans titles, and aggregates view counts.
4. Keeps the top 150,000 queries that appear >= 2 times.
5. Writes queries.csv alongside this script.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import re
import sys
import urllib.parse
from collections import Counter
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DUMP_BASE = "https://dumps.wikimedia.org/other/pageviews"
SPECIAL_PREFIXES = (
    "special:",
    "wikipedia:",
    "file:",
    "talk:",
    "user:",
    "user_talk:",
    "wikipedia_talk:",
    "template:",
    "template_talk:",
    "help:",
    "help_talk:",
    "category:",
    "category_talk:",
    "portal:",
    "mediawiki:",
    "module:",
    "draft:",
)
MIN_COUNT = 2
TOP_K = 150_000
MIN_ROWS = 100_000
OUTPUT_FILENAME = "queries.csv"

# Regex to reject titles with leftover percent-encoded junk
PCT_JUNK_RE = re.compile(r"%[0-9A-Fa-f]{2}")

USER_AGENT = (
    "TypeAheadSearchBot/1.0 "
    "(https://github.com/sumitakhuli/TypeAhed-Project; educational project)"
)


# ---------------------------------------------------------------------------
# Helpers — scrape directory listings
# ---------------------------------------------------------------------------


class LinkExtractor(HTMLParser):
    """Simple HTML parser that collects ``href`` values from ``<a>`` tags."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.links.append(value)


def _fetch(url: str) -> bytes:
    """Fetch *url* and return the raw bytes."""
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=120) as resp:
        return resp.read()


def _fetch_text(url: str) -> str:
    return _fetch(url).decode("utf-8", errors="replace")


def _list_links(url: str) -> list[str]:
    """Return all <a href="..."> values on the page at *url*."""
    parser = LinkExtractor()
    parser.feed(_fetch_text(url))
    return parser.links


def discover_dump_urls(n_hours: int = 3) -> list[str]:
    """Find *n_hours* recent pageview dump file URLs.

    Strategy: walk backwards from today's date through the monthly index
    pages until we find enough ``.gz`` files.
    """
    now = datetime.now(timezone.utc)
    urls: list[str] = []

    # Try the last 7 days worth of monthly pages (handles month boundaries)
    tried_months: set[str] = set()
    for day_offset in range(7):
        dt = now - timedelta(days=day_offset)
        year = dt.strftime("%Y")
        month_slug = dt.strftime("%Y-%m")
        if month_slug in tried_months:
            continue
        tried_months.add(month_slug)

        month_url = f"{DUMP_BASE}/{year}/{month_slug}/"
        print(f"Scanning {month_url} …")
        try:
            links = _list_links(month_url)
        except Exception as exc:
            print(f"  Could not fetch index: {exc}")
            continue

        gz_files = sorted(
            [l for l in links if l.endswith(".gz") and l.startswith("pageviews-")],
            reverse=True,
        )
        for fname in gz_files:
            full_url = month_url + fname
            if full_url not in urls:
                urls.append(full_url)
            if len(urls) >= n_hours:
                return urls

    if not urls:
        print("ERROR: Could not discover any dump files.", file=sys.stderr)
        sys.exit(1)

    return urls


# ---------------------------------------------------------------------------
# Parsing & filtering
# ---------------------------------------------------------------------------


def is_valid_title(title: str) -> bool:
    """Return True if *title* should be kept."""
    lower = title.lower()
    if lower.startswith(SPECIAL_PREFIXES):
        return False
    if PCT_JUNK_RE.search(title):
        return False
    # Drop very short or empty titles
    if len(title.strip()) < 2:
        return False
    return True


def clean_title(raw: str) -> str:
    """Normalise a raw page title: URL-decode, underscores→spaces, lowercase."""
    title = urllib.parse.unquote(raw)
    title = title.replace("_", " ")
    title = title.strip().lower()
    return title


def parse_dump(data: bytes, counter: Counter) -> int:
    """Parse a gzipped pageview dump and add English-desktop counts to *counter*.

    Returns the number of lines added.
    """
    added = 0
    with gzip.open(BytesIO(data)) as fh:
        for raw_line in fh:
            try:
                line = raw_line.decode("utf-8", errors="replace")
            except Exception:
                continue
            parts = line.split(" ")
            if len(parts) < 3:
                continue
            domain_code = parts[0]
            raw_title = parts[1]
            try:
                views = int(parts[2])
            except ValueError:
                continue

            if domain_code != "en":
                continue
            if not is_valid_title(raw_title):
                continue

            title = clean_title(raw_title)
            if not title or len(title) < 2:
                continue

            counter[title] += views
            added += 1
    return added


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def build(n_hours: int = 3) -> None:
    out_path = Path(__file__).resolve().parent / OUTPUT_FILENAME

    dump_urls = discover_dump_urls(n_hours)
    print(f"\nWill download {len(dump_urls)} dump file(s).\n")

    counter: Counter = Counter()
    for i, url in enumerate(dump_urls, 1):
        fname = url.rsplit("/", 1)[-1]
        print(f"[{i}/{len(dump_urls)}] Downloading {fname} …")
        data = _fetch(url)
        print(f"  Downloaded {len(data) / 1_048_576:.1f} MB — parsing …")
        added = parse_dump(data, counter)
        print(f"  Added {added:,} English-desktop entries.")

    # Filter: minimum count threshold
    counter = Counter({k: v for k, v in counter.items() if v >= MIN_COUNT})
    print(f"\nAfter min-count filter ({MIN_COUNT}): {len(counter):,} unique titles.")

    # Keep top K
    top = counter.most_common(TOP_K)
    print(f"Keeping top {TOP_K:,}: actual {len(top):,} rows.")

    if len(top) < MIN_ROWS:
        print(
            f"\nWARNING: Only {len(top):,} rows — below the {MIN_ROWS:,} target. "
            f"Re-run with --hours <N> to download more files.",
            file=sys.stderr,
        )

    # Write CSV
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["query", "count"])
        for query, count in top:
            writer.writerow([query, count])

    print(f"\nWrote {len(top):,} rows to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build queries.csv from Wikipedia pageviews.")
    parser.add_argument(
        "--hours",
        type=int,
        default=3,
        help="Number of hourly dump files to download (default: 3).",
    )
    args = parser.parse_args()
    build(n_hours=args.hours)
