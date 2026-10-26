"""Choose which contract documents to fetch, and write the manifest.

Instructor-only. The manifest is the list `download_pdfs.py` works through and
the join key everything downstream uses, so what it contains decides what the
module 5 comparison can be asked about.

    python build_manifest.py --limit 3000            # a working corpus
    python build_manifest.py --limit 0               # every document with a text layer
    python build_manifest.py --limit 500 --dry-run   # counts only

Two strata, because they answer different questions.

The **random** stratum, drawn per department and amount band with a fixed seed,
is what makes "how often do the text and the structured record disagree" a
measurable frequency rather than an anecdote. Sampling has to be blind for that
number to mean anything.

The **pinned** stratum is the handful of purchase orders the modules tell a
story about, with every revision they have. Those cannot be left to chance: a
lab built around PO 27019 needs PO 27019.

Documents approved before 2016 are excluded by default. Not a judgement about
their interest -- they are the older and often the more interesting ones -- but
their PDFs have no text layer at all, so fetching them costs the same and yields
nothing until OCR exists. See A15.
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCE = ROOT / "data" / "chicago" / "raw" / "rsxa-ify5_2026-08-11.csv"
DEFAULT_OUT = ROOT / "data" / "chicago" / "corpus_manifest.csv"

COLUMNS = ["po_number", "revision", "spec_number", "department", "vendor_name",
           "vendor_id", "contract_type", "award_amount", "approval_date",
           "description", "amount_band", "pdf_url", "stratum"]

# The purchase orders the modules are written around: PO 27019 changes vendor
# in 2020, T25581 changes department six times. Their revisions are what make
# a point-in-time question answerable from the documents as well as the graph.
PINNED = ["27019", "T25581"]

# Wide bands on purpose. They exist to keep a sample from being all small
# contracts, not to model the distribution.
BANDS = [(50_000, "lt50k"), (500_000, "50k-500k"), (5_000_000, "500k-5m")]


def band(amount: str) -> str:
    try:
        value = float(amount or 0)
    except ValueError:
        return "unknown"
    for ceiling, name in BANDS:
        if value < ceiling:
            return name
    return "gt5m"


def year(approval: str) -> int | None:
    """Pull the year out of an approval date, whatever shape it arrives in.

    The portal serves `MM/DD/YYYY` in the CSV and ISO in the API, and the two
    are not interchangeable: reading the first four characters of `09/16/2002`
    gives no year at all, and a filter built on it silently keeps nothing. The
    caller counts what fails to parse for the same reason.
    """
    if not approval:
        return None
    text = approval.strip()
    if "/" in text:
        parts = text.split("/")
        return int(parts[2][:4]) if len(parts) == 3 and parts[2][:4].isdigit() else None
    return int(text[:4]) if text[:4].isdigit() else None


def read_source(path: Path, min_year: int):
    """Yield one manifest row per contract revision that has a document.

    Rows without a PDF link are the majority and are dropped here rather than
    downstream: `download_pdfs.py` would otherwise spend a request discovering
    the same thing.
    """
    kept, no_pdf, too_old, unparsable = 0, 0, 0, 0
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            url = (row.get("Contract PDF") or "").strip()
            if not url:
                no_pdf += 1
                continue
            approved = (row.get("Approval Date") or "").strip()
            po = (row.get("Purchase Order (Contract) Number") or "").strip()
            y = year(approved)
            # A pinned order skips the year filter. Its revisions are the reason
            # it is pinned, and for T25581 they are all older than the cutoff:
            # applying the filter would drop exactly the documents the temporal
            # module needs. They will have no text until OCR exists (A15), but
            # the PDFs are on disk by then.
            if po not in PINNED:
                if y is None:
                    unparsable += 1
                    continue
                if y < min_year:
                    too_old += 1
                    continue
            kept += 1
            yield {
                "po_number": (row.get("Purchase Order (Contract) Number") or "").strip(),
                "revision": (row.get("Revision Number") or "0").strip(),
                "spec_number": (row.get("Specification Number") or "").strip(),
                "department": (row.get("Department") or "").strip(),
                "vendor_name": (row.get("Vendor Name") or "").strip(),
                "vendor_id": (row.get("Vendor ID") or "").strip(),
                "contract_type": (row.get("Contract Type") or "").strip(),
                "award_amount": (row.get("Award Amount") or "").strip(),
                "approval_date": approved,
                "description": (row.get("Purchase Order Description") or "").strip(),
                "amount_band": band(row.get("Award Amount") or ""),
                "pdf_url": url,
            }
    print(f"source: {kept:,} rows with a document from {min_year} on")
    print(f"        {no_pdf:,} without a PDF link, {too_old:,} older than {min_year}, "
          f"{unparsable:,} with an unreadable approval date")


def choose(rows, limit: int, seed: int, random_share: float = 0.2):
    """Select the documents, and record on each row how it was chosen.

      pinned      the orders the modules are written around
      random      a flat uniform draw
      stratified  round-robin over department x band, for coverage

    A frequency may only be computed over `random`. The stratified draw
    over-samples small strata by design -- every stratum smaller than the
    per-stratum budget is taken whole -- so a rate read off it is not a rate.
    """
    rng = random.Random(seed)

    pinned = [dict(r, stratum="pinned") for r in rows if r["po_number"] in PINNED]
    rest = [r for r in rows if r["po_number"] not in PINNED]
    rng.shuffle(rest)

    if limit <= 0:
        return pinned + [dict(r, stratum="all") for r in rest], 0

    budget = max(0, limit - len(pinned))
    n_random = int(budget * random_share)
    chosen = pinned + [dict(r, stratum="random") for r in rest[:n_random]]

    strata = defaultdict(list)
    for row in rest[n_random:]:
        strata[(row["department"], row["amount_band"])].append(row)
    for bucket in strata.values():
        rng.shuffle(bucket)

    keys = sorted(strata)
    rng.shuffle(keys)
    while len(chosen) < limit:
        drawn = False
        for key in keys:
            if strata[key]:
                chosen.append(dict(strata[key].pop(), stratum="stratified"))
                drawn = True
                if len(chosen) >= limit:
                    break
        if not drawn:
            break  # every stratum is empty: the source has fewer rows than asked
    return chosen, len(strata)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--limit", type=int, default=3000,
                    help="how many documents to select; 0 means all of them")
    ap.add_argument("--min-year", type=int, default=2016,
                    help="documents approved before this have no text layer")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--replace", action="store_true",
                    help="discard the current manifest instead of adding to it")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.source.exists():
        print(f"source not found: {args.source}", file=sys.stderr)
        return 1

    rows = list(read_source(args.source, args.min_year))
    chosen, strata = choose(rows, args.limit, args.seed)

    # Adding to the manifest rather than replacing it, because dropping a row
    # discards work that cannot be redone cheaply: its PDF is on disk, its text
    # is extracted, and its withheld pages have been read by a person. A new
    # draw would silently orphan all three.
    if args.out.exists() and not args.replace:
        with args.out.open(encoding="utf-8") as f:
            existing = list(csv.DictReader(f))
        seen = {(r["po_number"], r["revision"]) for r in chosen}
        kept = [dict({c: r.get(c, "") for c in COLUMNS},
                     stratum=r.get("stratum") or "inherited")
                for r in existing if (r["po_number"], r["revision"]) not in seen]
        print(f"existing: {len(existing)} rows, {len(kept)} of them not re-drawn "
              f"and kept")
        chosen = chosen + kept

    pos = len({r["po_number"] for r in chosen})
    print(f"selected: {len(chosen):,} documents, {pos:,} purchase orders, "
          f"{strata:,} department x band strata")
    pinned_found = sorted({r["po_number"] for r in chosen if r["po_number"] in PINNED})
    missing = sorted(set(PINNED) - set(pinned_found))
    print(f"pinned:   {', '.join(pinned_found) or 'none'}"
          + (f"   MISSING: {', '.join(missing)}" if missing else ""))

    if args.dry_run:
        print("\ndry run, nothing written")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(chosen)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
