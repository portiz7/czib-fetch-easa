#!/usr/bin/env python3
"""
scrape_easa_czibs.py
---------------------
Complete, two-phase scraper for EASA's public Conflict Zone Information
Bulletins (CZIBs).

  Phase 1 - get_czib_list():    listing page -> {czib_number, status, detail_url}
  Phase 2 - parse_czib_detail(): one detail page -> full normalized record

Both phases were written against the REAL page structure (confirmed via a
live fetch, not guessed):

  Listing page (https://www.easa.europa.eu/en/domains/air-operations/czibs)
  has two <table class="cols-7">, one whose id contains "status-active" and
  one whose id contains "status-withdrawn". Columns: Issue date | Revision
  date | Valid until | Subject/CZIB number (title+number+status combined in
  one cell) | (blank) | More info (a "view" link) | (blank). The CZIB number
  isn't in its own cell - it's derived from the detail link's URL slug
  instead (e.g. href=".../czibs/czib-2026-08" -> "CZIB-2026-08"), which is
  far more reliable than regexing it out of the combined title text.

  Detail page (e.g. .../czibs/czib-2026-08) renders as a strict label/value
  sequence inside <main id="main">: Status, CZIB number, Issue date,
  [Revision date - only present when the bulletin has been revised],
  Valid until, "Referenced publication(s):", Affected Airspace, Affected
  Countries, Applicability, Applicability Description, Description,
  "Recommendation(s)", then an optional "Note:", then boilerplate
  ("Contact us" / email-alert signup) that marks the end of real content.

Important deviation from the originally-suggested regex: real CZIB text
writes FIRs as "FIR <name> (<ICAO>)" (e.g. "FIR Amman (OJAC)"), not
"<ICAO> FIR". extract_firs() matches both forms so it actually works
against production text, but always returns results in "<ICAO> FIR" form.
"""

import json
import re
import sys
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.easa.europa.eu"
LIST_URL = f"{BASE_URL}/en/domains/air-operations/czibs"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ConflictZoneDashboardBot/1.0)"}
TIMEOUT = 20
RETRIES = 3
RETRY_BACKOFF = 2  # seconds, multiplied by attempt number
REQUEST_DELAY = 0.3  # seconds between detail-page requests, to be polite

OUT_PATH = "data/raw_easa.json"

# Detail-page labels, in the order they appear. Used to split the page's
# flattened text into label -> value-lines. "Contact us" isn't a data label,
# it's where real content ends (email-alert signup boilerplate follows).
DETAIL_LABELS = [
    "Status",
    "CZIB number",
    "Issue date",
    "Revision date",
    "Valid until",
    "Referenced publication(s):",
    "Affected Airspace",
    "Affected Countries",
    "Applicability",
    "Applicability Description",
    "Description",
    "Recommendation(s)",
    "Note:",
]
CONTENT_END_MARKERS = ["Contact us"]


def log(msg):
    print(f"[scrape_easa_czibs] {msg}", file=sys.stderr)


def _get(url):
    """GET with retries/backoff. Raises on final failure."""
    last_exc = None
    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            return r
        except Exception as e:
            last_exc = e
            log(f"  GET {url} failed (attempt {attempt}/{RETRIES}): {e}")
            if attempt < RETRIES:
                time.sleep(RETRY_BACKOFF * attempt)
    raise last_exc


def _clean(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


def extract_firs(text):
    """
    Detect ICAO FIR codes mentioned in free text. Real EASA CZIB text uses
    at least three different phrasings, confirmed against live bulletins:
      - "FIR Amman (OJAC)"                    - name, then code in parens
      - "Bahrain (Bahrain FIR – OBBB)"         - name FIR <en-dash> code
      - "OJAC FIR"                             - the originally-suggested form
    The originally-suggested r"\\b[A-Z]{4}\\s+FIR\\b" pattern only covers the
    third case and was confirmed to match NOTHING on a real single-country
    bulletin, and to catch only 1 of 5 codes on the multi-country Gulf one
    (which uses the second form) - all three are checked here. Always
    returns results normalized to "<ICAO> FIR".
    """
    if not text:
        return []
    codes = []
    codes += re.findall(r"\b([A-Z]{4})\s+FIR\b", text)  # "OJAC FIR" form
    codes += re.findall(r"FIR\s+[^().]*?\(([A-Z]{4})\)", text)  # "FIR Amman (OJAC)" form
    codes += re.findall(r"FIR\s*[–‒-]\s*([A-Z]{4})\b", text)  # "Bahrain FIR – OBBB" form
    seen = []
    for c in codes:
        if c not in seen:
            seen.append(c)
    return [f"{c} FIR" for c in seen]


def get_czib_list():
    """Phase 1: scrape the listing page for {czib_number, status, detail_url}."""
    log(f"Fetching listing page: {LIST_URL}")
    try:
        r = _get(LIST_URL)
    except Exception as e:
        log(f"Listing page fetch failed permanently: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    tables = soup.find_all("table")
    log(f"Found {len(tables)} table(s) on listing page")

    items = []
    for table in tables:
        table_id = (table.get("id") or "").lower()
        if "withdrawn" in table_id:
            table_status = "Withdrawn"
        elif "active" in table_id:
            table_status = "Active"
        else:
            table_status = None  # unknown - fall back to per-row text below

        body = table.find("tbody")
        rows = body.find_all("tr") if body else table.find_all("tr")

        for row in rows:
            try:
                cells = row.find_all(["td", "th"])
                if len(cells) < 4:
                    continue
                link = row.find("a", href=True)
                if not link:
                    log("  skipped a row with no detail link")
                    continue

                href = link["href"]
                slug = href.rstrip("/").split("/")[-1]
                czib_number = slug.upper()
                detail_url = href if href.startswith("http") else f"{BASE_URL}{href}"

                title_cell_text = _clean(cells[3].get_text(" ", strip=True))
                status = table_status
                title = title_cell_text
                if czib_number:
                    title = re.sub(re.escape(czib_number), "", title, flags=re.IGNORECASE)
                if status:
                    title = re.sub(rf"\b{re.escape(status)}\b\s*$", "", title, flags=re.IGNORECASE)
                else:
                    # No table-level status known - try to pull the trailing word
                    # ("Active"/"Withdrawn") off the combined cell text instead.
                    m = re.search(r"\b(Active|Withdrawn)\s*$", title, flags=re.IGNORECASE)
                    if m:
                        status = m.group(1)
                        title = title[: m.start()]
                title = _clean(title)

                items.append({
                    "czib_number": czib_number,
                    "status": status or "Unknown",
                    "title": title,
                    "detail_url": detail_url,
                })
            except Exception as e:
                log(f"  skipped one listing row: {e}")

    log(f"Listing parsed: {len(items)} CZIBs")
    return items


def _split_labelled_sections(main_text):
    """
    Turns the detail page's flattened, line-per-block text into
    {label: [value_lines...]}, using DETAIL_LABELS as split points.
    Robust to labels being absent entirely (e.g. "Revision date" only
    appears on bulletins that have actually been revised).
    """
    lines = [l for l in main_text.split("\n") if l.strip()]
    label_set = {l.lower().rstrip(":") for l in DETAIL_LABELS}
    end_set = {m.lower() for m in CONTENT_END_MARKERS}

    sections = {}
    current = None
    for line in lines:
        key = line.lower().rstrip(":")
        if key in end_set:
            current = None
            continue
        if key in label_set:
            # Map back to the canonical label string (preserving "(s):" etc.)
            current = next(l for l in DETAIL_LABELS if l.lower().rstrip(":") == key)
            sections.setdefault(current, [])
            continue
        if current:
            sections[current].append(line)
    return sections


def _extract_referenced_publications(soup):
    """
    Finds the "Referenced publication(s):" section by its heading and pulls
    out any real <a href> links within it as {title, url}. Falls back to a
    single {title: <plain text>, url: None} entry when the section exists
    but contains no hyperlinks (which is common - EASA often just names the
    publication in prose without linking it).
    """
    heading = soup.find(string=re.compile(r"Referenced publication", re.IGNORECASE))
    if not heading:
        return []
    container = heading.find_parent(["h3", "h2", "div", "p"])
    if not container:
        return []
    # Look in the container itself and a couple of following siblings for links.
    scope_nodes = [container] + container.find_next_siblings(limit=3)
    links = []
    for node in scope_nodes:
        if hasattr(node, "find_all"):
            for a in node.find_all("a", href=True):
                title = _clean(a.get_text(" ", strip=True))
                if title:
                    href = a["href"]
                    url = href if href.startswith("http") else f"{BASE_URL}{href}"
                    links.append({"title": title, "url": url})
    if links:
        return links

    # No links - fall back to whatever prose text sits in the section.
    next_text = container.find_next_sibling()
    text = _clean(next_text.get_text(" ", strip=True)) if next_text else ""
    return [{"title": text, "url": None}] if text else []


def _extract_more_info_url(soup, detail_url):
    link = soup.find("a", string=re.compile(r"more info", re.IGNORECASE))
    if link and link.get("href"):
        href = link["href"]
        return href if href.startswith("http") else f"{BASE_URL}{href}"
    return detail_url  # best available fallback - this page IS the authoritative record


def parse_czib_detail(url):
    """Phase 2: scrape one CZIB's detail page into a full normalized record."""
    log(f"Fetching detail page: {url}")
    try:
        r = _get(url)
    except Exception as e:
        log(f"  Detail page fetch failed permanently: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    main = soup.find("main")
    if not main:
        log(f"  No <main> found on {url} - page structure may have changed, skipping")
        return None

    sections = _split_labelled_sections(main.get_text("\n", strip=True))

    def one_line(label, default=""):
        vals = sections.get(label, [])
        return _clean(vals[0]) if vals else default

    def joined(label, default=""):
        vals = sections.get(label, [])
        return _clean(" ".join(vals)) if vals else default

    h1 = main.find("h1")
    subject = _clean(h1.get_text(" ", strip=True)) if h1 else one_line("CZIB number")

    valid_until_raw = one_line("Valid until")
    m = re.search(r"\d{2}/\d{2}/\d{4}", valid_until_raw)
    valid_until = m.group(0) if m else valid_until_raw

    affected_airspace = joined("Affected Airspace")
    # NOT joined()+re-split: each country is its own line in the source HTML
    # (e.g. ["Bahrain", "Kuwait", ..., "United Arab Emirates"]) - joining them
    # with spaces first and then trying to re-split on comma/newline destroys
    # that boundary (confirmed against live data: produced one fused string
    # "Bahrain Kuwait Qatar Oman United Arab Emirates" instead of 5 entries).
    # A line can *also* itself be comma-separated, so split each line on "," too.
    affected_countries = []
    for line in sections.get("Affected Countries", []):
        for part in line.split(","):
            part = part.strip()
            if part:
                affected_countries.append(part)

    applicability_raw = joined("Applicability").lower()
    applies_to_operators = "applies to operators" in applicability_raw and "not" not in applicability_raw

    description = joined("Description")
    recommendations = joined("Recommendation(s)")
    note = joined("Note:")
    if note:
        recommendations = f"{recommendations} Note: {note}".strip()
    applicability_description = joined("Applicability Description")

    all_text_for_firs = " ".join([
        affected_airspace, description, recommendations, applicability_description,
    ])

    record = {
        "czib_number": one_line("CZIB number"),
        "status": one_line("Status"),
        "issue_date": one_line("Issue date"),
        "revision_date": one_line("Revision date"),  # "" when never revised - field just absent on the page
        "valid_until": valid_until,
        "subject": subject,
        "more_info_url": _extract_more_info_url(soup, url),

        "affected_airspace": affected_airspace,
        "affected_countries": affected_countries,
        "description": description,
        "recommendations": recommendations,

        "applies_to_operators": applies_to_operators,
        "applicability_description": applicability_description,

        "referenced_publications": _extract_referenced_publications(soup),

        "affected_FIRs": extract_firs(all_text_for_firs),
    }
    return record


def scrape_all():
    """Runs both phases end to end. Returns a list of full CZIB records."""
    listing = get_czib_list()
    results = []
    for i, item in enumerate(listing):
        detail = parse_czib_detail(item["detail_url"])
        if detail is None:
            log(f"  skipping {item['czib_number']} - detail parse failed")
            continue
        # Listing-page values win where the two disagree (they're the
        # canonical source for these three fields); detail page fills in
        # everything else.
        detail["czib_number"] = item["czib_number"] or detail["czib_number"]
        detail["status"] = item["status"] or detail["status"]
        results.append(detail)
        if i < len(listing) - 1:
            time.sleep(REQUEST_DELAY)
    log(f"scrape_all complete: {len(results)}/{len(listing)} CZIBs fully parsed")
    return results


def main():
    czibs = scrape_all()
    out = {
        "source": "EASA",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "czibs": czibs,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))

    import os
    os.makedirs("data", exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    log(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
