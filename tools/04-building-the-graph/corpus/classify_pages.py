#!/usr/bin/env python3
"""Tell a page proper to its contract from a page the city reuses everywhere.

Instructor-only. Runs after `extract_contracts.py`.

    python tools/04-building-the-graph/corpus/classify_pages.py data/chicago/2022-2026

Writes `<dir>/page_classes.csv`, one row per page, and prints the distribution.

The criterion is repetition. A clause of the city's standard terms comes back
identical on hundreds of orders; a page with the object, the amounts and the
signatures does not. So each page is normalised -- lowercased, digits and
punctuation dropped, because the boilerplate carries the order number and the
dates inserted into it and without that step every copy looks unique -- and
then counted by how many DISTINCT CONTRACTS share its fingerprint. Contracts,
not documents: the revisions of one order share nearly every page, and counting
documents would make a contract's own boilerplate look like it travels.

Measured 19/10/2026 over the 2022-2026 census, 229,518 pages:

    propria del contratto (1 contratto)     121,963   53.1%   116,331 distinte
    ripetuta su 2-4 contratti                17,317    7.5%     5,809
    ripetuta su 5-49                         21,933    9.6%     1,864
    standard (50+ contratti)                 66,988   29.2%       411
    troppo corta per dire                     1,317    0.6%

The last column is the point: 411 distinct pages account for 66,988 copies and
45.5% of all the text in the corpus. Those 411 are mostly one thing -- a
307-page bond ordinance exported from Legistar and attached whole to the grants
it funds (see DECISIONS #64).
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import re
from pathlib import Path

NON_ALPHA = re.compile(r"[^a-z ]+")
SPACES = re.compile(r"\s+")


def fingerprint(text: str) -> str | None:
    """None when the page is too short for repetition to mean anything."""
    n = SPACES.sub(" ", NON_ALPHA.sub(" ", text.lower())).strip()
    return hashlib.sha1(n.encode()).hexdigest()[:16] if len(n) >= 80 else None


def band(n_contracts: int | None) -> str:
    if n_contracts is None:
        return "corta"
    if n_contracts == 1:
        return "propria"
    if n_contracts <= 4:
        return "2-4"
    return "5-49" if n_contracts <= 49 else "standard"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus_dir", type=Path, nargs="?", default=Path("data/chicago/2022-2026"))
    args = ap.parse_args()

    rows, by_key = [], collections.defaultdict(set)
    for f in sorted((args.corpus_dir / "corpus").glob("*.jsonl")):
        for line in open(f):
            r = json.loads(line)
            key = fingerprint(r["text"])
            po = r.get("po_number") or r["doc_id"].split("_r")[0]
            rows.append((key, r["doc_id"], po, r["page"], r["n_chars"]))
            if key:
                by_key[key].add(po)

    out = args.corpus_dir / "page_classes.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["page_key", "doc_id", "po_number", "page", "n_chars",
                    "contracts_sharing", "class"])
        for key, doc, po, page, n in rows:
            shared = len(by_key[key]) if key else ""
            w.writerow([key or "__short__", doc, po, page, n, shared,
                        band(len(by_key[key]) if key else None)])

    tot = len(rows)
    print(f"{'classe':12} {'pagine':>9} {'%':>6} {'caratteri':>13} {'distinte':>10}")
    for b in ("propria", "2-4", "5-49", "standard", "corta"):
        sel = [r for r in rows if band(len(by_key[r[0]]) if r[0] else None) == b]
        if not sel:
            continue
        ch = sum(r[4] for r in sel)
        print(f"{b:12} {len(sel):9,} {len(sel)/tot:6.1%} {ch:13,} {len({r[0] for r in sel}):10,}")
    print(f"\nscritto {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
