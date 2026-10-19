#!/usr/bin/env -S python3 -u
"""Load the payload into GraphDB or Fuseki, each with its own offline loader.

    python3 tools/03-where-data-lives/load_rdf.py graphdb
    python3 tools/03-where-data-lives/load_rdf.py fuseki                 # both WIPE the store

Reads `import/rdf/kgtp.nq.gz`. `importrdf preload` and `tdb2.xloader` want the
store to themselves, so the server is taken down, the loader runs in a one-off
container on the same volume, and the server comes back up. Both are an order of
magnitude faster than sending 36.8 million triples over HTTP.

**A named graph, not the default one.** All three triple stores load into
`<http://kgtp.org/graph/kgtp>`, so one SPARQL text runs on all three. Fuseki's
`ds` dataset answers from the union of the named graphs and leaves the stored
default graph out of it: triples loaded there answer `?s ?p ?o` with zero rows
and no error.
"""

import argparse
import json
import os
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
COMPOSE = os.path.join(ROOT, "modules", "03-where-data-lives", "docker-compose.yml")
IMPORT = os.path.join(ROOT, "modules", "03-where-data-lives", "import")
# The graph name comes from `engines`, so that this loader and the notebook
# that queries it afterwards cannot disagree about where the data went.
from engines import GRAPH

# Oxigraph is not here: it is the embedded engine on this side and has its own
# loader, `load_oxigraph.py`, because there is no container to run a bulk loader
# inside. The two below are servers, and both have to be DOWN while they load.
ENGINES = {
    "graphdb": {
        "image": "ontotext/graphdb:10.8.14",
        "volume": "module-03_graphdb-data",
        "mount": "/opt/graphdb/home",
        "endpoint": "http://localhost:7200/repositories/kgtp",
    },
    "fuseki": {
        "image": "secoresearch/fuseki:6.2.0",
        "volume": "module-03_fuseki-data",
        "mount": "/fuseki-base/databases",
        "endpoint": "http://localhost:3030/ds/sparql",
    },
}


def run(cmd, **kw):
    print("  $", " ".join(cmd[:9]), "..." if len(cmd) > 9 else "", flush=True)
    return subprocess.run(cmd, **kw)


def compose(*args, profile=None):
    c = ["docker", "compose", "-f", COMPOSE]
    if profile:
        c += ["--profile", profile]
    return run(c + list(args), check=False)


def loader_cmd(engine, nq_in_container, e):
    """The bulk loader of each engine, as it is invoked in a one-off container."""
    vol, mount = e["volume"], e["mount"]
    base = ["docker", "run", "--rm",
            "-v", f"{vol}:{mount}",
            "-v", f"{IMPORT}:/import:ro"]
    if engine == "graphdb":
        # preload, not load: a single non-fragmented image, and it does not run
        # inference -- which is what the comparison wants. The lesson prices
        # inference separately, on the contracts' dates alone.
        # `-Dgraphdb.home` is not optional and nothing sets it for us. The
        # importrdf script passes $GDB_JAVA_OPTS and -Dgraphdb.dist and no home,
        # so without this preload writes the repository into the container's own
        # filesystem instead of the mounted volume: it reports success, finishes
        # in under a second, and the server then starts with no repository at all
        # The log says "total tuples 0" and the server then answers
        # "Unknown repository: kgtp".
        return base + ["-e", "GDB_JAVA_OPTS=-Dgraphdb.home=/opt/graphdb/home -Xmx4g",
                       "--entrypoint", "/opt/graphdb/dist/bin/importrdf", e["image"],
                       "preload", "-f", "-c", "/import/graphdb-repo.ttl", nq_in_container]
    if engine == "fuseki":
        # xloader and not tdbloader: it sorts on disk instead of in the heap, so
        # 36.8 million triples do not need a JVM sized for them. It wants its
        # temporary space told explicitly, because the default lands inside the
        # container.
        return base + ["--entrypoint", "/jena/bin/tdb2.xloader", e["image"],
                       "--loc", f"{mount}/tdb", "--tmpdir", f"{mount}/tmp",
                       nq_in_container]
    raise SystemExit(engine)


def verify(engine, e):
    """Count what actually arrived, from outside the engine."""
    import urllib.parse, urllib.request
    q = f"SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH <{GRAPH}> {{ ?s ?p ?o }} }}"
    url = e["endpoint"] + "?" + urllib.parse.urlencode({"query": q})
    req = urllib.request.Request(url, headers={"Accept": "application/sparql-results+json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.load(r)
    return int(d["results"]["bindings"][0]["n"]["value"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("engine", choices=list(ENGINES))
    ap.add_argument("--file", default="rdf/kgtp.nq.gz",
                    help="N-Quads, relative to the import directory")
    ap.add_argument("--keep", action="store_true",
                    help="load on top of what is there instead of wiping first")
    a = ap.parse_args()
    e = ENGINES[a.engine]
    nq = "/import/" + a.file
    host_file = os.path.join(IMPORT, a.file)
    if not os.path.exists(host_file):
        raise SystemExit(f"missing {host_file}")

    t = {}
    print(f"== {a.engine}: {a.file} ({os.path.getsize(host_file)/1e6:.0f} MB) -> <{GRAPH}>")

    print("-- stopping the engine; the bulk loader wants the store to itself")
    compose("down", "-v" if not a.keep else "--remove-orphans", profile=a.engine)

    print("-- bulk load")
    t0 = time.time()
    r = run(loader_cmd(a.engine, nq, e), check=False)
    t["load_s"] = round(time.time() - t0, 1)
    if r.returncode != 0:
        raise SystemExit(f"{a.engine}: loader exited {r.returncode} after {t['load_s']}s")


    print("-- starting the engine")
    t0 = time.time()
    compose("up", "-d", profile=a.engine)
    for _ in range(120):
        try:
            n = verify(a.engine, e)
            break
        except Exception:
            time.sleep(5)
    else:
        raise SystemExit(f"{a.engine}: up, but the endpoint never answered")
    t["startup_s"] = round(time.time() - t0, 1)
    t["triples"] = n

    print(f"\n{a.engine}: {n:,} triples | load {t['load_s']}s | startup {t['startup_s']}s")
    out = os.path.join(IMPORT, "load-times.json")
    all_t = json.load(open(out)) if os.path.exists(out) else {}
    all_t[a.engine] = t
    json.dump(all_t, open(out, "w"), indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
