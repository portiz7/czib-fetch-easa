#!/usr/bin/env python3
"""
fetch_easa.py
-------------
Orchestrator for the two genuinely public, no-login EASA sources:

  1. CZIBs (Conflict Zone Information Bulletins) -> full two-phase HTML
     scraper, see scrape_easa_czibs.py (get_czib_list / parse_czib_detail /
     extract_firs / scrape_all). That module is self-contained and can be
     run/tested standalone; this script just calls its scrape_all().
  2. Information Notes (medium-risk, non-CZIB zones) -> public HTML page
     (metadata only, full text is gated behind the EASA CZ Hub login)

Output: data/raw_easa.json — raw, unprocessed data for this source only.
Cleaning, deduplication and cross-referencing against other sources happens
downstream in the conflict-zones-combine repo, not here.

This is intentionally conservative: if a source's HTML/JSON structure has
changed and a parser can't confidently extract something, it skips that item
and logs a warning rather than guessing. Check the GitHub Actions log after
each run.
"""

import json
import re
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from scrape_easa_czibs import scrape_all as scrape_easa_czibs

EASA_IN_URL = "https://www.easa.europa.eu/en/domains/air-operations/czibs/information"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ConflictZoneDashboardBot/1.0)"}
TIMEOUT = 20
OUT_PATH = "data/raw_easa.json"


def log(msg):
    print(f"[fetch_easa] {msg}", file=sys.stderr)


def fetch_easa_information_notes():
    """Public metadata for Information Notes (medium-risk, non-CZIB) zones."""
    try:
        r = requests.get(EASA_IN_URL, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        log(f"EASA Information Notes fetch failed: {e}")
        return []

    notes = []
    # Best-effort: look for table rows that mention a date pattern. This
    # section of EASA's site is metadata-only by design (full text is
    # CZ Hub-restricted), so we only expect area + dates here.
    rows = soup.select("table tr") or []
    for row in rows:
        text = row.get_text(" ", strip=True)
        if not text or "Area" in text:
            continue
        dates = re.findall(r"\d{2}/\d{2}/\d{4}", text)
        if dates:
            notes.append({"raw_text": text, "dates_found": dates})
    log(f"EASA Information Notes rows parsed: {len(notes)}")
    return notes


def main():
    out = {
        "source": "EASA",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "czibs": scrape_easa_czibs(),
        "information_notes": fetch_easa_information_notes(),
    }
    import os
    os.makedirs("data", exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    log(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
