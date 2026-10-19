#!/usr/bin/env -S python3 -u
"""One way to ask a question of any of the six engines.

    from engines import ask, ENGINES

    ask("neo4j",    "MATCH (n) RETURN count(n) AS c")
    ask("graphdb",  "SELECT (COUNT(*) AS ?n) WHERE { GRAPH <...> {?s ?p ?o} }")
    ask("kuzu",     "MATCH (:Organization)-[:IS_SIMILAR_TO]->() RETURN count(*)")

Every call returns the same shape -- a list of lists, one per row, in the order
the query names its columns -- whether it crossed a socket, a Redis connection or
nothing at all.

**Why this exists rather than six clients in every cell.** Before it, each cell
that compared the six carried its own driver setup, its own try/except per engine
and its own result unpacking: `result_set` for FalkorDB, `has_next()/get_next()`
for Kuzu, `.values()` for Neo4j, a JSON envelope for SPARQL over HTTP. Seventeen
lines of that in one cell is seventeen lines in which the lesson is not visible.

**And one thing it hides that the lesson must NOT hide.** `ask` applies the Kuzu
dialect automatically: a relationship type used between more than one pair of
labels is several tables on that engine, so `[:IS_SIMILAR_TO]` matches nothing
there and the pair has to be named. The rewriting happens here so that every
caller does not carry it -- but *The same question, six times* still marks every
cell where it ran, and `dialect()` below is what it ran. A convenience that made
the price invisible would be deleting the finding.

Connections are cached per engine. The two embedded stores are directories this
process opens, and opening them repeatedly is wasted work; the four served ones
hold a connection open for the same reason.
"""

import json
import os
import urllib.parse
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
IMPORT = os.path.join(ROOT, "modules", "03-where-data-lives", "import")
CSV = os.path.join(IMPORT, "csv")
GRAPH = "http://kgtp.org/graph/kgtp"

ENGINES = ("neo4j", "falkordb", "kuzu", "graphdb", "fuseki", "oxigraph")
LPG = ("neo4j", "falkordb", "kuzu")
RDF = ("graphdb", "fuseki", "oxigraph")
EMBEDDED = ("kuzu", "oxigraph")

LANG = {e: ("cypher" if e in LPG else "sparql") for e in ENGINES}

NEO4J_URI = os.environ.get("KGTP_M3_NEO4J_URI", "bolt://localhost:7690")
NEO4J_AUTH = (os.environ.get("KGTP_M3_NEO4J_USER", "neo4j"),
              os.environ.get("KGTP_M3_NEO4J_PASSWORD", "kgtp-local"))
FALKOR = ("localhost", 6379)
KUZU_DB = os.path.join(IMPORT, "kuzu", "kgtp.db")
OXIGRAPH_DB = os.path.join(IMPORT, "oxigraph", "kgtp.db")
HTTP = {"graphdb": "http://localhost:7200/repositories/kgtp",
        "fuseki":  "http://localhost:3030/ds/sparql"}

PREFIX = """PREFIX voc: <http://kgtp.org/voc/>
PREFIX id: <http://kgtp.org/id/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""

_conn = {}


# --------------------------------------------------------------- the Kuzu dialect
def _multi_pair():
    """Relationship types used between more than one pair of labels.

    Read from the exported schema rather than listed here, so that an edge added
    to the export cannot leave this stale.
    """
    schema = json.load(open(os.path.join(CSV, "schema.json")))
    seen = {}
    for spec in schema["edges"].values():
        seen.setdefault(spec["type"], []).append((spec["from"], spec["to"]))
    return {t: pairs for t, pairs in seen.items() if len(pairs) > 1}


def dialect(cypher, pairs=None):
    """The same Cypher, with Kuzu's table names where the plain type is ambiguous.

    This is a REWRITE and not a translation: every other engine runs the original
    text unchanged. Three of the module's ten questions need it, on this engine
    alone, and the lesson's timing table marks them `+Qn`.
    """
    out = cypher
    for t, pp in (pairs or _multi_pair()).items():
        for src, dst in pp:
            # `(:Src)-[:TYPE]->` and `[:TYPE*2..3]` both have to be reached, so the
            # label is matched from the pattern around the type rather than guessed.
            out = out.replace(f"(:{src})-[:{t}]->(:{dst})",
                              f"(:{src})-[:{t}__{src}__{dst}]->(:{dst})")
            out = out.replace(f"(:{src})-[:{t}*", f"(:{src})-[:{t}__{src}__{dst}*")
            out = out.replace(f"(a:{src})-[:{t}*", f"(a:{src})-[:{t}__{src}__{dst}*")
    return out


# --------------------------------------------------------------- the six clients
def _neo4j():
    from neo4j import GraphDatabase
    if "neo4j" not in _conn:
        # The deprecation notices GDS raises on every call land in the notebook's
        # output and bury the table under them. They are about procedure names we
        # are not going to change inside a nine-week course, so they are off.
        _conn["neo4j"] = GraphDatabase.driver(
            NEO4J_URI, auth=NEO4J_AUTH, notifications_min_severity="OFF")
    d = _conn["neo4j"]

    def go(q):
        with d.session() as s:
            return [list(r.values()) for r in s.run(q)]
    return go


def _falkordb():
    from falkordb import FalkorDB
    if "falkordb" not in _conn:
        _conn["falkordb"] = FalkorDB(host=FALKOR[0], port=FALKOR[1]).select_graph("kgtp")
    g = _conn["falkordb"]
    return lambda q: [list(r) for r in g.query(q).result_set]


def _kuzu():
    import kuzu
    if "kuzu" not in _conn:
        _conn["kuzu"] = kuzu.Connection(kuzu.Database(KUZU_DB, read_only=True))
    c = _conn["kuzu"]

    def go(q):
        r = c.execute(dialect(q))
        out = []
        while r.has_next():
            out.append(list(r.get_next()))
        return out
    return go


def _embedded_rdf():
    import pyoxigraph as ox
    if "oxigraph" not in _conn:
        _conn["oxigraph"] = ox.Store.read_only(OXIGRAPH_DB)
    store = _conn["oxigraph"]

    def go(q):
        res = store.query(PREFIX + q)
        if isinstance(res, ox.QueryBoolean):
            return [[str(bool(res)).lower()]]
        rows = []
        for sol in res:
            try:
                rows.append([None if t is None else t.value for t in sol])
            except TypeError:                       # a triple, not a solution
                rows.append([sol.subject.value, sol.predicate.value, sol.object.value])
        return rows
    return go


def _http_rdf(engine):
    url = HTTP[engine]

    def go(q):
        body = urllib.parse.urlencode({"query": PREFIX + q}).encode()
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/sparql-results+json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            d = json.load(r)
        if "boolean" in d:
            return [[str(d["boolean"]).lower()]]
        cols = d["head"]["vars"]
        return [[b[c]["value"] if c in b else None for c in cols]
                for b in d["results"]["bindings"]]
    return go


_RUNNER = {"neo4j": _neo4j, "falkordb": _falkordb, "kuzu": _kuzu,
           "oxigraph": _embedded_rdf,
           "graphdb": lambda: _http_rdf("graphdb"),
           "fuseki": lambda: _http_rdf("fuseki")}


# --------------------------------------------------------------- the one entry point
def ask(engine, query=None, *, cypher=None, sparql=None):
    """Ask one engine one question, and get rows back.

    Either pass `query` -- the right language for that engine -- or pass both
    `cypher` and `sparql` and let the paradigm decide. The second form is what the
    comparison cells want: one call, six engines, and the question written twice
    because the two languages are the subject.

    Raises whatever the client raises. An engine being down is a result the caller
    should report, not something to swallow here.
    """
    if query is None:
        query = cypher if engine in LPG else sparql
    if query is None:
        raise ValueError(f"no {LANG[engine]} given for {engine}")
    return _RUNNER[engine]()(query)


def one(engine, query=None, **kw):
    """The first cell of the first row, for the very common counting case."""
    rows = ask(engine, query, **kw)
    return rows[0][0] if rows and rows[0] else None


def up(engines=ENGINES):
    """Which engines answer right now, and why the others do not.

    Returns {engine: None} when it answers and {engine: "reason"} when it does not,
    so a cell can report a missing engine instead of dying on it.
    """
    out = {}
    for e in engines:
        try:
            ask(e, cypher="MATCH (n) RETURN n LIMIT 1",
                sparql="SELECT ?s WHERE { ?s ?p ?o } LIMIT 1")
            out[e] = None
        except Exception as ex:
            out[e] = f"{type(ex).__name__}: {str(ex)[:60]}"
    return out


def close():
    for e, c in list(_conn.items()):
        try:
            c.close()
        except Exception:
            pass
        del _conn[e]
