"""Look up a business name across the contracts and the licences.

Written to replace an external company register that turned out to need an
account. The city already publishes what that register would have told us: a
business licence carries the **legal entity name** and, separately, the name the
business trades under. They differ on most rows, and the pairing is the city's
own assertion that the two names are one business.

    python3 -m checks.whois "CRAFT METAL SPINNING"
    python3 -m checks.whois "PRAXAIR"

Note which field is which. `name` on a licence is the legal entity;
`businessName` holds `DOING BUSINESS AS NAME`, the trade name. The two read the
other way round from what the property names suggest.
"""

from __future__ import annotations

import argparse
import sys

sys.path.insert(0, ".")

CONTRATTI = """
MATCH (o:Organization) WHERE o.source = 'CONTRACTS' AND toUpper(o.name) CONTAINS $q
OPTIONAL MATCH (o)<-[:HAS_VENDOR]-(c:Contract)
RETURN o.name AS name, o.id AS id, o.addresses[0] AS address,
       count(DISTINCT c) AS contracts
ORDER BY contracts DESC LIMIT 10
"""

LICENZE = """
MATCH (l:LicenseRecord)
WHERE toUpper(coalesce(l.name, '')) CONTAINS $q
   OR toUpper(coalesce(l.businessName, '')) CONTAINS $q
RETURN DISTINCT l.name AS legal, l.businessName AS trading,
       l.address AS address, l.addressPostalCode AS postcode
LIMIT 10
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", help="part of a business name, case-insensitive")
    args = ap.parse_args()
    q = args.query.upper()

    from database.lpg.graph_db import Neo4jDB

    db = Neo4jDB()
    try:
        with db._driver.session(database=db._database) as session:
            contratti = [dict(r) for r in session.run(CONTRATTI, q=q)]
            licenze = [dict(r) for r in session.run(LICENZE, q=q)]
    finally:
        db.close()

    print(f"\ncontracts — {len(contratti)} vendor node(s)")
    for r in contratti:
        print(f"  {r['name'][:44]:44} {r['id']:22} {r['contracts']:>3} contracts")
        print(f"    {(r['address'] or '-')[:60]}")

    print(f"\nlicences — {len(licenze)} record(s)")
    for r in licenze:
        trading = r["trading"] or "-"
        print(f"  legal:   {(r['legal'] or '-')[:52]}")
        if trading.upper() != (r["legal"] or "").upper():
            print(f"  trading: {trading[:52]}     <- different name, same business")
        print(f"    {(r['address'] or '-')[:44]}  {r['postcode'] or ''}\n")

    if not contratti and not licenze:
        print("Nothing matched. The search is a substring, not a fuzzy match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
