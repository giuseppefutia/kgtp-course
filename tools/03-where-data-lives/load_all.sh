#!/usr/bin/env bash
# Load all six engines from one export, ONE AT A TIME.
#
# Serial is not caution, it is a requirement. Loading in parallel saves a few
# minutes of wall clock and costs correctness: GraphDB's preload leaves behind a
# `preload.recover` file that blocks every query while the container's
# healthcheck stays green -- a green light in front of a store that answers
# nothing.
#
# It also means each load_s in load-times.json is the engine's own number rather
# than its share of a contended laptop, which is the only form in which the
# column is worth printing.
#
# Every engine is loaded by its OWN bulk loader, never by queries from a client:
# the LOAD column of the lesson is each engine's fastest way in, and a client
# would measure a protocol instead. Neo4j and FalkorDB read the two reshaped
# copies of the export that step 1 of the module's README generates.
#
# Order: the two embedded first, because they need no container and fail fast if
# the export is wrong; then the two property graphs, which start from a wiped
# volume; then the two triple stores, whose loaders run in a one-off container.
set -uo pipefail
cd "$(dirname "$0")/../.."
PY=".venv/bin/python"
COMPOSE="docker compose -f modules/03-where-data-lives/docker-compose.yml"

step () { printf '\n\n======== %s  %s ========\n' "$1" "$(date +%H:%M:%S)"; }
fail=0

step "kuzu (embedded)"
$PY tools/03-where-data-lives/load_kuzu.py   || { echo "KUZU FAILED"; fail=1; }

step "oxigraph (embedded)"
$PY tools/03-where-data-lives/load_oxigraph.py || { echo "OXIGRAPH FAILED"; fail=1; }

step "neo4j (neo4j-admin, server down)"
# Brought up once on an empty volume so that compose owns it; the importer then
# stops the server, overwrites the store and starts it again.
$COMPOSE --profile neo4j down -v
$COMPOSE --profile neo4j up -d
for i in $(seq 60); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' kgtp-m3-neo4j 2>/dev/null)" = healthy ] && break
  sleep 5
done
$PY tools/03-where-data-lives/load_neo4j_offline.py || { echo "NEO4J FAILED"; fail=1; }

step "falkordb (falkordb-bulk-insert, server up)"
$COMPOSE --profile falkordb down -v
$COMPOSE --profile falkordb up -d
for i in $(seq 60); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' kgtp-m3-falkordb 2>/dev/null)" = healthy ] && break
  sleep 5
done
$PY tools/03-where-data-lives/load_falkordb_offline.py || { echo "FALKORDB FAILED"; fail=1; }

step "graphdb"
$PY tools/03-where-data-lives/load_rdf.py graphdb || { echo "GRAPHDB FAILED"; fail=1; }

step "fuseki"
$PY tools/03-where-data-lives/load_rdf.py fuseki   || { echo "FUSEKI FAILED"; fail=1; }

step "all four servers up together, which is how the lesson runs"
$COMPOSE --profile all up -d

printf '\n\n======== load-times.json ========\n'
$PY - <<'EOF'
import json, os
p = "modules/03-where-data-lives/import/load-times.json"
d = json.load(open(p)) if os.path.exists(p) else {}
# The file carries prose as well as measurements: keys starting with `_` are
# notes left by whoever took the number, and they are not engines.
d = {k: v for k, v in d.items() if not k.startswith("_")}
# No store column: the offline loaders do not record one, and the lesson
# measures every store live with `du` instead.
print(f"  {'':<18}{'seconds':>9}   content")
for k in sorted(d, key=lambda k: d[k].get("load_s") or d[k].get("total_s") or 0):
    v = d[k]
    secs = v.get("total_s") or v.get("load_s")
    what = (f"{v['triples']:,} triples" if "triples" in v
            else f"{v.get('nodes', 0):,} nodes, {v.get('edges', 0):,} edges")
    print(f"  {k:<18}{secs:>8}s   {what}")
EOF
exit $fail
