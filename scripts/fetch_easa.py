#!/usr/bin/env python3
"""
fetch_easa.py
-------------
Fetches the two genuinely public, no-login EASA sources:

  1. CZIBs (Conflict Zone Information Bulletins) -> public JSON export endpoint
  2. Information Notes (medium-risk, non-CZIB zones) -> public HTML page (metadata only,
     full text is gated behind the EASA CZ Hub login)

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

EASA_JSON_URL = "https://www.easa.europa.eu/en/domains/air-operations/czibs/export-json?page&_format=json"
EASA_IN_URL = "https://www.easa.europa.eu/en/domains/air-operations/czibs/information"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ConflictZoneDashboardBot/1.0)"}
TIMEOUT = 20
OUT_PATH = "data/raw_easa.json"


def log(msg):
    print(f"[fetch_easa] {msg}", file=sys.stderr)


def fetch_easa_czibs():
    """Public JSON export of all CZIBs, no auth required."""
    try:
        r = requests.get(EASA_JSON_URL, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log(f"EASA CZIB fetch failed: {e}")
        return []

    czibs = []
    # The export is a list of node dicts; field names mirror the site's
    # exposed columns. Adjust keys here if EASA changes the export shape.
    for item in data if isinstance(data, list) else data.get("data", []):
        try:
            czibs.append({
                "title": item.get("title") or item.get("field_czib_title", ""),
                "czib_number": item.get("field_czib_number") or item.get("czib_number", ""),
                "status": item.get("field_czib_status") or item.get("status", ""),
                "issue_date": item.get("field_issue_date") or item.get("issue_date", ""),
                "revision_date": item.get("field_revision_date") or item.get("revision_date", ""),
                "valid_until": item.get("field_valid_until") or item.get("valid_until", ""),
                "url": item.get("url") or item.get("path", ""),
            })
        except Exception as e:
            log(f"  skipped one EASA CZIB row: {e}")
    log(f"EASA CZIBs parsed: {len(czibs)}")
    return czibs


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
        "czibs": fetch_easa_czibs(),
        "information_notes": fetch_easa_information_notes(),
    }
    import os
    os.makedirs("data", exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    log(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
