#!/usr/bin/env python3
"""Throwaway debug script round 2 - targets the actual content region of the
listing table and a detail page, skipping the huge nav mega-menu."""
import re
import sys

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ConflictZoneDashboardBot/1.0)"}
LIST_URL = "https://www.easa.europa.eu/en/domains/air-operations/czibs"
DETAIL_URL = "https://www.easa.europa.eu/en/domains/air-operations/czibs/czib-2026-08"


def log(msg):
    print(msg, file=sys.stderr)


def main():
    r = requests.get(LIST_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    tables = soup.find_all("table")
    log(f"=== {len(tables)} tables on listing page ===")
    for i, t in enumerate(tables):
        log(f"--- table {i}: class={t.get('class')} id={t.get('id')} ---")
        thead = t.find("thead")
        if thead:
            log(f"  headers: {[th.get_text(' ', strip=True) for th in thead.find_all(['th','td'])]}")
        rows = t.find("tbody").find_all("tr") if t.find("tbody") else t.find_all("tr")
        log(f"  {len(rows)} rows")
        for row in rows[:2]:
            cells = row.find_all(["td", "th"])
            log(f"  row cells ({len(cells)}): {[c.get_text(' ', strip=True) for c in cells]}")
            for c in cells:
                a = c.find("a", href=True)
                if a:
                    log(f"    cell link: href={a['href']!r}")

    log("")
    log(f"=== DETAIL PAGE: {DETAIL_URL} ===")
    r2 = requests.get(DETAIL_URL, headers=HEADERS, timeout=20)
    r2.raise_for_status()
    soup2 = BeautifulSoup(r2.text, "html.parser")

    main_tag = soup2.find("main")
    log(f"<main> found: {main_tag is not None}")
    if main_tag:
        log(f"<main> attrs: {main_tag.attrs}")
        log("=== <main> full text ===")
        log(main_tag.get_text("\n", strip=True)[:8000])
    else:
        # Fallback: locate via the "Note:" strong tag or "Referenced publication" heading
        anchor = soup2.find("strong", string=re.compile("Note", re.IGNORECASE)) or \
                 soup2.find(string=re.compile("Referenced publication", re.IGNORECASE))
        if anchor:
            container = anchor.find_parent(["div", "section", "article"])
            hops = 0
            while container and hops < 4:
                text = container.get_text(" ", strip=True)
                if len(text) > 200:
                    break
                container = container.find_parent(["div", "section", "article"])
                hops += 1
            log(f"=== fallback container (class={container.get('class') if container else None}) text ===")
            log(container.get_text("\n", strip=True)[:8000] if container else "NOT FOUND")

    log("")
    log("=== all elements with class containing 'field' or 'content' (first 15, name+class only) ===")
    for el in soup2.find_all(class_=re.compile("field|content", re.IGNORECASE))[:15]:
        log(f"  <{el.name} class={el.get('class')}> text[:80]={el.get_text(' ', strip=True)[:80]!r}")


if __name__ == "__main__":
    main()
