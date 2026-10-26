"""Print the pages of the documents attached to a purchase order.

Written for the manual checks where deciding whether
two vendor names are one company means reading who actually signed. The graph
holds the addresses; the contract holds the legal name.

    python3 -m checks.read_pages --contract 93627 --cover
    python3 -m checks.read_pages --contract 36561 --grep LANGUAGE
    python3 -m checks.read_pages --contract 36561 --page 1 --full

--cover prints the fields the first page of every revision carries: the
contractor's name and the vendor number the city had for it at the time. Those
two, compared across revisions, say whether the counterparty changed.

Run from tools/04-building-the-graph, like the rest of the tools.
"""

from __future__ import annotations

import argparse
import re
import sys

sys.path.insert(0, ".")

COVER_FIELDS = r"Name of Contractor|Vendor Number|Term of Contract|City Department"

# Asked when the page query comes back empty: a purchase order with no pages is
# usually a document that arrived as a scan with no text layer, which is a
# different situation from a purchase order with no document at all. The URL is
# the way out of both.
DOCS = """
MATCH (c:Contract {id: $contract})<-[:INCLUDED_IN_CONTRACT]-(:ContractRecord)
      -[:HAS_DOCUMENT]->(d:Document)
RETURN d.id AS doc, d.hasTextLayer AS text_layer, d.url AS url ORDER BY doc
"""

QUERY = """
MATCH (c:Contract {id: $contract})<-[:INCLUDED_IN_CONTRACT]-(r:ContractRecord)
      -[:HAS_DOCUMENT]->(d:Document)-[:HAS_PAGE]->(p:Page)
WHERE $page IS NULL OR p.page = $page
RETURN d.id AS doc, p.page AS page, p.withheld AS withheld, p.text AS text
ORDER BY doc, page
"""


def no_pages(contract: str) -> int:
    """Explain an empty result, and hand over the URLs.

    Half the documents in the graph have no pages: they came as scans with no
    text layer, and the corpus extracted nothing from them. Reporting that as
    "no document" would send someone looking for a file that exists.
    """
    from database.lpg.graph_db import Neo4jDB

    db = Neo4jDB()
    try:
        with db._driver.session(database=db._database) as session:
            docs = [dict(r) for r in session.run(DOCS, contract=contract)]
    finally:
        db.close()

    if not docs:
        print(f"Contract {contract} has no document in the graph.")
        return 1

    print(f"Contract {contract} has {len(docs)} document(s), none with "
          f"extracted text. Open them in a browser and read them by eye:\n")
    for d in docs:
        why = "scan, no text layer" if not d["text_layer"] else "text layer, not extracted"
        print(f"  {d['doc']}  ({why})")
        print(f"  {d['url']}\n")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--contract", required=True, help="purchase order number")
    ap.add_argument("--page", type=int, help="a single page instead of all of them")
    ap.add_argument("--grep", help="show only lines matching this, case-insensitive")
    ap.add_argument("--full", action="store_true",
                    help="whole page instead of the first 1200 characters")
    ap.add_argument("--cover", action="store_true",
                    help="only the identifying fields on each revision's first page")
    args = ap.parse_args()

    from database.lpg.graph_db import Neo4jDB

    db = Neo4jDB()
    try:
        with db._driver.session(database=db._database) as session:
            rows = [dict(r) for r in session.run(
                QUERY, contract=args.contract,
                page=1 if args.cover else args.page)]
    finally:
        db.close()

    if not rows:
        return no_pages(args.contract)

    if args.cover:
        # Only page 1: "City Department" also occurs in the body of every
        # contract, and matching it everywhere buries the four lines wanted.
        pattern = re.compile(COVER_FIELDS, re.I)
        rows = [r for r in rows if r["page"] == 1]
    else:
        pattern = re.compile(re.escape(args.grep), re.I) if args.grep else None
    shown = 0
    for row in rows:
        # A withheld page has a node and no text: the PII filter kept the label
        # and dropped the content. Saying so beats printing an empty page.
        if row["withheld"]:
            print(f"\n--- {row['doc']} p.{row['page']}  [withheld, no text]")
            continue
        text = row["text"] or ""
        if pattern:
            hits = [l for l in text.splitlines() if pattern.search(l)]
            if not hits:
                continue
            print(f"\n--- {row['doc']} p.{row['page']}")
            for line in hits:
                print(f"    {line.strip()}")
        else:
            print(f"\n--- {row['doc']} p.{row['page']}")
            print(text if args.full else text[:1200])
        shown += 1

    if pattern and not shown:
        print(f"'{args.grep}' appears on none of the {len(rows)} pages.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
