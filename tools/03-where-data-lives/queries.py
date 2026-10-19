#!/usr/bin/env -S python3 -u
"""Ten questions, asked in Cypher and in SPARQL, with the same answer required.

A timing is worth reading only while the engines are answering the same
question, so every entry carries `check`: a value that must come out identical
on all six. The runner refuses to report a timing whose check does not match,
and names the engine that disagreed. A missing number is a result; a wrong one
is a lie.

The questions are ordered by what they stress, not by difficulty:

    Q1  point lookup            index hit, one row
    Q2  property scan           no index, full label scan
    Q3  one hop                 adjacency
    Q4  two hops                adjacency twice, with a join
    Q5  five hops               across the resolved entity layer
    Q6  aggregation             grouping and sum over 185,730 records
    Q7  group expansion         fan-out from the entity layer
    Q8  substring match         a scan on every engine, and that is the point
    Q9  variable-length path    the one shape SPARQL cannot write
    Q10 global count            whole-store aggregation

Q9 stays in the set although SPARQL has no form for it: property paths can find
whether a path exists, but cannot return it, bound its length and keep the
intermediate nodes. That is not a performance difference, so it is reported as
`unsupported` rather than as slow.
"""

# The graph name and the prefixes live in `engines`, which every caller of
# this module already imports. Written twice they would drift, and a query
# naming the wrong graph answers zero rows without an error.
from engines import GRAPH, PREFIX

# A department with enough contracts to make the traversals real, and a
# contract that exists. Both pinned so every engine is asked about the same
# rows: picking "any department" would let each engine answer an easier one.
DEPT = "DEPARTMENT OF WATER MANAGEMENT"
CONTRACT = "302701"

QUERIES = [
    dict(
        id="Q1_point_lookup", stress="index hit, one row",
        cypher=f"MATCH (c:Contract {{id: '{CONTRACT}'}}) RETURN c.id AS id, c.name AS name",
        # The IRI is written out instead of using the `id:` prefix: a prefixed
        # name cannot carry an unescaped slash, and `id:Contract/302701` is a
        # syntax error rather than a lookup, answered HTTP 400. Every instance
        # IRI in this dataset has that shape, so the prefix is only ever
        # useful for the namespace declaration.
        sparql=f"""SELECT ?id ?name WHERE {{
  GRAPH <{GRAPH}> {{ <http://kgtp.org/id/Contract/{CONTRACT}> voc:id ?id ; voc:name ?name }} }}""",
    ),
    dict(
        id="Q2_property_scan", stress="full label scan, no index",
        cypher="MATCH (r:ContractRecord) WHERE r.amount > 10000000 "
               "RETURN count(r) AS n",
        sparql=f"""SELECT (COUNT(*) AS ?n) WHERE {{
  GRAPH <{GRAPH}> {{ ?r voc:amount ?a . FILTER(?a > 10000000.0) }} }}""",
    ),
    dict(
        id="Q3_one_hop", stress="adjacency, one step",
        cypher=f"MATCH (d:Department {{id: '{DEPT}'}})-[:ASSIGNS_CONTRACT]->(c:Contract) "
               f"RETURN count(c) AS n",
        sparql=f"""SELECT (COUNT(*) AS ?n) WHERE {{
  GRAPH <{GRAPH}> {{ ?d voc:id "{DEPT}" ; voc:ASSIGNS_CONTRACT ?c }} }}""",
    ),
    dict(
        id="Q4_two_hops", stress="adjacency twice",
        cypher=f"MATCH (d:Department {{id: '{DEPT}'}})-[:ASSIGNS_CONTRACT]->(:Contract)"
               f"-[:HAS_VENDOR]->(o:Organization) RETURN count(DISTINCT o) AS n",
        sparql=f"""SELECT (COUNT(DISTINCT ?o) AS ?n) WHERE {{
  GRAPH <{GRAPH}> {{ ?d voc:id "{DEPT}" ; voc:ASSIGNS_CONTRACT ?c .
                     ?c voc:HAS_VENDOR ?o }} }}""",
    ),
    dict(
        # Five hops, and it crosses the entity layer, which is the whole reason
        # this question is the interesting one: "which licences are held by the
        # companies this department contracts with".
        #
        # The obvious three-hop version -- department, contract, vendor, then
        # straight to that vendor's licences -- returns ZERO on every engine,
        # and the reason is a property of the graph rather than a bug in the
        # query. 14,094 Organizations are contract vendors,
        # 196,646 hold a licence, and the two sets do not intersect AT ALL. The
        # contracts file and the licence file each produce their own
        # Organization rows and nothing merges them at that level -- the merge
        # is one floor up, in OrganizationGroup. So the bridge has to go through
        # the group, and a benchmark timing the empty version would have been
        # timing nothing. It answers 3,888.
        id="Q5_entity_crossing", stress="five hops, across the resolved entity layer",
        # Kuzu needs a different table name here, and the reason is the price of
        # its DDL. BELONGS_TO_ORG_GROUP spans two label pairs, so on Kuzu it is
        # two tables rather than one REL TABLE GROUP -- the split that makes its
        # algorithm library reachable at all. `[:BELONGS_TO_ORG_GROUP]` therefore
        # matches nothing there, and the pair has to be named.
        cypher=f"MATCH (d:Department {{id: '{DEPT}'}})-[:ASSIGNS_CONTRACT]->(:Contract)"
               f"-[:HAS_VENDOR]->(:Organization)-[:BELONGS_TO_ORG_GROUP]->(g:OrganizationGroup)"
               f"<-[:BELONGS_TO_ORG_GROUP]-(:Organization)-[:ORG_HAS_LICENSE]->(l:LicenseRecord) "
               f"RETURN count(DISTINCT l) AS n",
        sparql=f"""SELECT (COUNT(DISTINCT ?l) AS ?n) WHERE {{
  GRAPH <{GRAPH}> {{ ?d voc:id "{DEPT}" ; voc:ASSIGNS_CONTRACT ?c .
                     ?c voc:HAS_VENDOR ?o .
                     ?o voc:BELONGS_TO_ORG_GROUP ?g .
                     ?o2 voc:BELONGS_TO_ORG_GROUP ?g .
                     ?o2 voc:ORG_HAS_LICENSE ?l }} }}""",
    ),
    dict(
        id="Q6_aggregation", stress="group and sum over 185,730 records",
        cypher="MATCH (r:ContractRecord)-[:RECORDED_VENDOR]->(o:Organization) "
               "WHERE r.amount IS NOT NULL "
               "WITH o.id AS vendor, sum(r.amount) AS total "
               "RETURN vendor, total ORDER BY total DESC, vendor LIMIT 10",
        sparql=f"""SELECT ?vendor (SUM(?a) AS ?total) WHERE {{
  GRAPH <{GRAPH}> {{ ?r voc:RECORDED_VENDOR ?o ; voc:amount ?a . ?o voc:id ?vendor }} }}
GROUP BY ?vendor ORDER BY DESC(?total) ?vendor LIMIT 10""",
    ),
    dict(
        id="Q7_group_expansion", stress="fan-out from the entity layer",
        cypher="MATCH (g:OrganizationGroup)<-[:BELONGS_TO_ORG_GROUP]-(o:Organization) "
               "WITH g, count(o) AS n ORDER BY n DESC, g.clusterId LIMIT 1 "
               "RETURN g.clusterId AS grp, n",
        sparql=f"""SELECT ?grp (COUNT(*) AS ?n) WHERE {{
  GRAPH <{GRAPH}> {{ ?o voc:BELONGS_TO_ORG_GROUP ?g . ?g voc:clusterId ?grp }} }}
GROUP BY ?grp ORDER BY DESC(?n) ?grp LIMIT 1""",
    ),
    dict(
        # NOT a full-text index test, although it looks like one. Neither
        # form touches an index: `CONTAINS` in SPARQL is a filter over scanned
        # literals, and Cypher's CONTAINS does not use a full-text index either.
        # So this row compares how fast each engine scans, which is worth
        # knowing and is not what it claimed to be. The real index comparison
        # needs `text:query` on Jena and `db.index.fulltext.queryNodes` on
        # Neo4j -- engine-specific syntax with no common form, so it is a
        # separate exercise rather than a row in this table.
        id="Q8_name_search", stress="substring match -- a scan on every engine",
        cypher="MATCH (o:Organization) WHERE o.name CONTAINS 'CONSTRUCTION' "
               "RETURN count(o) AS n",
        # `?o rdf:type voc:Organization` is the question, not decoration: Q8
        # asks for ORGANISATIONS. Written without it, the pattern matches
        # everything in the store carrying a voc:name -- licence rows, contract
        # rows, groups -- and answers 25,644 instead of 2,957.
        #
        # That was a defect in this query and not a property of RDF: `MATCH (o)`
        # without the label answers the same 25,644 on Neo4j, with the same
        # breakdown. Both languages let you leave the class out, and
        # neither warns. The runner caught it because the answers disagreed --
        # which is the only reason it is worth recording here.
        sparql=f"""SELECT (COUNT(*) AS ?n) WHERE {{
  GRAPH <{GRAPH}> {{ ?o rdf:type voc:Organization ; voc:name ?nm .
                     FILTER(CONTAINS(?nm, "CONSTRUCTION")) }} }}""",
    ),
    dict(
        # This is the row where the whole answers-before-timings mechanism paid
        # for itself, and the divergence is NOT a mistake in the query.
        #
        # Neo4j 18,670, FalkorDB 18,670, Kuzu 18,898. By
        # path length, Neo4j and Kuzu agree at length 2 (8,403 each) and differ
        # at length 3 -- 10,267 against 10,495. The gap is exactly 228, which is
        # the number of IS_SIMILAR_TO edges `a->b` whose reciprocal `b->a` also
        # exists. Each one yields the walk a->b->a->b, which REPEATS the edge
        # a->b. Neo4j and FalkorDB forbid repeating a relationship inside one
        # path; Kuzu allows it. 10,267 + 228 = 10,495.
        #
        # So the same Cypher text means two different things in two engines that
        # both speak Cypher -- trail semantics against walk semantics -- on a
        # construct anyone would assume portable. Reported as a disagreement and
        # never averaged: a latency table alone would have shown Kuzu as 400x
        # slower than FalkorDB while answering a different question.
        id="Q9_var_length_path", stress="variable-length path, returned",
        cypher="MATCH p = (a:Organization)-[:IS_SIMILAR_TO*2..3]->(b:Organization) "
               "RETURN count(p) AS n",
        sparql=None,  # see the module docstring: not expressible, not slow
    ),
    dict(
        id="Q10_global_count", stress="whole-store aggregation",
        cypher="MATCH (l:LicenseRecord)-[:HAS_LICENSE_TYPE]->(t:LicenseType) "
               "WITH t.id AS type, count(l) AS n "
               "RETURN type, n ORDER BY n DESC, type LIMIT 5",
        sparql=f"""SELECT ?type (COUNT(*) AS ?n) WHERE {{
  GRAPH <{GRAPH}> {{ ?l voc:HAS_LICENSE_TYPE ?t . ?t voc:id ?type }} }}
GROUP BY ?type ORDER BY DESC(?n) ?type LIMIT 5""",
    ),
]


# --- the Kuzu dialect, and what it costs -------------------------------------
#
# Kuzu models IS_SIMILAR_TO and BELONGS_TO_ORG_GROUP as one table PER LABEL PAIR,
# because a REL TABLE GROUP makes project_graph refuse a subset and Louvain refuse
# to run at all. The trade is here: 2 of the 18 relationship types are split, and
# **3 of these 10 questions need a different text on that engine**. The other 16
# types and 7 questions are identical everywhere.
#
# This is the whole of the price, written down rather than described. Anyone
# reading the table should be able to see exactly which cells are not the same
# query.
def cypher_for(spec, engine):
    """The Cypher to send, with the Kuzu table names substituted where needed."""
    q = spec["cypher"]
    if engine != "kuzu" or q is None:
        return q
    return (q.replace("BELONGS_TO_ORG_GROUP]",
                      "BELONGS_TO_ORG_GROUP__Organization__OrganizationGroup]")
             .replace("IS_SIMILAR_TO*",
                      "IS_SIMILAR_TO__Organization__Organization*"))


# How many questions the dialect touches, asserted rather than assumed: if a
# future edit makes it four, this fails loudly instead of drifting.
_touched = [q["id"] for q in QUERIES
            if q["cypher"] and cypher_for(q, "kuzu") != q["cypher"]]
assert len(_touched) == 3, f"expected 3 questions to need the Kuzu dialect, got {_touched}"


def norm(rows):
    """Canonical form of an answer, so two engines can be held to the same one.

    Numbers are rounded to two decimals: the stores do not agree on how to
    print a double, and `1.0E7` against `10000000.0` is not a disagreement
    about the data. Everything else is compared as text -- so a date that one
    engine holds as a `Date` and another as a string compares EQUAL here, and
    a check on the answers alone cannot catch that difference.
    """
    out = []
    for r in rows:
        row = []
        for v in r:
            if isinstance(v, bool):
                row.append(str(v).lower())
            elif isinstance(v, (int, float)):
                row.append(f"{float(v):.2f}")
            else:
                s = str(v)
                # A store may give back a typed literal or a bare lexical form.
                for suffix in ('^^http://www.w3.org/2001/XMLSchema#integer',
                               '^^http://www.w3.org/2001/XMLSchema#double',
                               '^^http://www.w3.org/2001/XMLSchema#decimal'):
                    if s.endswith(suffix):
                        s = s[: -len(suffix)]
                try:
                    row.append(f"{float(s):.2f}")
                except ValueError:
                    row.append(s)
        out.append(tuple(row))
    return out
