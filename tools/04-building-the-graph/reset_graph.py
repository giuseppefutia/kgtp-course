"""Empty the graph, so a build starts from nothing.

The pipeline is not idempotent -- record identity is positional, see A10 -- so
loading twice into the same database does not produce the same graph as loading
once. Rebuilding from empty is what makes that irrelevant: if a partial load
never happens, idempotency stops being a requirement.

    python reset_graph.py --yes

Deletes in batches because a single transaction over 2.6M nodes exceeds
dbms.memory.transaction.total.max. Drops constraints and indexes too: leaving
them behind makes the next build look like it created them.
"""

from __future__ import annotations

import argparse
import sys

sys.path.insert(0, ".")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yes", action="store_true",
                    help="required: this deletes every node and relationship")
    ap.add_argument("--batch", type=int, default=10000)
    args = ap.parse_args()

    from database.lpg.graph_db import Neo4jDB

    db = Neo4jDB()
    try:
        with db._driver.session(database=db._database) as session:
            before = session.run("MATCH (n) RETURN count(n) AS n").single()["n"]
            if not args.yes:
                print(f"{before:,} nodes would be deleted. Re-run with --yes.")
                return 1

            print(f"deleting {before:,} nodes...")
            session.run(
                "MATCH (n) CALL (n) { DETACH DELETE n } "
                f"IN TRANSACTIONS OF {args.batch} ROWS"
            )

            # Constraints outlive the data they were created for, and a build
            # that finds them already there reports creating nothing.
            #
            # Constraints first: dropping one drops the index backing it, so
            # the index pass afterwards no longer sees it.
            for kind, plural in (("CONSTRAINT", "CONSTRAINTS"),
                                 ("INDEX", "INDEXES")):
                rows = list(session.run(f"SHOW {plural} YIELD name, type"))
                # The two token lookup indexes are created with the database,
                # not by a build, and Neo4j does not put them back once they
                # are gone -- every later MATCH by label falls back to a scan,
                # on a graph that reloads fine and reads slowly for no visible
                # reason. They are the one thing a reset must leave alone.
                names = [r["name"] for r in rows if r["type"] != "LOOKUP"]
                for name in names:
                    try:
                        session.run(f"DROP {kind} `{name}` IF EXISTS")
                    except Exception as e:
                        print(f"  could not drop {kind.lower()} {name}: {str(e)[:120]}")
                print(f"dropped {len(names)} {kind.lower()}(s)")

            after = session.run("MATCH (n) RETURN count(n) AS n").single()["n"]
            print(f"nodes remaining: {after}")
            return 0 if after == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
