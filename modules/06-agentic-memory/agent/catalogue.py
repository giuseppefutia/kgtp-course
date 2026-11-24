"""The eight tools of module 5 as data, so a session can hand the agent three.

    from agent.catalogue import ROUTING, select
    tools = select(session, ["search_titles", "about_contracts", "answer"])

Two things reach the model, and both have to describe the same tools: the
definitions the API reads, and the sentences in the system prompt that say when
to use each one. Module 5 keeps them apart -- `react.TOOLS` is the list,
`react.SYSTEM` is the prose -- so taking a tool out of the list leaves the
prompt ordering the model to call it.

Here each tool's sentence sits next to its name in `ROUTING`, and `prompt.py`
builds the instructions from the tools that were selected. Both halves are keyed
by the same name, so a selection cannot describe one set and declare another.

No tool is reimplemented. `react.run_tool` dispatches by name and
`react.run_tools` handles `answer` itself, so a shorter list means the model
never asks for the rest: the handlers stay module 5's.

What this does not give you: the assembled prompt is not module 5's prose word
for word, even on all eight tools. A run here is therefore not the same
experiment as a run in module 5, and nothing in the result will say so.
"""

from __future__ import annotations

from pipelines.react import TOOLS as REACT_TOOLS, tools_for

# One sentence per tool, cut out of `react.SYSTEM` and filed under the tool it
# is about.
#
# Two of module 5's sentences name two tools at once -- find_entity then
# contracts_of, and reformulate_query then search_titles. Each is filed under the
# tool that *starts* the sequence, so selecting the first without the second
# cannot promise a tool that was not selected.
ROUTING = {
    "search_descriptions":
        "A question about a kind of work: search_descriptions.",
    "search_titles":
        "Exact words that a purchase order title would use: search_titles.",
    "reformulate_query":
        "If search_descriptions finds little, try reformulate_query and pass "
        "its output to search_titles rather than the question.",
    "find_entity":
        "A question about a named company or department: find_entity first, "
        "then the tool that takes its identifier. Never write a name or an "
        "identifier you were not given. If find_entity returns several "
        "entities they are different, not spellings of one: say which you used.",
    # The sentence a tool gets when it is selected on its own carries the work
    # of the ones that are missing, and is weaker for it. Where module 5 names
    # two tools together, the pair is kept here and replaces both single
    # sentences when both tools are selected -- measured 11/11/2026: with the
    # generic wording the agent resolved all six departments one at a time,
    # seven find_entity and seven contracts_of against module 5's one each.
    "contracts_of":
        "All the contracts of an entity: contracts_of, with an identifier from "
        "find_entity. Two conditions on the same contracts -- a vendor AND a "
        "department -- is one contracts_of with `within`, never two lists "
        "compared by you.",
    "about_contracts":
        "Contracts found by topic, then something about their vendors or "
        "departments: pass the purchase orders to about_contracts.",
    "about_entity":
        "Which departments, types or years an entity works with: about_entity, "
        "which returns the complete set. about_contracts describes only the "
        "purchase orders you happen to be holding.",
    "answer":
        "Always finish by calling `answer`. Put the purchase orders of the "
        "contracts that answer the question in `purchase_orders`, copied from "
        "the tools; the list is written for you, so do not repeat it in "
        "`summary`. If nothing relevant was found, call answer with an empty "
        "list and say so -- do not list unrelated results.",
}

# Sentences that belong to a pair of tools rather than to one. Used only when
# every tool in the key is selected, and then instead of those tools' own lines.
WHEN_ALL = {
    ("find_entity", "contracts_of"):
        "A question about a named company or department: find_entity, then "
        "contracts_of. Never write a name or an identifier you were not given. "
        "Two conditions on the same contracts -- a vendor AND a department: "
        "resolve both with find_entity, then one contracts_of with `within`. "
        "Never compare lists. If find_entity returns several entities they are "
        "different, not spellings of one; say which you used.",
}

# The order module 5 declares the tools in, so that two selections of the same
# names produce the same string. A set would reorder them from run to run, and
# two prompts that differ only in the order of their sentences are still two
# prompts.
ORDER = [tool["function"]["name"] for tool in REACT_TOOLS]

FULL = tuple(ORDER)

# `react.next_step` ends a conversation on an answer or on the step budget. An
# agent without `answer` therefore cannot finish except by running out of steps,
# which in a lesson looks like the notebook hanging rather than like a result.
REQUIRED = ("answer",)


def select(session, names=FULL) -> list[dict]:
    """Give me the definitions of these tools, in a fixed order.

    The descriptions carry counts that `tools_for` reads from the graph and
    formats in. They are filtered here rather than copied, so that no count is
    frozen into this file.

    The session is only read, and only by `tools_for`.
    """
    chosen = set(check(names))
    return [tool for tool in tools_for(session)
            if tool["function"]["name"] in chosen]


def check(names) -> list[str]:
    """Reject a selection that would quietly become a different experiment.

    Two ways to lose a run without being told. A misspelled name would hand the
    agent one tool fewer than intended, and the missing tool's effect would be
    reported as the effect of whatever the run was testing. A selection without
    `answer` would hang instead of answering, for the reason `REQUIRED` gives.

    Both raise. Returns the names in `ORDER`, which is what makes two equal
    selections build one identical prompt.
    """
    chosen = list(names)
    unknown = [name for name in chosen if name not in ROUTING]
    if unknown:
        raise ValueError(
            f"not tools of module 5: {unknown}. Known: {', '.join(ORDER)}")
    missing = [name for name in REQUIRED if name not in chosen]
    if missing:
        raise ValueError(f"{missing} cannot be left out: an agent without it "
                         f"has no way to finish")
    return [name for name in ORDER if name in set(chosen)]
