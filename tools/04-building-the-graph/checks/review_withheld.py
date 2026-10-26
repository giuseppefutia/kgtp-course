"""Read the pages the PII filter withheld, to confirm or overturn its decision.

The human gate of the corpus pipeline, and the only step that must not be
automated. Nothing here writes: the text is printed to the terminal and goes
nowhere else, because the whole reason these pages were withheld is that they
should not land in a file.

    python3 -m checks.review_withheld                  what is waiting, worst first
    python3 -m checks.review_withheld --po 135798      the reasons, page by page
    python3 -m checks.review_withheld --po 135798 --text
    python3 -m checks.review_withheld --po 135798 --text --page 12

The text comes from the original PDF under data/chicago/raw/pdfs/, which is
gitignored. It was never extracted to corpus/ and is not in the graph.

What to decide, page by page: the filter scores multiplicity, not presence. A
contract page full of addresses is normal; a dozen individuals each paired with
a home address and a personal mailbox is not. Officials signing in their
official capacity stay. Directories of personal contact details go.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, ".")

ROOT = Path(__file__).resolve().parents[3]
PDF_DIR = ROOT / "data" / "chicago" / "raw" / "pdfs"


def withheld(session, po=None):
    query = """
        MATCH (d:Document)-[:HAS_PAGE]->(p:Page {withheld: true})
        WHERE $po IS NULL OR d.poNumber = $po
        RETURN d.poNumber AS po, d.revision AS revision, p.page AS page,
               p.piiScore AS score, p.piiReasons AS reasons,
               p.personalEmails AS emails, p.phones AS phones,
               p.streetAddresses AS addresses
        ORDER BY p.piiScore DESC, d.poNumber, p.page
    """
    return [dict(r) for r in session.run(query, po=po)]


def page_text(po, revision, page):
    """Print one page of the original PDF. Requires pdftotext."""
    pdf = PDF_DIR / f"{po}_r{revision}.pdf"
    if not pdf.exists():
        return f"[the PDF is not on disk: {pdf.name}]"
    out = subprocess.run(
        ["pdftotext", "-f", str(page), "-l", str(page), "-raw", str(pdf), "-"],
        capture_output=True, text=True)
    return out.stdout.strip() or "[no text layer on this page]"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--po", help="review one purchase order")
    ap.add_argument("--page", type=int, help="one page of it")
    ap.add_argument("--text", action="store_true", help="print the page text")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    from database.lpg.graph_db import Neo4jDB

    db = Neo4jDB()
    try:
        with db._driver.session(database=db._database) as session:
            rows = withheld(session, args.po)
    finally:
        db.close()

    if args.page:
        rows = [r for r in rows if r["page"] == args.page]
    if not rows:
        print("nothing withheld for that selection")
        return 0

    if not args.po:
        # The queue, worst first. Six documents carry a sixth of the total, so
        # reading in this order is not the same as reading a random sixth.
        by_doc = {}
        for r in rows:
            key = (r["po"], r["revision"])
            by_doc.setdefault(key, []).append(r)
        print(f"{len(rows)} withheld pages across {len(by_doc)} documents\n")
        ordered = sorted(by_doc.items(), key=lambda kv: -len(kv[1]))
        for (po, rev), pages in ordered[:args.limit]:
            worst = max(p["score"] or 0 for p in pages)
            print(f"  PO {po:<10} r{rev:<3} {len(pages):3d} pages   worst score {worst}")
        if len(ordered) > args.limit:
            print(f"  ... and {len(ordered) - args.limit} more documents")
        print(f"\n  python3 -m checks.review_withheld --po {ordered[0][0][0]} --text")
        return 0

    for r in rows:
        print("=" * 70)
        print(f"PO {r['po']} r{r['revision']}  page {r['page']}  score {r['score']}")
        print(f"  {', '.join(r['reasons'] or [])}")
        print(f"  emails {r['emails']}  phones {r['phones']}  addresses {r['addresses']}")
        if args.text:
            print("-" * 70)
            print(page_text(r["po"], r["revision"], r["page"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
