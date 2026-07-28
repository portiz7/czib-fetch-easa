#!/usr/bin/env python3
"""Throwaway debug: inspect the real table structure of the Information
Notes page (analogous to the CZIB listing table debug done earlier)."""
import sys
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ConflictZoneDashboardBot/1.0)"}
URL = "https://www.easa.europa.eu/en/domains/air-operations/czibs/information"


def log(msg):
    print(msg, file=sys.stderr)


def main():
    r = requests.get(URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    tables = soup.find_all("table")
    log(f"=== {len(tables)} tables ===")
    for i, t in enumerate(tables):
        log(f"--- table {i}: id={t.get('id')} class={t.get('class')} ---")
        thead = t.find("thead")
        if thead:
            log(f"  headers: {[th.get_text(' ', strip=True) for th in thead.find_all(['th','td'])]}")
        body = t.find("tbody")
        rows = body.find_all("tr") if body else t.find_all("tr")
        log(f"  {len(rows)} rows")
        for row in rows[:3]:
            cells = row.find_all(["td", "th"])
            log(f"  row ({len(cells)} cells):")
            for j, c in enumerate(cells):
                a = c.find("a", href=True)
                log(f"    [{j}] text={c.get_text(' ', strip=True)!r} link={a['href'] if a else None}")


if __name__ == "__main__":
    main()
