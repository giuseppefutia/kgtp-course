#!/usr/bin/env -S python3 -u
"""Load the payload into FalkorDB with `falkordb-bulk-insert`.

    python3 tools/03-where-data-lives/load_falkordb_offline.py --dry-run   # print the command
    python3 tools/03-where-data-lives/load_falkordb_offline.py             # WIPES graph kgtp

Reads `import/csv-falkordb-bulk/` (run `falkor_bulk_headers.py` first). Unlike
the other offline loaders this one wants the server UP: it sends a bulk command
over the Redis protocol. The image ships no loader, so it is a package pinned in
pyproject.toml.

The loader creates no index. The key and full-text indexes are created after it,
waited for, and timed into the total: FalkorDB builds them asynchronously, so a
`CREATE INDEX` that has returned has not finished.

Dates arrive as strings; `falkor_bulk_headers.py` says why and what it breaks.
"""

import argparse
import json
import os
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
IMPORT = os.path.join(ROOT, "modules", "03-where-data-lives", "import")
BULK = os.path.join(IMPORT, "csv-falkordb-bulk")
CSV = os.path.join(IMPORT, "csv")
HOST = os.environ.get("KGTP_M3_FALKOR_HOST", "localhost")
PORT = int(os.environ.get("KGTP_M3_FALKOR_PORT", "6379"))
EXPECTED = (2_137_944, 4_073_458)
FULLTEXT = [("Organization", "name"), ("Contract", "name")]


def command(graph):
    """The invocation, built from the plan the header generator wrote.

    One `-N label file` per node file and one `-R type file` per edge file --
    per FILE and not per type, because two files carry BELONGS_TO_ORG_GROUP and
    two carry IS_SIMILAR_TO with different columns.
    """
    plan = json.load(open(os.path.join(BULK, "plan.json")))
    # The loader is a console script that pip puts next to the interpreter, so
    # it is looked for there: a shell whose PATH lacks the virtual environment
    # would otherwise run some other install, or none.
    exe = os.path.join(os.path.dirname(sys.executable), "falkordb-bulk-insert")
    cmd = [exe, graph,
           "--server-url", f"redis://{HOST}:{PORT}",
           "--enforce-schema",            # the types live in the header rows
           "--id-type", "STRING",         # our keys are strings, not integers
           # The loader's default escape character is a backslash, and the
           # export is plain RFC 4180, where a backslash is only a backslash.
           # Left on, it eats the one in front of a quote and the cell no longer
           # parses: a licence description carrying both quote characters
           # stopped the load two seconds in.
           "--escapechar", "none"]
    for label, f in sorted(plan["nodes"].items()):
        cmd += ["-N", label, os.path.join(BULK, f)]
    for rel, files in sorted(plan["relationships"].items()):
        for f in files:
            cmd += ["-R", rel, os.path.join(BULK, f)]
    return cmd


def indexes(graph):
    """The keys indexed and WAITED FOR, then the two full-text indexes.

    FalkorDB returns from CREATE INDEX before the index exists, and a query
    run against an index still UNDER CONSTRUCTION is a scan. So the wait is
    polled, and it is part of the number.
    """
    from falkordb import FalkorDB
    g = FalkorDB(host=HOST, port=PORT).select_graph(graph)
    schema = json.load(open(os.path.join(CSV, "schema.json")))

    t0 = time.time()
    for label, spec in schema["nodes"].items():
        try:
            g.query(f"CREATE INDEX FOR (n:{label}) ON (n.{spec['key']})")
        except Exception as e:
            print(f"   {label}: {str(e)[:80]}")
    while True:
        states = [row[7] for row in g.query("CALL db.indexes()").result_set]
        pending = [x for x in states if "UNDER CONSTRUCTION" in str(x)]
        if not pending:
            break
        print(f"   {len(pending)}/{len(states)} still building: {pending[0]}")
        time.sleep(5)
    keys_s = round(time.time() - t0, 1)
    print(f"   {len(schema['nodes'])} key indexes online in {keys_s}s")

    t0 = time.time()
    for label, prop in FULLTEXT:
        try:
            g.query(f"CREATE FULLTEXT INDEX FOR (n:{label}) ON (n.{prop})")
        except Exception as e:
            print(f"   {label}.{prop}: {str(e)[:80]}")
    ft_s = round(time.time() - t0, 1)

    n = g.query("MATCH (n) RETURN count(n)").result_set[0][0]
    e = g.query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0]
    return keys_s, ft_s, n, e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", default="kgtp")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the command and the file count, change nothing")
    a = ap.parse_args()

    cmd = command(a.graph)
    nodes = sum(1 for i, x in enumerate(cmd) if x == "-N")
    edges = sum(1 for i, x in enumerate(cmd) if x == "-R")
    print(f"{nodes} node files, {edges} edge files, from "
          f"{os.path.relpath(BULK, ROOT)}")
    if a.dry_run:
        # Paths shown relative to the repo root: the command sends them absolute.
        rel = lambda x: os.path.relpath(x, ROOT) if x.startswith(ROOT) else x
        print("\n" + " ".join(cmd[:7]) + " \\")
        print(" \\\n".join(f"   {f} {lab} {rel(p)}"
                           for f, lab, p in zip(cmd[7::3], cmd[8::3], cmd[9::3])))
        return

    # The bulk loader will not write into a graph that already has the keys, and
    # a half-loaded graph is worse than none: the deletion is explicit here
    # rather than hidden, exactly as the wipe is in load_all.sh.
    from falkordb import FalkorDB
    db = FalkorDB(host=HOST, port=PORT)
    try:
        db.select_graph(a.graph).delete()
        print(f"-- graph {a.graph} deleted")
    except Exception as e:
        print(f"-- nothing to delete ({str(e)[:60]})")

    print("-- bulk insert, server UP; this path speaks the Redis protocol")
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    insert_s = round(time.time() - t0, 1)
    for line in r.stdout.splitlines()[-6:]:
        print("   " + line.strip())
    if r.returncode != 0:
        print(r.stderr[-2000:])
        raise SystemExit(f"bulk insert failed after {insert_s}s")

    print("\n-- indexes, which the loader does not create")
    keys_s, ft_s, n, e = indexes(a.graph)

    total = round(insert_s + keys_s + ft_s, 1)
    print(f"\n   bulk insert       {insert_s:>7.1f} s")
    print(f"   key indexes       {keys_s:>7.1f} s")
    print(f"   full-text         {ft_s:>7.1f} s")
    print(f"   TOTAL             {total:>7.1f} s")
    print(f"\nfalkordb: {n:,} nodes  {e:,} edges"
          f"   {'exact' if (n, e) == EXPECTED else 'DIFFERS'}")

    out = os.path.join(IMPORT, "load-times.json")
    allt = json.load(open(out)) if os.path.exists(out) else {}
    allt["falkordb-offline"] = {
        "insert_s": insert_s, "index_keys_s": keys_s, "fulltext_s": ft_s,
        "total_s": total, "nodes": n, "edges": e,
        "measured": time.strftime("%Y-%m-%d"),
        "tool": "falkordb-bulk-insert, external package, server up",
        "defect": "no DATE type: dates arrive as strings, and a date "
                  "comparison answers 0",
    }
    json.dump(allt, open(out, "w"), indent=2, sort_keys=True)
    print(f"written to {os.path.basename(out)}")


if __name__ == "__main__":
    main()
