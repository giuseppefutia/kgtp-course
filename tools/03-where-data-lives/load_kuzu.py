#!/usr/bin/env -S python3 -u
"""Load the payload into Kuzu, in this process, through Arrow.

    python3 tools/03-where-data-lives/load_kuzu.py

Reads `import/csv/`, rebuilds `import/kuzu/kgtp.db` from nothing. Embedded: no
server and no container.

**Arrow, not `COPY FROM` a CSV.** Kuzu reads a CSV list column only as
`[a,b,c]`, with no way to change the delimiter, and the export joins elements
with `|`. Rewriting the column does not work either: the elements are company
names, they contain commas, and quoting them leaves the quotes in the values.
Arrow carries typed lists, and the problem does not arise.

**One table per label pair.** A relationship type spanning several pairs could
be one REL TABLE GROUP, keeping the Cypher identical to Neo4j's, but the
algorithm library cannot project a group. So it is split, `REL__Src__Dst`, and
the price moves into the query language: 2 of the 18 types span more than one
pair, and 3 of the lesson's 10 questions need a different text on this engine
(`cypher_for` in queries.py).
"""

import argparse
import json
import os
import shutil
import time

import pandas as pd
import pyarrow as pa

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
IMPORT = os.path.join(ROOT, "modules", "03-where-data-lives", "import")
CSV = os.path.join(IMPORT, "csv")

ARROW = {"STRING": pa.string(), "INT64": pa.int64(), "DOUBLE": pa.float64(),
         "BOOLEAN": pa.bool_(), "DATE": pa.date32()}
KUZU = {"STRING": "STRING", "INT64": "INT64", "DOUBLE": "DOUBLE",
        "BOOLEAN": "BOOLEAN", "DATE": "DATE"}


def kuzu_type(kind):
    if kind.startswith("LIST<"):
        return KUZU[kind[5:-1]] + "[]"
    return KUZU[kind]


def _missing(v):
    """An absent cell, in the three shapes pandas hands one over.

    `None`, the empty string, and NaN. The third is the one that bites: on
    pandas 3.0 `Series.where(cond, None)` over a string column substitutes NaN
    rather than None, so a `None is v` test passes it through to `int(float(v))`
    and the load dies on `cannot convert float NaN to integer` on
    Organization.louvainCoarsest. `v != v` is the NaN test that always holds.
    """
    return v is None or v != v or v == ""


def arrow_col(series, kind):
    """One CSV column as a typed Arrow array. An empty cell is absent, not empty."""
    if kind.startswith("LIST<"):
        inner = kind[5:-1]
        cast = {"INT64": lambda x: int(float(x)), "DOUBLE": float,
                "BOOLEAN": lambda v: v.lower() == "true"}.get(inner, str)
        vals = [None if _missing(v) else [cast(x) for x in str(v).split("|")]
                for v in series]
        return pa.array(vals, type=pa.list_(ARROW[inner]))
    if kind == "INT64":
        return pa.array([None if _missing(v) else int(float(v)) for v in series],
                        type=pa.int64())
    if kind == "DOUBLE":
        return pa.array([None if _missing(v) else float(v) for v in series],
                        type=pa.float64())
    if kind == "BOOLEAN":
        return pa.array([None if _missing(v) else str(v).lower() == "true" for v in series],
                        type=pa.bool_())
    if kind == "DATE":
        return pa.array(pd.to_datetime(series, errors="coerce").dt.date, type=pa.date32())
    return pa.array([None if _missing(v) else str(v) for v in series], type=pa.string())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=os.path.join(IMPORT, "kuzu", "kgtp.db"))
    a = ap.parse_args()
    schema = json.load(open(os.path.join(CSV, "schema.json")))

    # Kuzu creates the database as a single FILE, not a directory, and it has
    # broken a cell before. So remove both shapes, and do not
    # trust shutil.rmtree to have done anything.
    os.makedirs(os.path.dirname(a.path), exist_ok=True)
    for p in (a.path, a.path + ".wal", a.path + ".tmp"):
        if os.path.isdir(p):
            shutil.rmtree(p)
        elif os.path.exists(p):
            os.remove(p)

    import kuzu
    db = kuzu.Database(a.path)
    conn = kuzu.Connection(db)
    t = {"ddl_s": 0.0, "nodes_s": 0.0, "edges_s": 0.0}
    print(f"kuzu {kuzu.__version__} -> {a.path}")

    print("\n-- DDL: every table declared before any row (Neo4j needs none of this)")
    t0 = time.time()
    for label, spec in schema["nodes"].items():
        cols = ", ".join(f"{p} {kuzu_type(k)}" for p, k in sorted(spec["properties"].items()))
        conn.execute(f"CREATE NODE TABLE {label}({cols}, PRIMARY KEY({spec['key']}))")
    # One table per (type, source, target). A type spanning several pairs becomes
    # several tables -- see the module docstring for why, and for what it costs.
    pairs, props = {}, {}
    for name, spec in schema["edges"].items():
        pairs.setdefault(spec["type"], []).append((spec["from"], spec["to"]))
        props.setdefault(spec["type"], {}).update(spec["properties"])
    for name, spec in schema["edges"].items():
        rel, src, dst = spec["type"], spec["from"], spec["to"]
        table = rel if len(pairs[rel]) == 1 else f"{rel}__{src}__{dst}"
        extra = "".join(f", {p} {kuzu_type(k)}" for p, k in sorted(props[rel].items()))
        conn.execute(f"CREATE REL TABLE {table}(FROM {src} TO {dst}{extra})")
    t["ddl_s"] = round(time.time() - t0, 1)
    print(f"   {len(schema['nodes'])} node tables, {len(pairs)} rel tables in {t['ddl_s']}s")

    print("\n-- nodes")
    t0 = time.time()
    for label, spec in schema["nodes"].items():
        f = os.path.join(CSV, f"node_{label}.csv")
        df = pd.read_csv(f, dtype=str, keep_default_na=False, na_values=[""], low_memory=False)
        tbl = pa.table({p: arrow_col(df[p], spec["properties"][p])
                        for p in sorted(spec["properties"])})
        s0 = time.time()
        conn.execute(f"COPY {label} FROM tbl")
        print(f"   {label:<20} {tbl.num_rows:>10,}  {time.time()-s0:>6.1f}s")
        del df, tbl
    t["nodes_s"] = round(time.time() - t0, 1)

    print("\n-- edges")
    t0 = time.time()
    for name, spec in schema["edges"].items():
        src, dst, rel = spec["from"], spec["to"], spec["type"]
        f = os.path.join(CSV, f"edge_{name}.csv")
        df = pd.read_csv(f, dtype=str, keep_default_na=False, na_values=[""], low_memory=False)
        cols = {"f": arrow_col(df[":START"], schema["nodes"][src]["properties"][schema["nodes"][src]["key"]]),
                "t": arrow_col(df[":END"], schema["nodes"][dst]["properties"][schema["nodes"][dst]["key"]])}
        # The columns must be the TABLE's, not this file's. A REL TABLE GROUP is
        # declared with the union of the properties of every label pair it
        # carries, while each pair's CSV has only its own: IS_SIMILAR_TO between
        # Departments has no `methods` column, and Kuzu answers "tbl has 4
        # columns but 5 columns were expected". So the missing ones
        # are supplied as nulls, in the table's order.
        for p, k in sorted(props[rel].items()):
            cols[p] = (arrow_col(df[p], k) if p in df.columns
                       else pa.nulls(len(df), type=(pa.list_(ARROW[k[5:-1]])
                                                    if k.startswith("LIST<") else ARROW[k])))
        tbl = pa.table(cols)
        table = rel if len(pairs[rel]) == 1 else f"{rel}__{src}__{dst}"
        s0 = time.time()
        # No (from=, to=) clause any more: each table has exactly one pair, so
        # there is nothing left to disambiguate.
        conn.execute(f"COPY {table} FROM tbl")
        print(f"   {table:<40}{tbl.num_rows:>10,}  {time.time()-s0:>6.1f}s")
        del df, tbl
    t["edges_s"] = round(time.time() - t0, 1)

    n = sum(conn.execute(f"MATCH (n:{l}) RETURN count(n)").get_next()[0] for l in schema["nodes"])
    tables = [rel if len(pairs[spec["type"]]) == 1
              else f'{spec["type"]}__{spec["from"]}__{spec["to"]}'
              for rel, spec in ((s_["type"], s_) for s_ in schema["edges"].values())]
    e = sum(conn.execute(f"MATCH ()-[r:{t}]->() RETURN count(r)").get_next()[0]
            for t in sorted(set(tables)))
    t["nodes"], t["edges"] = n, e
    t["load_s"] = round(t["ddl_s"] + t["nodes_s"] + t["edges_s"], 1)
    size = sum(os.path.getsize(os.path.join(dp, f))
               for dp, _, fs in os.walk(os.path.dirname(a.path)) for f in fs)
    t["store_mb"] = round(size / 1e6)
    print(f"\nkuzu: {n:,} nodes  {e:,} edges | {t['load_s']}s | {t['store_mb']} MB")

    out = os.path.join(IMPORT, "load-times.json")
    allt = json.load(open(out)) if os.path.exists(out) else {}
    allt["kuzu"] = t
    json.dump(allt, open(out, "w"), indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
