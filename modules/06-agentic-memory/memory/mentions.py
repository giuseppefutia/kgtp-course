"""Which entities a turn touched, taken from the agent's tool calls.

    from memory.mentions import mentions_of
    await store.short_term.add_message(session, "assistant", answer,
                                       extraction_mode="explicit",
                                       explicit_mentions=mentions_of(turn, graph))

The memory store can extract entities from a message by running a model over
its text. It does not need to here, because the agent already said what it
looked at: `about_contracts({"purchase_orders": ["T25581"]})` names the
contract in a structured argument, not in prose.

So the mentions come from `turn["trace"]`, and the vendor behind each purchase
order comes from one query against the domain graph. Nothing is parsed out of a
tool's printed output: a result string is formatting, and formatting changes
without anyone noticing that a memory stopped being linked.

What this buys over text extraction is exactness. Measured 11/11/2026 on a
nine-turn conversation: by cosine, the message that answers
"which departments has that uniform supplier worked with" ranks **third**,
behind a question about office furniture, because cosine matches the shape of a
question and that message shares none of its words. The entity it names appears
in exactly one message.

A turn is linked to its **subject**, not to its answer. Asked which contracts
are for office furniture the agent answers with thirty purchase orders, and a
turn that answers with thirty contracts is not about any one of them: linking
all thirty would bury the one turn that is about a single thing under the ones
that are about a topic. So purchase orders become mentions only when the turn
names at most `SUBJECT_LIMIT` of them, and the name the user asked about --
whatever went to `find_entity` -- always does.

Measured 11/11/2026, and the reason the limit is not only editorial: the store
embeds every entity it links, and the same flag governs the message's embedding,
so entity vectors cannot be switched off on their own. Writing one assistant
message cost 1.7s with 2 mentions, 6.0s with 9, and 23.1s with 43. A nine-turn
conversation linking everything a search touched spends minutes of a lesson on
vectors none of its queries read.

What it costs: a turn that reached its answer by text search alone names no
subject, so it gets no mentions and this retrieval cannot find it. That is a
silent gap -- the message is stored, the edges are not -- and the lesson shows
the empty counts rather than claiming coverage.
"""

from __future__ import annotations

from dataclasses import dataclass

# The purchase orders a tool was asked about or answered with. `find_entity`
# takes a name and `contracts_of` an identifier, so neither contributes a
# purchase order; both are read for their own subject below.
PO_ARGS = ("purchase_orders",)

# Above this many purchase orders in one turn, the turn is about a topic rather
# than about a contract, and its purchase orders are its answer rather than its
# subject. Three because two is the common shape -- a contract and the one it
# replaced -- and four has not been seen on a question about a named order.
SUBJECT_LIMIT = 3

VENDORS = """
MATCH (c:Contract) WHERE c.id IN $purchase_orders
MATCH (c)<-[:INCLUDED_IN_CONTRACT]-(:ContractRecord)-[:RECORDED_VENDOR]->(v:Organization)
RETURN c.id AS purchase_order, collect(DISTINCT v.name) AS vendors
"""


@dataclass(frozen=True)
class Ref:
    """One entity a message mentions, by name and POLE+O type.

    The store's identity precedence is `id` > `name + type` > `name`, and a
    name on its own neither creates a node nor resolves: it links the one
    unmerged entity carrying that surface form, or warns and skips. So the type
    travels with the name, always.
    """
    name: str
    type: str


def mentions_of(turn: dict, graph) -> list[Ref]:
    """What this turn is about: the name it was asked for, and few enough orders.

    Deduplicated and ordered, so that the same turn produces the same list
    twice -- two runs of a notebook that differ in the order of their MENTIONS
    edges are two runs nobody can compare.
    """
    steps = turn.get("trace", [])
    purchase_orders = {
        value
        for step in steps
        for key in PO_ARGS
        for value in (step.get("args") or {}).get(key) or []
    }
    asked_for = {
        (step.get("args") or {}).get("name")
        for step in steps
        if step.get("tool") == "find_entity"
    } - {None, ""}

    refs = [Ref(name, "ORGANIZATION") for name in sorted(asked_for)]
    if not purchase_orders or len(purchase_orders) > SUBJECT_LIMIT:
        return refs

    refs += [Ref(po, "OBJECT") for po in sorted(purchase_orders)]
    vendors: set[str] = set()
    for row in graph.run(VENDORS, purchase_orders=sorted(purchase_orders)):
        vendors.update(row["vendors"])
    refs += [Ref(name, "ORGANIZATION") for name in sorted(vendors)
             if name not in asked_for]
    return refs
