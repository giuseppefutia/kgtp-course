#!/usr/bin/env -S python3 -u
"""Write the export again, in the shape `falkordb-bulk-insert` wants.

    python3 tools/03-where-data-lives/falkor_bulk_headers.py

Reads `import/csv/`, writes `import/csv-falkordb-bulk/` and its `plan.json`,
which `load_falkordb_offline.py` reads.

Two things change:

    headers    typed, `name:STRING`; keys `id:ID(Label)`; edges
               `:START_ID(Label)` / `:END_ID(Label)`
    lists      re-rendered as Python literals, `['a', 'b']`: the loader runs
               `ast.literal_eval` on every ARRAY cell, and the export joins
               elements with `|`

**Dates go in as STRING**, and this is the file that decides it. The loader's
types are BOOL, DOUBLE, STRING, LONG and ARRAY -- no date -- so on the loaded
graph `typeOf(n.startDate)` is `String`, and `n.startDate > date('2020-01-01')`
is null rather than false: the query answers 0 rows with no error, where Neo4j
and Kuzu answer 15,564.
"""

import ast
import csv
import json
import os
import sys

csv.field_size_limit(sys.maxsize)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
IMPORT = os.path.join(ROOT, "modules", "03-where-data-lives", "import")
CSV = os.path.join(IMPORT, "csv")
OUT = os.path.join(IMPORT, "csv-falkordb-bulk")

TYPES = {"STRING": "STRING", "INT64": "LONG", "DOUBLE": "DOUBLE",
         "BOOLEAN": "BOOL", "DATE": "STRING"}          # <- no DATE in this loader
LISTS = {"LIST<STRING>": str, "LIST<INT64>": int,
         "LIST<DOUBLE>": float, "LIST<BOOLEAN>": lambda x: x.lower() == "true"}


def kind(k):
    return "ARRAY" if k in LISTS else TYPES[k]


def cell(v, k):
    if v == "" or v is None:
        return ""
    if k in LISTS:
        f = LISTS[k]
        return repr([f(x) for x in v.split("|")])
    return v


def convert(src, dst, cols, props, head):
    with open(src, newline="", encoding="utf-8") as fh, \
         open(dst, "w", newline="", encoding="utf-8") as out:
        r = csv.reader(fh); next(r)
        w = csv.writer(out)
        w.writerow(head)
        n = 0
        for row in r:
            w.writerow([cell(v, props[c]) if c in props else v
                        for c, v in zip(cols, row)])
            n += 1
    return n


def main():
    schema = json.load(open(os.path.join(CSV, "schema.json")))
    os.makedirs(OUT, exist_ok=True)
    plan = {"nodes": {}, "relationships": {}}
    for label, spec in schema["nodes"].items():
        src = os.path.join(CSV, f"node_{label}.csv")
        with open(src, newline="", encoding="utf-8") as fh:
            cols = next(csv.reader(fh))
        # `ID(Label)` and not `ID`: the keys are unique within a label and not
        # across labels, and without a namespace the loader stops on the first
        # collision -- "Node identifier '4' was used multiple times". label.py
        # prefixes the namespace onto the key for its own dictionary, so the
        # property that lands in the graph is still the bare id.
        head = [f"{c}:ID({label})" if c == spec["key"]
                else f"{c}:{kind(spec['properties'][c])}" for c in cols]
        n = convert(src, os.path.join(OUT, f"node_{label}.csv"), cols,
                    spec["properties"], head)
        plan["nodes"][label] = f"node_{label}.csv"
        print(f"  node {label:<20}{n:>10,}")
    for name, spec in schema["edges"].items():
        src = os.path.join(CSV, f"edge_{name}.csv")
        with open(src, newline="", encoding="utf-8") as fh:
            cols = next(csv.reader(fh))
        head = [f":START_ID({spec['from']})" if c == ":START"
                else f":END_ID({spec['to']})" if c == ":END"
                else f"{c}:{kind(spec['properties'][c])}" for c in cols]
        n = convert(src, os.path.join(OUT, f"edge_{name}.csv"), cols,
                    spec["properties"], head)
        plan["relationships"].setdefault(spec["type"], []).append(f"edge_{name}.csv")
        print(f"  edge {name:<52}{n:>10,}")
    json.dump(plan, open(os.path.join(OUT, "plan.json"), "w"), indent=2, sort_keys=True)
    size = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT))
    print(f"\n{size/1e6:.0f} MB -> {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
