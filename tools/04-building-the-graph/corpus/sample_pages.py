#!/usr/bin/env python3
"""Draw the stratified sample that a person reads by hand.

Instructor-only. Runs after `classify_pages.py`.

    python tools/04-building-the-graph/corpus/sample_pages.py data/chicago/2022-2026 --n 300

Writes three files under `<dir>/sample300/`:

    pages.jsonl        the pages to read: identity, join fields, text
    regex_labels.csv   what the automatic detectors said about each one
    (the hand labels go beside them, written by whoever reads)

The two files are separate on purpose. A reader who sees the machine's label
next to the text confirms it instead of judging it, and the agreement number
that comes out of a confirmed label measures nothing.

The draw is proportional to the detectors' categories inside each repetition
class, with a floor of four pages per category: the rare types are exactly the
ones a detector can be wrong about without anyone noticing. **The floor makes
the sample unrepresentative by design** -- frequencies computed on these 300
pages are not corpus frequencies, and a share measured here has to be
re-weighted by the population before it means anything (DECISIONS #64).

Seed 42, like the rest of the project.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import random
import re
from pathlib import Path

MONEY = re.compile(r"\$\s?\d[\d,]{2,}")

# The detectors whose precision the hand reading is meant to measure. Kept here
# and not in a shared module because they are a measured object, not a tool: the
# reading of 19/10/2026 put their agreement with a reader at 25%.
DETECTORS = [
    ("prezzi e importi", re.compile(r"schedule of prices|unit price|total (?:bid|contract|amount)|lump sum|price per|extended (?:price|amount)|not[- ]to[- ]exceed", re.I)),
    ("assicurazioni", re.compile(r"certificate of (?:liability )?insurance|acord|policy (?:number|no)|general aggregate|workers? compensation|described policies", re.I)),
    ("EDS e dichiarazioni", re.compile(r"economic disclosure|certificate of filing|affidavit|sworn|notary|disclosure of (?:retained parties|ownership)|anti-?collusion", re.I)),
    ("MBE/WBE e subappalti", re.compile(r"\bM[./]?B[./]?E\b|\bW[./]?B[./]?E\b|minority[- ]owned|women[- ]owned|subcontractor|compliance plan|schedule [cd]-?1", re.I)),
    ("modifiche e proroghe", re.compile(r"modification (?:summary|no)|amendment|change order|extension of (?:time|term)|renewal (?:option|period)|increase.{0,25}amount", re.I)),
    ("gara e aggiudicazione", re.compile(r"solicitation|request for (?:quotation|proposal|bid)|invitation (?:for|to) bid|addendum|bid opening|award(?:ed)? to", re.I)),
    ("ambito e specifiche", re.compile(r"scope of (?:work|services)|statement of work|technical specifications?|specifications? (?:shall|for the|require)|deliverable|work shall (?:consist|include)|shall (?:furnish|provide|install|perform)", re.I)),
    ("parti e firme", re.compile(r"in witness whereof|signature|authorized signatory|attest|duly authorized|hereby agree", re.I)),
    ("durata e scadenze", re.compile(r"commencement date|expiration date|term of (?:this )?(?:contract|agreement)|shall (?:commence|expire|terminate)|effective date", re.I)),
    ("anagrafica e rimandi", re.compile(r"contract (?:po )?number|purchase order|specification no|contract summary|vendor (?:number|name)|department of", re.I)),
]
PRIORITY = [d[0] for d in DETECTORS]


def vendor_tokens(v: str) -> list[str]:
    return [w for w in re.findall(r"[A-Za-z]{5,}", v or "")
            if w.lower() not in ("corporation", "company", "incorporated", "limited",
                                 "services", "group", "the", "and")]


def names_own_contract(r: dict) -> bool:
    """Does the page carry an identifier of the contract it belongs to?"""
    t, tl = r["text"], r["text"].lower()
    po = (r.get("po_number") or "").strip()
    spec = (r.get("spec_number") or "").strip()
    vt = vendor_tokens(r.get("vendor_name", ""))
    return bool((po and po in t)
                or (len(spec) > 3 and spec.lower() in tl)
                or (vt and sum(1 for w in vt if w.lower() in tl) >= max(1, len(vt) // 2)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus_dir", type=Path, nargs="?", default=Path("data/chicago/2022-2026"))
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    cls = {(r["doc_id"], int(r["page"])): r["class"]
           for r in csv.DictReader(open(args.corpus_dir / "page_classes.csv"))}
    pool = collections.defaultdict(list)
    for f in sorted((args.corpus_dir / "corpus").glob("*.jsonl")):
        for line in open(f):
            r = json.loads(line)
            k = cls[(r["doc_id"], r["page"])]
            hit = [name for name, rx in DETECTORS if rx.search(r["text"])]
            r["regex_type"] = next((p for p in PRIORITY if p in hit), "nessuna categoria")
            r["page_class"] = k
            r["names_contract"] = names_own_contract(r)
            r["has_money"] = bool(MONEY.search(r["text"]))
            if k == "propria" and r["names_contract"]:
                pool[("propria", r["regex_type"])].append(r)
            elif k in ("2-4", "5-49"):
                pool[("ripetuta", r["regex_type"])].append(r)
            elif k == "standard":
                pool[("standard", r["regex_type"])].append(r)

    rng = random.Random(args.seed)
    quota = {"propria": round(args.n * 0.733), "ripetuta": round(args.n * 0.133),
             "standard": round(args.n * 0.133)}
    picked = []
    for stratum, target in quota.items():
        keys = [k for k in pool if k[0] == stratum]
        tot = sum(len(pool[k]) for k in keys) or 1
        alloc = {k: max(4, round(target * len(pool[k]) / tot)) for k in keys}
        while sum(alloc.values()) > target:
            alloc[max(alloc, key=lambda k: alloc[k])] -= 1
        for k, m in alloc.items():
            picked += rng.sample(pool[k], min(m, len(pool[k])))
    rng.shuffle(picked)

    out = args.corpus_dir / f"sample{args.n}"
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "pages.jsonl", "w") as f:
        for i, r in enumerate(picked, 1):
            f.write(json.dumps({"page_id": f"p{i:03d}", "doc_id": r["doc_id"], "page": r["page"],
                                "po_number": r.get("po_number", ""), "spec_number": r.get("spec_number", ""),
                                "department": r.get("department", ""), "vendor_name": r.get("vendor_name", ""),
                                "n_chars": r["n_chars"], "text": r["text"]}, ensure_ascii=False) + "\n")
    with open(out / "regex_labels.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["page_id", "doc_id", "page", "page_class", "regex_type", "names_contract", "has_money"])
        for i, r in enumerate(picked, 1):
            w.writerow([f"p{i:03d}", r["doc_id"], r["page"], r["page_class"],
                        r["regex_type"], r["names_contract"], r["has_money"]])
    print(f"{len(picked)} pagine, {sum(r['n_chars'] for r in picked):,} caratteri")
    print(collections.Counter(r["page_class"] for r in picked))
    print(f"scritto {out}/pages.jsonl e {out}/regex_labels.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
