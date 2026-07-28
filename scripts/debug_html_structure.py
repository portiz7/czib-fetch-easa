#!/usr/bin/env python3
"""Throwaway debug script - dumps real HTML structure of the CZIB listing
page and one detail page so the real scraper can be written against actual
markup instead of guesses. Not part of the pipeline; delete after use."""
import re
import sys

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ConflictZoneDashboardBot/1.0)"}
LIST_URL = "https://www.easa.europa.eu/en/domains/air-operations/czibs"


def log(msg):
    print(msg, file=sys.stderr)


def main():
    r = requests.get(LIST_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    links = soup.find_all("a", href=re.compile(r"/czibs/czib-", re.IGNORECASE))
    log(f"=== LISTING PAGE: {len(links)} links matching /czibs/czib- ===")
    seen = set()
    sample_hrefs = []
    for a in links:
        href = a.get("href")
        if href in seen:
            continue
        seen.add(href)
        sample_hrefs.append(href)
        # Print the link's own text plus a bit of surrounding row/card context
        parent_text = a.find_parent(["tr", "article", "li", "div"])
        ctx = parent_text.get_text(" ", strip=True)[:200] if parent_text else ""
        log(f"  href={href!r} text={a.get_text(' ', strip=True)!r} ctx={ctx!r}")

    log(f"=== total tables on listing page: {len(soup.find_all('table'))} ===")

    if not sample_hrefs:
        log("No detail links found via regex - dumping first 3000 chars of body text for manual inspection")
        log(soup.get_text(" ", strip=True)[:3000])
        return

    detail_href = sample_hrefs[0]
    detail_url = detail_href if detail_href.startswith("http") else f"https://www.easa.europa.eu{detail_href}"
    log(f"=== FETCHING DETAIL PAGE: {detail_url} ===")
    r2 = requests.get(detail_url, headers=HEADERS, timeout=20)
    r2.raise_for_status()
    soup2 = BeautifulSoup(r2.text, "html.parser")

    for tag in ["h1", "h2", "h3", "h4", "dt", "strong", "b"]:
        found = soup2.find_all(tag)
        if found:
            log(f"--- <{tag}> tags ({len(found)}) ---")
            for el in found[:25]:
                log(f"  {el.get_text(' ', strip=True)[:150]!r}")

    log("=== full page text, first 6000 chars ===")
    log(soup2.get_text("\n", strip=True)[:6000])


if __name__ == "__main__":
    main()
