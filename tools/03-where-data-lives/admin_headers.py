#!/usr/bin/env -S python3 -u
"""Write the export again, with the headers `neo4j-admin` wants.

    python3 tools/03-where-data-lives/admin_headers.py

Reads `import/csv/`, writes `import/csv-neo4j-admin/` and its `plan.json`, which
`load_neo4j_offline.py` reads.

Only the header line changes; every row is copied byte for byte, so Neo4j loads
exactly the rows the other five engines load:

    keys       `id:ID(Label)` -- one id space per label, see header_for_node
    edges      `:START` / `:END` become `:START_ID(Label)` / `:END_ID(Label)`
    columns    every one typed, `name:string`; lists `name:string[]`, with the
               `|` delimiter given on the importer's command line
"""

import argparse
import json
import os
import shutil

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
IMPORT = os.path.join(ROOT, "modules", "03-where-data-lives", "import")
CSV = os.path.join(IMPORT, "csv")
OUT = os.path.join(IMPORT, "csv-neo4j-admin")

# The export's own type names to the importer's. `string` is the default and is
# written anyway, because a header that states every type is one a reader can
# check against `schema.json` without knowing which name is the default.
TYPES = {"STRING": "string", "INT64": "long", "DOUBLE": "double",
         "BOOLEAN": "boolean", "DATE": "date",
         "LIST<STRING>": "string[]", "LIST<INT64>": "long[]",
         "LIST<DOUBLE>": "double[]", "LIST<BOOLEAN>": "boolean[]"}


def header_for_node(cols, props, key, label):
    out = []
    for c in cols:
        if c == key:
            # `:ID(Label)` and not `:ID`, which is an ID SPACE and not decoration.
            # The export's keys are unique WITHIN a label and not across labels --
            # LicenseRecord 20867 and ContractRecord 20867 both exist -- and the
            # importer puts everything in one `global id space` unless told
            # otherwise, so a plain `:ID` fails with DuplicateInputIdException.
            # It names three colliding ids and stops.
            out.append(f"{c}:ID({label})")
        else:
            out.append(f"{c}:{TYPES[props[c]]}")
    return ",".join(out)


def header_for_edge(cols, props, src_label, dst_label):
    out = []
    for c in cols:
        if c == ":START":
            # The same id space the node file declared, or the importer cannot
            # tell which label a bare key belongs to.
            out.append(f":START_ID({src_label})")
        elif c == ":END":
            out.append(f":END_ID({dst_label})")
        else:
            out.append(f"{c}:{TYPES[props[c]]}")
    return ",".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    schema = json.load(open(os.path.join(CSV, "schema.json")))
    os.makedirs(a.out, exist_ok=True)

    plan = {"nodes": {}, "relationships": {}}
    for label, spec in schema["nodes"].items():
        src = os.path.join(CSV, f"node_{label}.csv")
        dst = os.path.join(a.out, f"node_{label}.csv")
        # newline="" on both sides: the exporter writes CRLF, and reading in
        # text mode without this translates it to LF, so the copy would differ
        # from the original by one byte a row. The importer accepts either, but a
        # second view of the data that is not byte-identical is a second dataset.
        with open(src, encoding="utf-8", newline="") as fh:
            cols = fh.readline().rstrip("\r\n").split(",")
            head = header_for_node(cols, spec["properties"], spec["key"], label)
            with open(dst, "w", encoding="utf-8", newline="") as out:
                out.write(head + "\r\n")
                shutil.copyfileobj(fh, out)
        plan["nodes"][label] = os.path.basename(dst)
        print(f"  node {label:<20} {len(cols):>3} columns")

    for name, spec in schema["edges"].items():
        src = os.path.join(CSV, f"edge_{name}.csv")
        dst = os.path.join(a.out, f"edge_{name}.csv")
        with open(src, encoding="utf-8", newline="") as fh:
            cols = fh.readline().rstrip("\r\n").split(",")
            head = header_for_edge(cols, spec["properties"],
                                   spec["from"], spec["to"])
            with open(dst, "w", encoding="utf-8", newline="") as out:
                out.write(head + "\r\n")
                shutil.copyfileobj(fh, out)
        plan["relationships"].setdefault(spec["type"], []).append(
            os.path.basename(dst))
        print(f"  edge {name:<52} {len(cols):>3} columns")

    with open(os.path.join(a.out, "plan.json"), "w") as fh:
        json.dump(plan, fh, indent=2, sort_keys=True)
    size = sum(os.path.getsize(os.path.join(a.out, f)) for f in os.listdir(a.out))
    print(f"\n{len(plan['nodes'])} node files, "
          f"{sum(len(v) for v in plan['relationships'].values())} edge files, "
          f"{size/1e6:.0f} MB -> {os.path.relpath(a.out, ROOT)}")


if __name__ == "__main__":
    main()
