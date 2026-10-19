#!/usr/bin/env -S python3 -u
"""Load the payload into Oxigraph, in this process, with `bulk_load`.

    python3 tools/03-where-data-lives/load_oxigraph.py

Reads `import/rdf/kgtp.nq.gz`, rebuilds `import/oxigraph/kgtp.db`. Embedded, the
RDF mirror of Kuzu: no server to stop, so none of `load_rdf.py`'s
stop-load-start, and the same input and named graph as GraphDB and Fuseki, so
the three triple stores hold the same quads.

`bulk_load` writes sorted files straight into the store instead of inserting
quad by quad. The compaction that follows is timed on its own line, and the
lesson's LOAD column adds the two: skipped, it would show up later as query
latency.

`to_graph` is deliberately NOT passed. It applies to files of triples; N-Quads
already name their graph, and passing it would be a second, silent opinion about
where the data goes.
"""

import argparse
import gzip
import json
import os
import shutil
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
IMPORT = os.path.join(ROOT, "modules", "03-where-data-lives", "import")
# The graph name comes from `engines`, so that this loader and the notebook
# that queries it afterwards cannot disagree about where the data went.
from engines import GRAPH


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=os.path.join(IMPORT, "oxigraph", "kgtp.db"))
    ap.add_argument("--file", default=os.path.join(IMPORT, "rdf", "kgtp.nq.gz"))
    ap.add_argument("--keep", action="store_true",
                    help="load on top of whatever is there instead of wiping")
    a = ap.parse_args()

    import pyoxigraph as ox
    if not a.keep and os.path.exists(a.path):
        shutil.rmtree(a.path)
    os.makedirs(os.path.dirname(a.path), exist_ok=True)

    src_mb = os.path.getsize(a.file) / 1e6
    print(f"pyoxigraph {ox.__version__ if hasattr(ox, '__version__') else ''} "
          f"-> {a.path}")
    print(f"   {os.path.basename(a.file)}  {src_mb:.0f} MB  -> <{GRAPH}>")

    store = ox.Store(a.path)
    t0 = time.time()
    with gzip.open(a.file, "rb") as fh:
        store.bulk_load(input=fh, format=ox.RdfFormat.N_QUADS)
    load_s = round(time.time() - t0, 1)

    # `optimize` is the LSM-tree compaction the served image also runs on demand.
    # It is timed separately because it is not part of getting the data in, and
    # skipping it would leave the first queries reading many more sorted runs
    # than the steady state does -- which would be measured as query latency.
    t0 = time.time()
    store.optimize()
    opt_s = round(time.time() - t0, 1)

    n = next(iter(store.query(
        f"SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH <{GRAPH}> {{ ?s ?p ?o }} }}"
    )))[0].value
    # RocksDB deletes obsolete SST files asynchronously after a compaction, so
    # a file named by os.walk can be gone by the time getsize reaches it.
    # Missing files are skipped rather than crashing a load that
    # already succeeded.
    size = 0
    for dp, _, fs in os.walk(a.path):
        for f in fs:
            try:
                size += os.path.getsize(os.path.join(dp, f))
            except FileNotFoundError:
                pass
    t = {"load_s": load_s, "optimize_s": opt_s,
         "total_s": round(load_s + opt_s, 1),
         "triples": int(n), "store_mb": round(size / 1e6)}
    print(f"\noxigraph: {int(n):,} triples | {t['total_s']}s "
          f"({load_s}s load + {opt_s}s optimize) | {t['store_mb']} MB")

    out = os.path.join(IMPORT, "load-times.json")
    allt = json.load(open(out)) if os.path.exists(out) else {}
    allt["oxigraph"] = t
    json.dump(allt, open(out, "w"), indent=2, sort_keys=True)
    print(f"written to {os.path.basename(out)}")


if __name__ == "__main__":
    main()
