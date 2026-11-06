"""The two retrievers and the graph lookup, with the Cypher they run.

The queries are here in full rather than behind a helper, because which pages
come back is the thing being compared and the query is the comparison.
"""

from __future__ import annotations

from neo4j import GraphDatabase

from pipelines.models import embedding_model
from pipelines.config import setting

LEXICAL = """
// Words, not meaning. The full-text index covers every page that has text.
CALL db.index.fulltext.queryNodes('page_text', $question) YIELD node, score
MATCH (node)<-[:HAS_PAGE]-(d:Document)<-[:HAS_DOCUMENT]-(:ContractRecord)
      -[:INCLUDED_IN_CONTRACT]->(c:Contract)
// `d.id` because the page number alone does not identify a page. A purchase
// order is filed once per revision, each filing is its own Document, and each
// has its own page 2 with different text on it. Measured 5/11/2026 on 214209:
// `..._r0` page 2 is 1,025 characters, `..._r1` page 2 is 2,495, and printed as
// `PO 214209 p2` twice they read as one page retrieved twice.
RETURN c.id AS purchase_order, node.page AS page, node.text AS text,
       d.id AS document, round(score, 2) AS score
ORDER BY score DESC LIMIT $k
"""

DENSE = """
// Meaning, not words. One vector per page, all 92,439 of them.
CALL db.index.vector.queryNodes('page_embedding', $k, $vector) YIELD node, score
MATCH (node)<-[:HAS_PAGE]-(d:Document)<-[:HAS_DOCUMENT]-(:ContractRecord)
      -[:INCLUDED_IN_CONTRACT]->(c:Contract)
RETURN c.id AS purchase_order, node.page AS page, node.text AS text,
       d.id AS document, round(score, 3) AS score
ORDER BY score DESC
"""

NEIGHBOURS = """
// One hop out of a purchase order, grouped by relation rather than listed as
// triples: the paper measures 19-53% fewer tokens for the same content, and
// tokens are the budget this module runs out of first.
MATCH (c:Contract {id: $purchase_order})
OPTIONAL MATCH (c)-[:HAS_VENDOR]->(o:Organization)
OPTIONAL MATCH (c)<-[:ASSIGNS_CONTRACT]-(d:Department)
OPTIONAL MATCH (c)<-[:INCLUDED_IN_CONTRACT]-(r:ContractRecord)
RETURN collect(DISTINCT o.name) AS vendors,
       collect(DISTINCT d.id) AS departments,
       count(DISTINCT r) AS revisions
"""


def driver():
    return GraphDatabase.driver(
        setting("neo4j", "uri"),
        auth=(setting("neo4j", "user"), setting("neo4j", "password")))


def session_of(d):
    """A session on the configured database, never on the server's default.

    Both calls below used `d.session()`, which lands on whatever the server
    calls default -- `neo4j` -- while this course keeps everything in `kgtp`.
    The lexical retriever answered with zero rows and no error; the dense one
    raised `There is no such vector schema index: page_embedding`, about an
    index that does exist, one database away. Found by `tools/verify.py` on
    23/9/2026.
    """
    return d.session(database=setting("neo4j", "database"))


def retrieve(session, question: str, k: int = 5, dense: bool = True) -> list[dict]:
    """Return the k pages this question retrieves, best first.

    Takes a session, like everything in `pipelines.graph` and `pipelines.search`.
    It used to open its own driver, which made this module the one place in
    module 5 with a second calling convention -- two of ten functions needed no
    session and eight did.

    Both retrievers stay, side by side, because they disagree about which
    questions they can answer. Dense retrieval compresses proper names away and
    half the questions in this module name a company: measured 1/9/2026 over the
    nine benchmark questions the lexical retriever reaches a higher MRR than the
    dense one, 0.531 against 0.472, which is not what a course on embeddings
    predicts.

    `dense=False` needs nothing but the graph, so it is the one that still runs
    when no model is being served.
    """
    if not dense:
        return [dict(r) for r in session.run(LEXICAL, question=question, k=k)]
    return [dict(r) for r in
            session.run(DENSE, vector=embedding_model().embed_query(question), k=k)]


def neighbours(session, purchase_order: str) -> dict:
    """What the graph holds about one purchase order."""
    row = session.run(NEIGHBOURS, purchase_order=purchase_order).single()
    return dict(row) if row else {}
