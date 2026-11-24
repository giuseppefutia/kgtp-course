"""The system message, assembled from the tools that were selected.

    from agent.prompt import build
    system = build(["search_titles", "about_contracts", "answer"])

Three parts are the same whatever the selection: the sentence that says what the
agent is for, the one that says there are two kinds of tool, and the one that
forbids giving up while an untried tool could still find the answer. None of
them names a tool, so none of them can promise one that is not there.

Between the second and the third go the routing lines of the selected tools,
from `catalogue.ROUTING`, in `catalogue.ORDER`. The instruction to finish with
`answer` arrives the same way, because `answer` is a selected tool like the
others and is last in that order.

`react.SYSTEM` is re-exported here as `ORIGINAL`. It is the prose module 5
tuned, and it is not what `build` produces even for all eight tools: module 5
names four tools in its second paragraph, which a selection cannot do, so that
paragraph is kept without the names. An experiment that needs module 5's agent
exactly has to use `ORIGINAL`, and `compare()` prints the two side by side so
the choice is made on the difference rather than on the assumption that there
is none.
"""

from __future__ import annotations

from pipelines.react import SYSTEM as ORIGINAL

from agent.catalogue import FULL, ROUTING, WHEN_ALL, check

ROLE = "You answer questions about City of Chicago contracts, using the tools."

# The taxonomy without the names. Module 5 puts four tools in this sentence;
# naming them here would reintroduce exactly the coupling `catalogue` exists to
# remove, and the routing lines below already say which tool is which kind.
FAMILIES = ("Two kinds of tools. Text tools find contracts by the words written "
            "about them. Graph tools know facts no document states: who the "
            "vendor really is, which department, and what else that vendor does.")

# Kept word for word from `react.SYSTEM`. It names no tool, and it is the rule
# that stops the agent handing the question back: module 5 measured the agent
# suggesting search terms to the person instead of trying them.
PERSIST = ("Never answer that nothing was found, and never suggest search terms "
           "to the person, while a tool you have not tried could still find it: "
           "try them yourself.")


def build(names=FULL) -> str:
    """Write the system message for this selection of tools.

    Goes through `check`, so an unknown name or a selection without `answer`
    raises here rather than producing a prompt that describes tools the model
    was not given.

    A tool whose pair is also selected is described by the pair's sentence
    instead of its own, from `catalogue.WHEN_ALL`: module 5 names some tools
    together, and the single-tool wording has to be general enough to stand
    without the other one.

    The same selection always produces the same string, which is what lets two
    runs differ by one tool and nothing else.
    """
    chosen = check(names)
    # A pair's sentence takes the place of its first member, so the order stays
    # the one `check` returned: a sentence moved to the front would be a second
    # difference between two runs that are meant to differ by one tool.
    pairs = {key[0]: key for key in WHEN_ALL if all(n in chosen for n in key)}
    covered = {name for key in pairs.values() for name in key[1:]}
    lines = [f"- {WHEN_ALL[pairs[name]] if name in pairs else ROUTING[name]}"
             for name in chosen if name not in covered]
    return "\n\n".join([ROLE, FAMILIES, "\n".join(lines), PERSIST])


def compare(names=FULL) -> str:
    """Put module 5's prose and this selection's prompt next to each other.

    For the one question this cannot answer on its own: whether a run with all
    eight tools here is the same experiment as a run in module 5. The strings
    differ, so the answer has to come from running both.
    """
    mine = build(names)
    return (f"--- react.SYSTEM, {len(ORIGINAL)} chars ---\n{ORIGINAL}\n"
            f"\n--- build({len(check(names))} tools), {len(mine)} chars ---\n{mine}")
