"""`recall` as a ninth tool, so the agent decides when to read its memory.

    from memory.tool import RECALL, recall_handler
    turn = agent(session, question,
                 tools=select(session, [...]) + [RECALL],
                 system=build([...]) + RECALL_LINE,
                 extra_tools={"recall": recall_handler(memory_session, session_id)})

Everything before this section hands the agent its memory whether it wants it
or not: we choose when to read and which policy to read with, and the agent is
shown a longer system message without being told where the extra paragraph came
from. It cannot ask, and it cannot decline.

As a tool it can do both, and what the lesson measures is whether it does: on a
nine-turn conversation, a tool that is never called and a tool called on every
turn are both failures, and they are failures of the one sentence that
describes it.

The tool takes the **question**, not a name, and that is a correction with a
measurement behind it. Keyed on an entity name it was called once, on the right
turn, with `about="uniform supplier"` -- the words of the question. No entity is
called that: the one that matters is `J & D UNIFORMS, INC.`, so the lookup
matched nothing. The requirement was circular. To pass the name as it was
written the agent would need the memory it was asking for.

Measured 11/11/2026, and the rest of that run is why the empty answer matters as
much as the key: the handler replied "it was not discussed, so look it up
instead", the agent obeyed, searched the graph for a uniform supplier and
answered about a different company with its sources attached. A sentence written
to be helpful turned a miss into a confident wrong answer.

So the policy is the one that needs no name: narrow by cosine, then let the model
pick from what came back. Letting the agent choose the policy as well would
measure our prompt for choosing policies rather than its decision to look.
"""

from __future__ import annotations

RECALL = {"type": "function", "function": {
    "name": "recall",
    "description": ("What this conversation already established. Pass the "
                    "question you were asked, in full and unchanged -- pronouns "
                    "included. Use it whenever the question refers to something "
                    "it does not name."),
    "parameters": {"type": "object", "required": ["question"], "properties": {
        "question": {"type": "string"}}}}}

# The routing line, in the shape `catalogue.ROUTING` uses, so it can be appended
# to a prompt built from a selection.
RECALL_LINE = ("A question that refers to something without naming it -- \"it\", "
               "\"that supplier\", \"the one you mentioned\": recall first, "
               "passing the question itself.")

BY_COSINE = """
MATCH (:Conversation {session_id: $session})-[:HAS_MESSAGE]->(m:Message)
WHERE m.embedding IS NOT NULL
WITH m, vector.similarity.cosine(m.embedding, $vector) AS score
RETURN m.role AS role, m.content AS content, score
ORDER BY score DESC LIMIT $k
"""


def recall_handler(memory_session, session_id: str, embed, pick,
                   k: int = 6, log: list | None = None):
    """Build the handler `extra_tools` expects: one argument dict, one string back.

    `embed` turns the question into a vector and `pick` chooses among the rows
    it retrieves; both are passed in rather than imported so that the notebook
    can show what they are. Narrow then choose, which is the fifth policy of
    the section above with the agent in charge of when.

    Returns prose, because that is the contract every other tool here keeps:
    `run_tool` is typed to `str`.

    An empty result says it is empty and **does not suggest what to do next**.
    Saying "look it up instead" was measured on 11/11/2026 to turn a miss into a
    confident answer about the wrong company: the agent obeyed, searched, and
    found a different uniform supplier. A tool reports; it does not instruct.
    """
    def answer_for(question: str) -> str:
        if not question:
            return "recall needs the question. Pass it unchanged."
        rows = [dict(row) for row in memory_session.run(
            BY_COSINE, session=session_id, vector=embed(question), k=k)]
        if not rows:
            return "this conversation has nothing recorded yet."
        said, chosen = pick(rows, question)
        if chosen is None:
            return f"recall could not read its own selection step: {said[:80]!r}"
        if not chosen:
            return "nothing in this conversation bears on that question."
        return "\n".join(f"[{row['role']}] {' '.join(row['content'].split())}"
                         for row in chosen)

    def handler(args: dict) -> str:
        """One call, and both halves of it recorded.

        `log` keeps the argument the agent chose AND the text it got back. The
        question is the decision being measured -- the tool asks for it in full,
        pronouns included -- and the text is what the answer was built from.
        Logging only the question, as this did first, left a notebook that could
        report the tool had been called and nothing about what that did.
        """
        question = str(args.get("question") or "").strip()
        returned = answer_for(question)
        if log is not None:
            log.append({"question": question, "returned": returned})
        return returned
    return handler
