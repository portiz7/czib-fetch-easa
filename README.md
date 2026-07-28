# czib-fetch-easa

Source repo 1 of 2 in a small pipeline that feeds the
[Test_2_CZIB](https://github.com/portiz7/test_2_czib) conflict-zone dashboard.

```
czib-fetch-easa       (this repo)  ─┐
czib-fetch-opsgroup                 ├─▶ conflict-zones-combine ─▶ Test_2_CZIB (dashboard)
                                    ─┘
```

## What this repo does

Every 6 hours (and on manual `workflow_dispatch`), `scripts/fetch_easa.py`:

1. Pulls EASA's public JSON export of all CZIBs (Conflict Zone Information Bulletins) —
   no login required. Each raw entry becomes `{nid, title, status, countries, issue_date,
   valid_until, coordinates}` — `countries` is a list because some bulletins (e.g. the
   Gulf one) cover several countries at once. Note: this export does **not** expose a
   formal bulletin number like "CZIB-2026-04" — only an internal `nid`, which is what
   downstream uses as a stable per-bulletin reference instead.
2. Pulls EASA's public Information Notes page (medium-risk, non-CZIB zones) — metadata
   only, since the full text is gated behind the EASA CZ Hub login.
3. Writes the raw, unprocessed result to `data/raw_easa.json`, and commits it if it
   changed.

This repo does **no** cleaning, deduplication, cross-referencing with other sources, or
AI synthesis — that all happens downstream in
[conflict-zones-combine](https://github.com/portiz7/conflict-zones-combine), which reads this repo's
`data/raw_easa.json` directly over `https://raw.githubusercontent.com/...` (this repo is
public specifically so that read needs no auth token).

## Local run

```
pip install -r requirements.txt
python scripts/fetch_easa.py
```

## Scope

Does **not** touch the EASA CZ Hub (authenticated, member-states/authorised-operators
only) — out of scope by design for a script that can't hold a login session.
