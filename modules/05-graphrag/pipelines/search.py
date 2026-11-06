"""Text retrieval over the two indexes, and the rewrite that feeds the lexical one.

    from pipelines.search import search_descriptions, search_titles, rewrite

The companion of `graph.py`: that file walks relationships, this one reads text.
Together they are everything the agent in `react.py` can do, and the notebook
shows each of them running on its own before the agent is allowed to choose.

Two indexes, and the split is decision 34. The dense one holds the **130**
descriptions that are real prose; the lexical one holds **87,486** contract
titles. Short titles make bad vectors -- with all 917 descriptions embedded,
`Demolition Services` came back in the top five for three of twelve unrelated
questions -- so prose is searched by meaning and labels by words.
"""

from __future__ import annotations

from pipelines.config import setting
from pipelines.models import NO_THINKING

# Terms kept from the rewrite. Fifteen, and the number matters: copied as 12
# while moving this code on 23/9/2026, it changed the Lucene query enough to
# take `unrelated-agent` to 0 of 3 runs.
MAX_TERMS = 15

T1 = """
CALL db.index.vector.queryNodes('description_embedding', $n, $v) YIELD node, score
MATCH (c:Contract)-[:HAS_DESCRIPTION]->(node)
RETURN c.id AS po, node.text AS name, score
ORDER BY score DESC LIMIT $k
"""

T2 = """
CALL db.index.fulltext.queryNodes('contract_name', $q) YIELD node, score
RETURN node.id AS po, node.name AS name, score
ORDER BY score DESC LIMIT $k
"""

# Asked for Lucene directly the model wrote the operator in lower case, and `or`
# in lower case is a term rather than an operator: the index then answered
# `LAMPS, FLOOD OR SPOT` at 82.78 against 8.90 for the right contract --
# confidently, and wrongly. Measured 15/9/2026. Asked for the words a clerk
# would type, it stays inside what it is good at and the query is built here.
REWRITE_PROMPT = """Name the words a City of Chicago purchase order might use for the
thing this question is about. Titles are terse and inconsistent: the same thing
is called `PEST CONTROL` on one contract and `RODENT ABATEMENT` on another.

Give the words a procurement clerk would have typed, in English, singular and
plural where both are used. Words and short phrases only.

Answer with JSON and nothing else: {"terms": ["...", "..."]}

Question: """


# What this model asks for in front of a question. It was trained
# asymmetrically -- documents embedded plainly, questions behind an instruction
# -- and leaving it out costs relevance with nothing to show that it did.
#
# Measured 23/9/2026 on four questions with an answer among the 130 descriptions
# and four without, taking the top score of each:
#
#                      with an answer   without      gap
#     with the prefix   0.809-0.883     0.653-0.731  0.078
#     without it        0.783-0.865     0.727-0.766  0.017
#
# The bands separate either way and `RELEVANT = 0.78` sits inside both gaps, but
# without the prefix the margin is one hundredth of a point, which is not a
# threshold, it is a coincidence. Until this date the agent embedded its
# questions plain and the notebook embedded them with the prefix: same question,
# 0.783 against 0.823, on opposite sides of the line.
QUERY_PREFIX = ("Instruct: Given a web search query, retrieve relevant passages "
                "that answer the query\nQuery:")


def vector(question: str) -> list[float]:
    """The question as the embedding the index was built with."""
    from openai import OpenAI

    api = OpenAI(base_url=setting("embeddings", "base_url"),
                 api_key=setting("embeddings", "api_key"),
                 timeout=60.0, max_retries=3)
    # The prefix is NOT applied, and that is a decision with a measurement
    # against it: see A30. Applying it widens the gap between a question with an
    # answer and one without from 0.017 to 0.078, but every score rises by about
    # four hundredths and `RELEVANT = 0.78` was calibrated without it. Tried on
    # 23/9/2026: `unrelated-agent` and `vendor-ranking` went to 0 of 3 runs, and
    # moving the line to 0.80 did not bring them back. Recalibrating properly
    # needs a question set, not a third guess.
    return api.embeddings.create(model=setting("embeddings", "model"),
                                 input=[question]).data[0].embedding


def search_descriptions(session, question: str, k: int = 5,
                        overfetch: int = 20) -> list[dict]:
    """The dense index over prose. Returns rows with `po`, `name`, `score`.

    `overfetch` asks the index for more neighbours than are kept, because two
    descriptions can belong to the same contract and collapsing them afterwards
    would otherwise return fewer than k, silently and unevenly.
    """
    return [dict(r) for r in session.run(T1, v=vector(question), n=overfetch, k=k)]


def search_titles(session, query: str, k: int = 8) -> list[dict]:
    """The lexical index over 87,486 contract titles.

    A malformed Lucene query is a result, not a crash: the caller is often a
    model, and an exception ends the conversation where a message lets it try
    something else.
    """
    try:
        return [dict(r) for r in session.run(T2, q=query, k=k)]
    except Exception as error:      # noqa: BLE001 - reported, not raised
        return [{"po": None, "name": f"bad query: {type(error).__name__}", "score": 0.0}]


def lucene(terms: list[str]) -> str:
    quoted = [f'"{term.strip()}"' for term in terms if term and term.strip()]
    return " OR ".join(list(dict.fromkeys(quoted))[:MAX_TERMS])


def rewrite(question: str) -> str:
    """The question as words a procurement clerk might have typed.

    Only the lexical index needs this. The dense one matches meaning already, so
    widening the vocabulary is what words need and vectors do not.

    The fallback matters: a list cut off at the token limit leaves valid JSON
    behind it but not in front -- `..., "silverfish control", "be`. Every
    complete quoted string before the cut is still usable, and dropping the
    whole answer for the last broken one is how `disinfestazione` went back to
    zero results on 15/9/2026.
    """
    import json
    import re

    from openai import OpenAI

    api = OpenAI(base_url=setting("llm", "base_url"), api_key=setting("llm", "api_key"),
                 timeout=60.0, max_retries=8)
    reply = api.chat.completions.create(
        model=setting("llm", "model"), temperature=0, max_tokens=600, extra_body=NO_THINKING,
        messages=[{"role": "user", "content": REWRITE_PROMPT + question}])
    content = reply.choices[0].message.content or ""

    terms: list[str] = []
    match = re.search(r"\{.*\}", content, re.S)
    if match:
        try:
            terms = json.loads(match.group(0)).get("terms") or []
        except json.JSONDecodeError:
            terms = []
    if not terms:
        terms = [t for t in re.findall(r'"([^"]{2,60})"', content) if t.lower() != "terms"]
    return lucene(terms) or question
