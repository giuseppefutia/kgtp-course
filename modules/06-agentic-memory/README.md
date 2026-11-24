# Module 6 — Agentic memory

The agent of module 5 does not know what it just said. This module gives it a
memory, in a graph of its own, and measures what that buys.

- Live session: 1.5h
- Prerequisites: module 5's agent; the graph of module 4.

## The problem

`agent(session, question)` builds a list of messages, calls the model until it
has an answer, and returns. The list dies with the call. Ask a second question
that says *"that supplier"* and nothing in the system knows who that is.

A memory is a record of what happened, kept somewhere that outlives the call.
The module starts from the smallest one that works — a Python dictionary with
three fields — and ends with a store the agent can query on its own.

## What the module builds, in order

1. **The record.** What was asked, what came back, which tools got there. Three
   fields, built by hand, carried into the next turn as text.
2. **The same record, in a graph.** `neo4j-agent-memory` writes it as
   `Conversation`, `Message`, and a linked list of `NEXT_MESSAGE` — and the
   notebook reads it back with ordinary Cypher rather than through the library,
   because two of those relationships are not in the documentation.
3. **Choosing what to carry.** Nine turns do not fit in a prompt, so four
   retrieval policies compete on the same conversation: the last six messages,
   the closest one by cosine, the closest six, and the messages that mention
   the entity by name.
4. **Letting the agent choose.** `recall` as a ninth tool, so the agent decides
   whether to look at all.
5. **Remembering the path, not the answer.** The trace of tool calls a turn
   made, stored, retrieved by similarity to a new question, and handed back as
   a procedure.

## What you will see fail

**The policy that carries the most characters answers with the wrong company.**
Nine turns in, asked which departments *that uniform supplier* worked with, the
last six messages carry 5,767 characters, none of which mention it — the turn
that does is nine back. The agent then does the only thing it can: it searches
the graph for a uniform supplier and finds a different one, real, with its own
contracts and departments and sources attached. Nothing in the answer says the
contract you asked about was never found.

Three more, each measured rather than described: a tool that reports an empty
result *and suggests what to do instead* turns a miss into a confident wrong
answer; a turn that spends its step budget is stored and never offered again;
and every tool in the run succeeds 100% of the time, including the one that
kept not finding what was asked for.

## What you need

**The graph of module 4, read-only, plus a second database for the memory.**
The memory is a graph of its own — different nodes, different questions, no
query joins the two. They meet in the model's context, in Python, over two
connections.

Create it once, in Neo4j Browser or cypher-shell, against the `system`
database:

```cypher
CREATE DATABASE kgtpmemory IF NOT EXISTS
```

`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` and `NEO4J_DATABASE` are read from
the environment as in modules 4 and 5. The memory database is read the same
way, from `NEO4J_MEMORY_DATABASE`, and falls back to `kgtpmemory`.

**The notebook empties that database before it writes.** A store appends, so a
second run would otherwise show every earlier run at once. The cell prints the
name it is about to empty — read it before you run it, and never point
`NEO4J_MEMORY_DATABASE` at the graph of module 4.

One package more than module 5:

```
pip install -e ".[notebooks,graphrag,agent-memory]"
```

And the same **two models being served**, one that answers and one that embeds.
The embedding model matters more here than anywhere else in the course: the
memory store fixes the width of its vector indexes the first time anything
connects to it. Connect once without passing the course embedder and the store
is built at the library's default 1536, and every later connection is refused
with `EmbeddingDimensionMismatchError`. The only way out is a new database. The
notebook passes the embedder on its first connection and says so where it does.

The module is one notebook, `lesson.ipynb`. `memory/` holds the pieces it
builds — the embedder, the entity mentions, the counting behind the figures,
and `recall` as a tool; `agent/` holds module 5's eight tools as data, so a
ninth can be added to them; `pictures.py` draws every figure from the results
of the cell above it.
