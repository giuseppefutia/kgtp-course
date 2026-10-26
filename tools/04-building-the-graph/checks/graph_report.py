"""What is in the graph right now, by label and relationship type.

Read-only. Exists so that "did the build work" is a command rather than a
recollection, and so that a number quoted in the documents can be checked
against the graph that is actually loaded.

    python3 -m checks.graph_report
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")


def main() -> int:
    from database.lpg.graph_db import Neo4jDB

    db = Neo4jDB()
    try:
        with db._driver.session(database=db._database) as session:
            print("nodes")
            for row in session.run(
                "MATCH (n) UNWIND labels(n) AS l "
                "RETURN l AS label, count(*) AS n ORDER BY n DESC"
            ):
                print(f"  {row['label']:<22} {row['n']:>10,}")

            print("\nrelationships")
            for row in session.run(
                "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS n ORDER BY n DESC"
            ):
                print(f"  {row['type']:<22} {row['n']:>10,}")

            total = session.run("MATCH (n) RETURN count(n) AS n").single()["n"]
            if total == 0:
                print("\nThe graph is empty.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
