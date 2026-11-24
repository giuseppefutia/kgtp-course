"""What one session holds, counted for the drawing that shows it.

    from memory.shape import shape_of
    display(SVG(memory_picture(shape_of(memory_session, SESSION))))

The counting lives here because it is not the lesson. Thirty-six lines of
Cypher in a cell whose output is a picture reads as thirty-six lines of
plumbing, and a reader who skips them misses nothing: what they do is count
nodes so that `pictures.memory_picture` has numbers, and the picture takes its
data as arguments by the rule module 5's `pictures.py` sets.

The query itself stays in the notebook once, shown rather than used, because it
says something the module means: the library's memory is read with ordinary
Cypher, and nothing here needs its API to look at what it wrote.
"""

from __future__ import annotations

# Every match is OPTIONAL, and that is not caution. This query used to narrow
# the entities in a `CALL` subquery, and a `CALL` that returns no rows
# eliminates the row that called it: a conversation with messages and no
# entities -- which is what section 3 writes -- disappeared entirely, and its
# picture was drawn with a message count of zero. Found 12/11/2026 by reading
# the figure.
CONVERSATION = """
MATCH (c:Conversation {session_id: $session})
OPTIONAL MATCH (c)-[:HAS_MESSAGE]->(m:Message)
WITH c, count(m) AS messages
OPTIONAL MATCH (c)-[:HAS_MESSAGE]->(:Message)-[:MENTIONS]->(e:Entity)
WITH messages, e.name AS name, count(e) AS mentioned_by
ORDER BY mentioned_by DESC, name
WITH messages, collect({name: name, messages: mentioned_by})[0..5] AS entities
RETURN messages AS message_count, entities
"""

TRACES = """
MATCH (t:ReasoningTrace {session_id: $session})
OPTIONAL MATCH (t)-[*1..2]->(c:ToolCall)
RETURN count(DISTINCT t) AS traces, count(DISTINCT c) AS tool_calls
"""


def shape_of(memory_session, session_id: str) -> dict:
    """Count one session's messages, entities and traces.

    Both queries always run. A session can hold traces and no conversation --
    the reasoning section writes exactly that -- and returning early when the
    first query found nothing drew that section's picture empty.
    """
    traces = memory_session.run(TRACES, session=session_id).single()
    shape = {"session": session_id, "messages": 0, "entities": [],
             "traces": traces["traces"], "tool_calls": traces["tool_calls"]}
    rows = list(memory_session.run(CONVERSATION, session=session_id))
    if rows:
        shape["messages"] = rows[0]["message_count"]
        shape["entities"] = [e for e in rows[0]["entities"] if e["name"]]
    return shape
