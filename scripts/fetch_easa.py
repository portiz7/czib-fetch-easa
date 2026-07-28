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
from scrape_easa_czibs import extract_firs

EASA_IN_URL = "https://www.easa.europa.eu/en/domains/air-operations/czibs/information"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ConflictZoneDashboardBot/1.0)"}
TIMEOUT = 20
OUT_PATH = "data/raw_easa.json"


def log(msg):
    print(f"[fetch_easa] {msg}", file=sys.stderr)


def _clean(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


def _extract_countries(text):
    """Countries in this table always precede a "(... FIR ...)" parenthetical,
    e.g. "Israel (Tel Aviv FIR – LLLL), Jordan (Amman FIR – OJAC)" - confirmed
    against all 3 live rows. Matches only capitalized word sequences right
    before such a parenthetical, so surrounding prose ("and", "in the") is
    never swept in."""
    if not text:
        return []
    countries = re.findall(r"\b([A-Z][a-zA-Z]*(?:\s[A-Z][a-zA-Z]*)*)\s*\([^)]*FIR[^)]*\)", text)
    seen = []
    for c in countries:
        c = c.strip()
        if c and c not in seen:
            seen.append(c)
    return seen


def _slugify_id(area_text, index):
    """Information Notes have no bulletin-number-like field anywhere on the
    page (confirmed - the table has only Area covered/Issue date/Valid
    until/Overview of recommendations columns), so there's no real ID to
    extract. Derives a readable one from the subject instead of a bare
    index, falling back to "IN-{index}" if that fails."""
    m = re.search(r"airspace of ([A-Za-z][^(.:]*?)(?:\s+Airspace affected\b|[(.:]|$)", area_text)
    if m:
        phrase = re.sub(r"^(the|a|an)\s+", "", m.group(1).strip(), flags=re.IGNORECASE)
        words = phrase.split()[:5]  # capped so long country lists don't produce unreadable IDs
        name = re.sub(r"[^A-Za-z]+", "-", " ".join(words)).strip("-").upper()
        if name:
            return f"IN-{name}"
    return f"IN-{index}"


def fetch_easa_information_notes():
    """
    Public Information Notes table (medium-risk, non-CZIB zones) - full text
    is gated behind the EASA CZ Hub login, but this summary table is public.

    Real table structure (confirmed via a live fetch): a single <table
    class="cols-4"> with headers ["Area covered", "Issue date", "Valid
    until", "Overview of the recommendations *"]. There is no separate
    subject/ID/description/applicability column - "Area covered" mixes the
    note's title and its actual area-covered text in one cell, and that's
    genuinely everything this page exposes. Per explicit instruction, only
    id/issue_date/valid_until/affected_countries/affected_FIRs/recommendations
    are populated from real data here; every other field mirrors the CZIB
    schema shape but is left "N/A" since this page has no such data at all.
    """
    try:
        r = requests.get(EASA_IN_URL, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        log(f"EASA Information Notes fetch failed: {e}")
        return []

    table = soup.find("table")
    if not table:
        log("No table found on Information Notes page - structure may have changed")
        return []

    body = table.find("tbody")
    rows = body.find_all("tr") if body else table.find_all("tr")

    notes = []
    for i, row in enumerate(rows, start=1):
        try:
            cells = row.find_all(["td", "th"])
            if len(cells) < 4:
                continue
            area_covered = _clean(cells[0].get_text(" ", strip=True))
            issue_date = _clean(cells[1].get_text(" ", strip=True))
            valid_until = _clean(cells[2].get_text(" ", strip=True))
            recommendations = _clean(cells[3].get_text(" ", strip=True))

            notes.append({
                "id": _slugify_id(area_covered, i),
                "status": "N/A",
                "issue_date": issue_date,
                "revision_date": "N/A",
                "valid_until": valid_until,
                "subject": "N/A",
                "more_info_url": "N/A",
                "affected_airspace": "N/A",
                "affected_countries": _extract_countries(area_covered),
                "description": "N/A",
                "recommendations": recommendations,
                "applies_to_operators": "N/A",
                "applicability_description": "N/A",
                "referenced_publications": "N/A",
                "affected_FIRs": extract_firs(area_covered),
            })
        except Exception as e:
            log(f"  skipped one Information Note row: {e}")

    log(f"EASA Information Notes parsed: {len(notes)}")
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
