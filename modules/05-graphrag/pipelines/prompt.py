"""Every prompt this module sends, in one place.

Kept out of the code that sends them for the reason `rag/prompt.py` already
follows here: a prompt edited inside the function that uses it is a prompt
nobody diffs, and half the behaviour of these three approaches is in this file
rather than in the other five.
"""

ANSWER_PROMPT = {
    "system": (
        "Answer only from the context provided. Name the purchase order you "
        "took each fact from. If the context does not contain the answer, say "
        "so rather than guess: an invented answer is worse than none, because "
        "it arrives with sources attached."),
    "user": "Context:\n{context}\n\nQuestion: {question}",
    "max_tokens": 400,
}

AGENT_PROMPT = {
    "system": (
        "You answer questions about City of Chicago procurement contracts.\n"
        "Two tools: search_documents reads the contract PDFs, run_cypher "
        "queries the graph.\n"
        "Plan your calls. Read each result before deciding the next one.\n"
        "An empty result is information, not a reason to repeat the same "
        "call -- and it does not mean the record is absent: it can equally "
        "mean the query was wrong.\n"
        "Answer when you have enough, and say what you could not establish."),
}


# --- text2cypher -----------------------------------------------------------
#
# Carried over from `rag/prompt.py`, which is where this pipeline was written
# first. Reused rather than rewritten: they are the result of the tuning that
# produced the measurement in decision 16, and a fresh prompt would have made
# that number describe a system that no longer exists.

# The second and third lines are there because of a false refusal. Asked "how
# many contracts are in the graph?" the first version answered `end`: it read
# "in the graph" as a question about the database rather than about procurement,
# and the pipeline told a student that a counting question over contracts was
# off topic. Measured 4/11/2026 on six in-scope questions and three out: the
# first version let 5 of 6 through, this one 6 of 6, and both still refuse all
# three of `capital of France`, a poem, and tomorrow's weather.
GUARDRAIL_PROMPT = {
    "system": (
        "Decide whether this graph can be asked the question. The graph holds "
        "public procurement: contracts, their revisions, licences, supplier "
        "organisations, the departments that award them and the people "
        "involved.\n"
        "Answer 'ok' for anything that graph could be queried for, including "
        "how many of something there are, or how much, or when -- a question "
        "about the data itself is still a question about procurement.\n"
        "Answer 'end' only when the subject is not procurement at all.\n"
        "Nothing else."),
    "user": "{question}",
}

GENERATE_CYPHER_PROMPT = {
    "system": (
        "You are a Neo4j expert. Convert the question into one valid, "
        "executable Cypher query.\n"
        "Respond with the query and nothing else: no preamble, no explanation, "
        "no markdown fences. Use only what the schema contains."),
    "user": "Schema:\n{schema}\n\nQuestion: {question}\n\nCypher:",
}

VALIDATE_CYPHER_PROMPT = {
    "system": (
        "You review a Cypher query written by someone else, against the schema "
        "and the question it is meant to answer."),
    "user": (
        "Check for: syntax errors; undefined variables; labels, relationship "
        "types or properties that are not in the schema; relationships whose "
        "endpoints or direction the schema does not allow; and whether the "
        "query returns enough to answer the question.\n\n"
        "Be specific -- \"Property 'bar' does not exist on label 'Foo', did you "
        "mean 'baz'?\" -- and do not invent errors that are not there.\n\n"
        "Return an empty list when the query is correct. Every item you return "
        "is read as a defect and sends the query back to be rewritten, so a "
        "list is not a review: do not report what the query gets right, do not "
        "restate the question, and do not include an item that ends by saying "
        "the query is fine after all.\n\n"
        "The schema below is the only evidence. For any claim about a label, a "
        "relationship type, a property or a direction, quote the line of the "
        "schema you are relying on, verbatim, inside the item. If you cannot "
        "find a line that shows it, you have not found a defect -- say "
        "nothing. The relationship table is written as "
        "`(Source)-[:TYPE]->(Target)`, so the direction is there to read and "
        "is never a matter of judgement.\n\n"
        "Schema:\n{schema}\n\nQuestion: {question}\n\nCypher:\n{cypher}"),
}

CORRECT_CYPHER_PROMPT = {
    "system": (
        "You fix a Cypher query using the schema, the question and an error "
        "report. Output the corrected query only: no explanation, no fences."),
    "user": ("Schema:\n{schema}\n\nQuestion: {question}\n\n"
             "Cypher:\n{cypher}\n\nErrors:\n{errors}\n\nCorrected Cypher:"),
}

CYPHER_ANSWER_PROMPT = {
    "system": (
        "You are given the rows a graph query returned. Answer the question "
        "from them, in plain language. If the rows are empty, say that the "
        "query returned nothing -- which is not the same as saying the fact "
        "does not exist, and the difference matters here."),
    "user": "Rows: {rows}\n\nQuestion: {question}",
    "max_tokens": 400,
}
