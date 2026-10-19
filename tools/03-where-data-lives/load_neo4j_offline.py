#!/usr/bin/env -S python3 -u
"""Load the payload into Neo4j with `neo4j-admin database import full`.

    python3 tools/03-where-data-lives/load_neo4j_offline.py

Reads `import/csv-neo4j-admin/` (run `admin_headers.py` first). The importer
writes the store itself and wants the server down, so the container is stopped
and started around it, and `neo4j` -- Community Edition's one user database --
is OVERWRITTEN. The importer creates no index; the constraints and full-text
indexes are created after it and timed into the total.

Three things the importer requires:

  * `--multiline-fields`, which defaults to false: two node files have a field
    containing a newline, legal RFC 4180. The v2 form takes the list of files
    that need it, found by scanning rather than listed;
  * one group per FILE, not per type: a group reads ONE header, from its first
    file, and the two `IS_SIMILAR_TO` files have different columns;
  * `:ID(Label)`, one id space per label, because the keys repeat across labels
    -- see `admin_headers.header_for_node`.
"""

import argparse
import json
import os
import subprocess
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
COMPOSE = os.path.join(ROOT, "modules", "03-where-data-lives", "docker-compose.yml")
IMPORT = os.path.join(ROOT, "modules", "03-where-data-lives", "import")
ADMIN = os.path.join(IMPORT, "csv-neo4j-admin")
IMAGE = "neo4j:2025.11.2-community"
# One copy of where the container is and how to log into it, shared with
# the notebooks: a password in two files is a password that will disagree.
from engines import NEO4J_URI as URI, NEO4J_AUTH
FULLTEXT = [("org_name_ft", "Organization", "name"),
            ("contract_name_ft", "Contract", "name")]


def compose(*args):
    subprocess.run(["docker", "compose", "-f", COMPOSE, "--profile", "neo4j", *args],
                   check=False, capture_output=True)


def multiline_files():
    """The files with a field containing a newline, found rather than listed."""
    import csv
    import sys
    csv.field_size_limit(sys.maxsize)
    out = []
    for f in sorted(os.listdir(ADMIN)):
        if not f.endswith(".csv"):
            continue
        with open(os.path.join(ADMIN, f), newline="", encoding="utf-8") as fh:
            for row in csv.reader(fh):
                if any("\n" in (c or "") or "\r" in (c or "") for c in row):
                    out.append(f"/import/csv-neo4j-admin/{f}")
                    break
    return out


def main():
    ap = argparse.ArgumentParser()
    a = ap.parse_args()
    plan = json.load(open(os.path.join(ADMIN, "plan.json")))
    args = [f"--nodes={lab}=/import/csv-neo4j-admin/{f}"
            for lab, f in sorted(plan["nodes"].items())]
    # One group per FILE and not per type -- see the module docstring.
    args += [f"--relationships={t}=/import/csv-neo4j-admin/{f}"
             for t, fs in sorted(plan["relationships"].items()) for f in fs]
    ml = multiline_files()
    print(f"{len(plan['nodes'])} node files, "
          f"{sum(len(v) for v in plan['relationships'].values())} edge files, "
          f"{len(ml)} of them with multi-line fields")

    print("\n-- stopping the server; the importer writes the store directly")
    compose("stop")

    cmd = ("neo4j-admin database import full neo4j --overwrite-destination "
           "--id-type=string --array-delimiter='|' --multiline-fields-format=v2 "
           f"--multiline-fields='{','.join(ml)}' " + " ".join(args))
    print("-- importing")
    t0 = time.time()
    r = subprocess.run(
        ["docker", "run", "--rm", "-v", "module-03_neo4j-data:/data",
         "-v", f"{IMPORT}:/import:ro", IMAGE, "sh", "-c", cmd],
        capture_output=True, text=True)
    import_s = round(time.time() - t0, 1)
    tail = [l for l in r.stdout.splitlines() if "Imported:" in l or "nodes" in l
            or "relationships" in l or "properties" in l or "IMPORT" in l]
    for l in tail[-6:]:
        print("   " + l.strip())
    if r.returncode != 0:
        print(r.stdout[-2000:])
        raise SystemExit(f"import failed after {import_s}s")

    print("\n-- starting the server")
    compose("up", "-d")
    from neo4j import GraphDatabase
    from neo4j.exceptions import ServiceUnavailable
    d = GraphDatabase.driver(URI, auth=NEO4J_AUTH)
    for _ in range(120):
        try:
            with d.session() as s:
                s.run("RETURN 1").consume()
            break
        except Exception:
            time.sleep(5)

    # The importer creates no indexes, and every key lookup in the lesson needs
    # them. They are timed into the total: a store without its indexes is not
    # loaded, it is half loaded and fast to report.
    print("-- constraints and full-text indexes, which the importer does not create")
    schema = json.load(open(os.path.join(IMPORT, "csv", "schema.json")))
    t0 = time.time()
    with d.session() as s:
        for lab, spec in schema["nodes"].items():
            s.run(f"CREATE CONSTRAINT {lab.lower()}_key IF NOT EXISTS "
                  f"FOR (n:{lab}) REQUIRE n.{spec['key']} IS UNIQUE").consume()
        for name, lab, prop in FULLTEXT:
            s.run(f"CREATE FULLTEXT INDEX {name} IF NOT EXISTS "
                  f"FOR (n:{lab}) ON EACH [n.{prop}]").consume()
        create_s = round(time.time() - t0, 1)
        t0 = time.time()
        s.run("CALL db.awaitIndexes(1200)").consume()
        await_s = round(time.time() - t0, 1)
        n = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        e = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
    d.close()

    total = round(import_s + create_s + await_s, 1)
    print(f"\n   import            {import_s:>7.1f} s")
    print(f"   indexes, CREATE   {create_s:>7.1f} s")
    print(f"   indexes, await    {await_s:>7.1f} s")
    print(f"   TOTAL             {total:>7.1f} s")
    print(f"\nneo4j: {n:,} nodes  {e:,} edges"
          f"   {'exact' if (n, e) == (2_137_944, 4_073_458) else 'DIFFERS'}")

    out = os.path.join(IMPORT, "load-times.json")
    allt = json.load(open(out)) if os.path.exists(out) else {}
    allt["neo4j-offline"] = {"import_s": import_s, "index_create_s": create_s,
                             "index_await_s": await_s, "total_s": total,
                             "nodes": n, "edges": e,
                             "tool": "neo4j-admin database import full"}
    json.dump(allt, open(out, "w"), indent=2, sort_keys=True)
    print(f"written to {os.path.basename(out)}")


if __name__ == "__main__":
    main()
