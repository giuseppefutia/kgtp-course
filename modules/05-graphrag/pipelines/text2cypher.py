"""Text2Cypher: the model writes the query, the graph answers it.

    from pipelines.text2cypher import text2cypher
    text2cypher("How many contracts does the Chicago Fire Department hold?").show()

    guardrail -> generate -> validate -> (correct -> validate)* -> execute -> answer

The second thing called GraphRAG, and the opposite of `graphrag.py`. There the
traversal is fixed and written by hand, so the model never needs to know how
the graph is shaped; here the model writes the traversal, so it needs the whole
schema and everything depends on whether it read it properly.

That is also why this is the only approach in the module that uses
`pipelines/schema.py`. The agent gets six label names in a tool description and
invents properties; this one gets the measured schema, and the validation node
exists because getting it is not the same as using it.

**What decision 16 measured on this pipeline, 17/8/2026.** Two rounds of
`EXPLAIN` remove every syntax error, and correctness rises by one question out
of ten. The noisy queries did not disappear -- they moved from *malformed* to
*silently wrong*. The repaired system looks far better, reports zero errors, and
is the same system getting half the answers wrong with nothing left to signal
it. Do not read the repair loop as a fix; it is the exhibit.
"""

from __future__ import annotations

import re

from operator import add
from typing import Annotated, Literal, Optional

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from pipelines.models import chat_model, invoke
from pipelines.prompt import (CORRECT_CYPHER_PROMPT, CYPHER_ANSWER_PROMPT,
                               GENERATE_CYPHER_PROMPT, GUARDRAIL_PROMPT,
                               VALIDATE_CYPHER_PROMPT)
from pipelines.retrievers import driver, session_of
from pipelines.state import Answer
from pipelines.schema import warm_up

MAX_CORRECTIONS = 2


class CypherState(TypedDict, total=False):
    question: str
    schema: str
    cypher: str
    errors: list[str]
    corrections: int
    rows: list[dict]
    answer: str
    steps: list[str]
    # One entry per round of validation: the draft as it stood, and what the
    # validator said about it. Reduced with `add` so the rounds accumulate
    # instead of the last one replacing the rest.
    #
    # Without this the caller saw the final query and nothing else, and the
    # repair loop -- which is what this pipeline is here to show -- was
    # invisible. On the Fire Department question the three rounds contradict
    # each other, and no reader could have known.
    attempts: Annotated[list[dict], add]


class Guardrail(BaseModel):
    decision: Literal["ok", "end"] = Field(
        description="ok if the question is about procurement, end if it is not")


class Validation(BaseModel):
    errors: Optional[list[str]] = Field(
        default=None,
        description="Defects that require the query to be changed, each stated "
                    "against the schema. Empty when the query is correct.")


# `### Label` headings and the relationship table, read back out of the same
# schema text the model was given -- not a second query, so the check cannot
# disagree with what the model saw.
_LABEL = re.compile(r"^### (\w+)\s*$", re.M)
_TRIPLE = re.compile(r"\| `\((\w+)\)-\[:(\w+)\]->\((\w+)\)`")
# `(a:Department)-[:ASSIGNS_CONTRACT]->(c:Contract)`, both ends named. Anything
# less than that -- a variable-length hop, an unlabelled end, a type union --
# is skipped rather than guessed at.
# The right-hand node is a lookahead, so it stays available as the left-hand
# node of the next hop. Without it `re.findall` consumed the middle node of
# `(a)-[:R]->(b)-[:S]->(c)` and never saw the second relationship -- which is
# exactly the shape of the question that fails in `Where each one breaks`.
_PATTERN = re.compile(r"\(\s*\w*\s*:\s*`?(\w+)`?[^)]*\)\s*"
                      r"(<)?-\[\s*:\s*`?(\w+)`?\s*\]-(>)?\s*"
                      r"(?=\(\s*\w*\s*:\s*`?(\w+)`?[^)]*\))")


def check_against_schema(cypher: str, schema: str) -> list[str]:
    """What the model kept getting wrong, decided by reading instead of asking.

    Measured 5/11/2026, on `How many departments award more than 1000
    contracts?`: the model validator objected to a correct query three times
    out of three, and each objection quoted the very line that refuted it --
    *"the schema defines `(Department)-[:ASSIGNS_CONTRACT]->(Contract)` ... but
    this relationship type is not present in the schema's relationship table"*.
    Asking a 3B-active model to find one line in seventeen thousand characters
    is the wrong instrument, and no wording of the prompt fixed it: an earlier
    attempt made it object to the direction instead, and the correction it
    produced returned 0 departments rather than 21.

    A label either appears in the schema or it does not. So does a relationship
    type, and so does the direction between two labels. Three exact questions,
    answered here; the model keeps only the one that is a matter of reading --
    whether the query answers what was asked. See `docs/DECISIONS.md`.

    Silent on anything it cannot parse: a wrong answer from this function would
    send a correct query back to be rewritten, which is the failure it exists
    to remove.
    """
    labels = set(_LABEL.findall(schema))
    triples = set(_TRIPLE.findall(schema))
    types = {t for _, t, _ in triples}
    if not labels or not triples:                # a schema we cannot read is
        return []                                # not evidence of anything
    problems: list[str] = []
    for used in set(re.findall(r":\s*`?(\w+)`?\s*[)\]{\s]", cypher)):
        if used in types or used in labels:
            continue
        kind, known = (("relationship type", types) if used.isupper()
                       else ("label", labels))
        near = [k for k in known if k.lower() == used.lower()]
        problems.append(f"The {kind} `{used}` is not in the schema."
                        + (f" Did you mean `{near[0]}`?" if near else ""))
    for left, back, rtype, forward, right in _PATTERN.findall(cypher):
        if not (left in labels and right in labels and rtype in types):
            continue
        a, b = (right, left) if back and not forward else (left, right)
        if (a, rtype, b) in triples:
            continue
        if (b, rtype, a) in triples:
            problems.append(
                f"`({a})-[:{rtype}]->({b})` is the wrong way round. The schema "
                f"has `({b})-[:{rtype}]->({a})`, and a pattern written "
                f"backwards is legal Cypher that matches nothing.")
        else:
            problems.append(
                f"The schema has no `{rtype}` between `{a}` and `{b}`.")
    return problems


def _ask(prompt: dict, **values) -> str:
    reply = invoke(chat_model(max_tokens=prompt.get("max_tokens", 700)), [
        ("system", prompt["system"]),
        ("user", prompt["user"].format(**values))])
    return (reply.content or "").strip()


def _clean(cypher: str) -> str:
    """Strip the markdown fence the model adds even when told not to.

    Not cosmetic: decision 15 records two correct queries scored MALFORMED
    because three backticks survived into the statement. Scaffolding that
    blames the model for its own leftovers is the failure this guards against.
    """
    text = cypher.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    return text.replace("```cypher", "").replace("```", "").strip()


# `method="function_calling"` rather than the default. The default is
# `json_schema`, which goes through the OpenAI client's `parse` API and hands
# back a message whose `parsed` field is typed `None` but carries the model --
# pydantic 2.13 flags that on every call, twice per run of this pipeline:
#
#   UserWarning: Pydantic serializer warnings:
#     PydanticSerializationUnexpectedValue(Expected `none` ... input_type=Guardrail)
#
# Measured 4/11/2026: both nodes return the same values either way, and the
# warning is gone. It is not cosmetic -- eight lines of library traceback above
# the one line this section is about reads, to a student, as something broken.
STRUCTURED = {"method": "function_calling"}


def guardrail(state: CypherState) -> CypherState:
    """Refuse questions the graph has nothing to say about."""
    decision = invoke(chat_model().with_structured_output(Guardrail, **STRUCTURED), [
        ("system", GUARDRAIL_PROMPT["system"]),
        ("user", GUARDRAIL_PROMPT["user"].format(question=state["question"]))])
    return {"schema": warm_up(quiet=True),
            "answer": ("" if decision.decision == "ok" else
                       "That question is not about procurement, so this graph "
                       "cannot answer it."),
            "steps": ["guardrail"], "corrections": 0}


def generate(state: CypherState) -> CypherState:
    cypher = _clean(_ask(GENERATE_CYPHER_PROMPT, schema=state["schema"],
                         question=state["question"]))
    return {"cypher": cypher, "steps": state["steps"] + ["generate"]}


def validate(state: CypherState) -> CypherState:
    """Three checks, cheapest and most certain first, stopping at the first that
    objects.

    `EXPLAIN` either compiles or does not, and costs no tokens.
    `check_against_schema` reads the schema instead of asking about it, and is
    exact for the three things that used to go wrong. The model is asked last
    and about one thing only, the thing neither of the others can judge:
    whether the query returns enough to answer the question.

    The order is the point. Until 5/11/2026 the model went second and objected
    to correct queries three times out of three; now it is only reached by a
    query that parses and matches the schema, and it has nothing left to
    hallucinate about.
    """
    errors: list[str] = []
    with driver() as d, session_of(d) as session:
        try:
            session.run(f"EXPLAIN {state['cypher']}").consume()
        except Exception as e:
            errors.append(f"{type(e).__name__}: {str(e)[:200]}")
    said_by = "EXPLAIN"
    if not errors:
        errors = check_against_schema(state["cypher"], state["schema"])
        said_by = "the schema"
    if not errors:
        report = invoke(chat_model().with_structured_output(Validation, **STRUCTURED), [
            ("system", VALIDATE_CYPHER_PROMPT["system"]),
            ("user", VALIDATE_CYPHER_PROMPT["user"].format(
                schema=state["schema"], question=state["question"],
                cypher=state["cypher"]))])
        errors = report.errors or []
        said_by = "the model"
    # `said_by` so a reader can tell the parser from the model. They are not the
    # same authority: EXPLAIN either compiles or does not, and the model is
    # guessing against a schema.
    return {"errors": errors, "steps": state["steps"] + ["validate"],
            "attempts": [{"cypher": state["cypher"], "errors": errors,
                          "said_by": said_by}]}


def correct(state: CypherState) -> CypherState:
    cypher = _clean(_ask(CORRECT_CYPHER_PROMPT, schema=state["schema"],
                         question=state["question"], cypher=state["cypher"],
                         errors="\n".join(state["errors"])))
    return {"cypher": cypher, "corrections": state["corrections"] + 1,
            "steps": state["steps"] + ["correct"]}


def execute(state: CypherState) -> CypherState:
    with driver() as d, session_of(d) as session:
        try:
            rows = [dict(r) for r in session.run(state["cypher"])][:50]
        except Exception as e:
            rows = [{"error": f"{type(e).__name__}: {str(e)[:200]}"}]
    return {"rows": rows, "steps": state["steps"] + ["execute"]}


def answer(state: CypherState) -> CypherState:
    return {"answer": _ask(CYPHER_ANSWER_PROMPT, rows=state["rows"],
                           question=state["question"]),
            "steps": state["steps"] + ["answer"]}


def after_guardrail(state: CypherState) -> Literal["generate", "__end__"]:
    return END if state["answer"] else "generate"


def after_validation(state: CypherState) -> Literal["correct", "execute"]:
    """Repair while there are errors and corrections left, then run it anyway.

    Running a query the validator still dislikes is deliberate: what happens
    downstream of an unrepaired query is the material, and stopping here would
    hide it behind an error message.
    """
    if state["errors"] and state["corrections"] < MAX_CORRECTIONS:
        return "correct"
    return "execute"


def build():
    graph = StateGraph(CypherState)
    for node in (guardrail, generate, validate, correct, execute, answer):
        graph.add_node(node)
    graph.add_edge(START, "guardrail")
    graph.add_conditional_edges("guardrail", after_guardrail)
    graph.add_edge("generate", "validate")
    graph.add_conditional_edges("validate", after_validation)
    graph.add_edge("correct", "validate")
    graph.add_edge("execute", "answer")
    graph.add_edge("answer", END)
    return graph.compile()


def text2cypher_with_trace(question: str) -> Answer:
    """`text2cypher`, printing every draft and who objected to it.

    Same pipeline, same return value. The name is long on purpose: a call to
    `trace(...)` does not say which pipeline is running.

    What it prints is one block per draft, because that is the unit a reader
    needs: the query as it stood, whether the database could compile it, and
    what the model said about it. A list of node names shows none of that, and
    an earlier version of this function printed a prose line per node -- which
    put sentences I had written in between the data the pipeline produced.
    """
    final: dict = {}
    drafts = 0
    for step in build().stream({"question": question, "steps": []}):
        for node, delta in step.items():
            final.update(delta)
            if node == "guardrail":
                print(f"question   {question}")
                if delta.get("answer"):
                    print(f"guardrail  off topic — {delta['answer']}")
                    continue
                schema = delta.get("schema") or ""
                print(f"schema     {len(schema):,} characters, "
                      f"{schema.count(chr(10) + '### ')} labels, given to the model")
            if delta.get("cypher"):
                drafts += 1
                room = (f"correction {drafts - 1} of {MAX_CORRECTIONS}"
                        if drafts > 1 else "first attempt")
                print(f"\ndraft {drafts}    ({room})")
                for line in delta["cypher"].splitlines():
                    if line.strip():
                        print(f"   {line.strip()}")
            if node == "validate":
                problems = delta.get("errors") or []
                if not problems:
                    print("   nothing objected to it")
                    continue
                who = final.get("attempts", [{}])[-1].get("said_by", "the model")
                print(f"   {who} objects:")
                for problem in problems:
                    print(f"      - {problem}")
            if delta.get("rows") is not None:
                print(f"\nran draft {drafts}, because there were no corrections left")
                print(f"   {delta['rows']}")
            if node == "answer":
                print(f"\nanswer     {' '.join((delta.get('answer') or '').split())}")
    print(f"\n[ {drafts} draft{'s' if drafts != 1 else ''}   "
          f"{drafts * 2 + 1} model calls   "
          f"{len(final.get('schema') or ''):,} chars of schema ]")
    rows = final.get("rows") or []
    steps = [{"tool": f"draft {i}",
              "arguments": " ".join(a["cypher"].split()),
              "result": a["errors"] or "the validator found nothing"}
             for i, a in enumerate(final.get("attempts") or [], start=1)]
    return Answer(question, final.get("answer") or "",
                  context=final.get("cypher", ""), steps=steps,
                  path=final.get("steps") or [])


def text2cypher(question: str) -> Answer:
    """Ask the graph, and hand back every draft the pipeline went through.

    `steps` carries one entry per round of validation and the row that came out
    at the end, so `.show()` prints the repair loop rather than only its result.
    """
    final = build().invoke({"question": question, "steps": []})
    rows = final.get("rows") or []
    # One entry per draft, numbered, each carrying what the validator said about
    # *that* draft. Labelling them `generate` and `correct` was worse than no
    # label: the node that wrote draft 2 is `correct`, but the message printed
    # beside it came from the `validate` that read draft 2, so every line named
    # one node and showed another's output.
    steps = [{"tool": f"draft {i}",
              "arguments": " ".join(attempt["cypher"].split()),
              "result": attempt["errors"] or "the validator found nothing"}
             for i, attempt in enumerate(final.get("attempts") or [], start=1)]
    if rows:
        steps.append({"tool": "execute",
                      "arguments": " ".join(final.get("cypher", "").split()),
                      "result": rows})
    return Answer(question, final.get("answer") or "",
                  context=final.get("cypher", ""), steps=steps,
                  path=final.get("steps") or [])
