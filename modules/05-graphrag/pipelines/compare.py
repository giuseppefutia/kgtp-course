"""The four systems on the same five questions, and which band each one covers.

This is the measurement the module is for. `docs/DECISIONS.md` entry 2 puts the
module on the territory of *Is GraphRAG Needed?* (AWS/Cisco, GEM 2026) -- which
approach works when -- and this is that question asked of the four systems in
this notebook, on this graph, with this model.

Five questions, each chosen because it **separates** the four, not because it is
hard. The bands are the point: a question the documents hold and the graph does
not, a count only the graph has, one that needs both, one whose words are not
the document's words, and one that names two things at once.

Scoring is recorded by hand and not computed here. A first version matched the
expected string against the answer, and four verdicts in twenty-four were wrong
the same way: the phrase appeared **inside a refusal**. *"I couldn't find a
contract that addresses liquidated damages"* contains `liquidated damages`. A
scorer that cannot tell an answer from an apology measures nothing, and the
cheap fix -- a list of refusal phrases -- only moves the guess.
"""

from __future__ import annotations

import io
import contextlib
import time

# (band, question) -- the band is what the row is here to show.
GRID = [
    ("a count only the graph has",
     "How many departments award more than 1000 contracts?"),
    ("who holds it today",
     "Who is the supplier of purchase order 82547 today?"),
    ("text and graph in one question",
     "Which departments work with the vendor that holds purchase order 82547 today?"),
    ("the words you have, not the trade's",
     "What happens if the contractor finishes late?"),
    ("two named things at once",
     "Which contracts does Erie Neighborhood House have with the "
     "Department of Public Health?"),
]

SYSTEMS = ["RAG", "GraphRAG", "Text2Cypher", "Agent"]


def run_grid(session, questions=None) -> dict:
    """Twenty answers, about five minutes. Returns them; it does not score them.

    Live, so the lesson can show that the recorded verdicts below are a
    recording and not a claim about what will happen tonight.
    """
    from pipelines.graphrag import graphrag
    from pipelines.rag import rag
    from pipelines.react import agent
    from pipelines.text2cypher import text2cypher

    def quiet(f, *a, **k):
        with contextlib.redirect_stdout(io.StringIO()):
            return f(*a, **k)

    how = {
        "RAG": lambda q: rag(session, q, k=5, dense=False).answer,
        "GraphRAG": lambda q: graphrag(session, q, k=5, dense=False).answer,
        "Text2Cypher": lambda q: quiet(text2cypher, q).answer,
        "Agent": lambda q: quiet(agent, session, q, echo=False)["answer"] or "",
    }
    out = {}
    for band, question in (questions or GRID):
        out[band] = {}
        for name in SYSTEMS:
            started = time.time()
            try:
                answer = how[name](question) or ""
            except Exception as error:      # noqa: BLE001 - the endpoint, not the code
                answer = f"({type(error).__name__})"
            out[band][name] = {"seconds": round(time.time() - started, 1),
                               "answer": " ".join(answer.split())[:300]}
    return out


# Three runs of `run_grid`, 5/11/2026, Qwen3.8-27B, read one answer at a time.
# `+` answered it, `-` said it could not, `!` answered it wrongly, `x` is the
# proxy's rate limit and not a verdict on anything.
RECORDED = {
    "a count only the graph has":        {"RAG": "---", "GraphRAG": "---",
                                          "Text2Cypher": "+++", "Agent": "!!!"},
    "who holds it today":                {"RAG": "+++", "GraphRAG": "+++",
                                          "Text2Cypher": "+++", "Agent": "+x+"},
    "text and graph in one question":    {"RAG": "---", "GraphRAG": "+++",
                                          "Text2Cypher": "---", "Agent": "+++"},
    "the words you have, not the trade's": {"RAG": "---", "GraphRAG": "---",
                                          "Text2Cypher": "--+", "Agent": "--x"},
    "two named things at once":          {"RAG": "---", "GraphRAG": "---",
                                          "Text2Cypher": "---", "Agent": "+++"},
}

# What each system actually said, where the mark alone would mislead.
SAID = {
    ("a count only the graph has", "Agent"):
        "11 award more than 1,000 contracts -- and it says why it is 11: "
        "'I can only count the departments that appear in the graph'. "
        "The right answer is 21.",
    ("text and graph in one question", "GraphRAG"):
        "the Chicago Fire Department -- right, and for a narrower reason than "
        "the question asked. It names the department **of that purchase "
        "order**; the question asked which departments work with **the "
        "vendor**. The two coincide because this vendor has one. The agent "
        "answers the question that was asked: 'it works with only one "
        "department'.",
    ("the words you have, not the trade's", "Text2Cypher"):
        "on the third run only: 'the project typically undergoes a Time "
        "Extension'. It crossed the vocabulary gap through the graph -- "
        "TIME EXTENSION is the commonest reason for a modification, 1,052 of "
        "them -- and not through the contract text, which is where the three "
        "retrieval systems were looking.",
}


# Median seconds of the three runs, not the mean: a call the proxy rate-limited
# is retried up to eight times, and one of those turns a 13-second answer into a
# 60-second one without the system having done anything differently.
SECONDS = {
    "a count only the graph has": {
        "RAG": 3.4,
        "GraphRAG": 6.1,
        "Text2Cypher": 55.8,
        "Agent": 70.8
    },
    "who holds it today": {
        "RAG": 5.5,
        "GraphRAG": 4.7,
        "Text2Cypher": 111.3,
        "Agent": 34.0
    },
    "text and graph in one question": {
        "RAG": 6.7,
        "GraphRAG": 4.8,
        "Text2Cypher": 55.3,
        "Agent": 14.6
    },
    "the words you have, not the trade's": {
        "RAG": 1.6,
        "GraphRAG": 2.9,
        "Text2Cypher": 112.7,
        "Agent": 77.6
    },
    "two named things at once": {
        "RAG": 24.6,
        "GraphRAG": 3.6,
        "Text2Cypher": 71.9,
        "Agent": 20.2
    }
}


def table(runs: dict, seconds: dict | None = None) -> str:
    """One block per question, one line per system.

    A grid with the systems as columns fitted in ninety characters and read as a
    wall: five rows of twelve marks, and the question it took to produce them on
    a line of its own underneath. Turned on its side the question is the
    heading, which is what a reader looks for first, and each system gets a line
    it does not share.
    """
    asked = dict(GRID)
    out = []
    for band, marks in runs.items():
        out.append(asked.get(band, band))
        out.append(f"   tests: {band}")
        for system in SYSTEMS:
            run = " ".join(marks[system])
            cost = f"{seconds[band][system]:>7.1f}s" if seconds else ""
            out.append(f"   {system:<14}{run:<8}{cost}")
        out.append("")
    out.append("+ answered      - said it could not      ! answered wrongly"
               "      x rate limit")
    out.append("three marks, one per run. seconds are the median, measured "
               "back to back against")
    out.append("an endpoint capped at ten requests a minute -- ceilings, not "
               "costs. What holds is")
    out.append("the ordering: reading pages is seconds, writing a query is a "
               "minute.")
    return "\n".join(out)


# ------------------------------------------------ the agent, given the schema

# Does the agent choose better when it can see the shape of the graph?
# `agent(..., schema=True)` appends the whole measured schema -- seventeen
# thousand characters -- to its instructions. Five questions, three runs each,
# 5/11/2026. Medians; one of the thirty calls died on the proxy's rate limit
# and is excluded.
#
# It never did better on any of the five. On `a count only the graph has` the
# answer became **unstable** (8, 10, 8) where without the schema it was the same
# wrong number three times. On `the words you have` it spent the whole
# twelve-step budget, all three runs, and returned **nothing at all** -- against
# seven steps and an honest refusal without it.
#
# The mechanism is not mysterious. The tools do not let the agent write Cypher,
# so the schema is context it cannot act on: it can only change which tool it
# reaches for, and it changed that for the worse.
SCHEMA_TRIAL = {
    "a count only the graph has": {
        "without": {
            "steps": 4,
            "sent": 23980,
            "seconds": 31.4,
            "stable": True,
            "runs": 3
        },
        "with": {
            "steps": 6,
            "sent": 143934,
            "seconds": 53.8,
            "stable": False,
            "runs": 3
        }
    },
    "who holds it today": {
        "without": {
            "steps": 2,
            "sent": 10227,
            "seconds": 4.5,
            "stable": True,
            "runs": 3
        },
        "with": {
            "steps": 2,
            "sent": 45315,
            "seconds": 24.4,
            "stable": True,
            "runs": 3
        }
    },
    "text and graph in one question": {
        "without": {
            "steps": 3,
            "sent": 15657,
            "seconds": 6.8,
            "stable": True,
            "runs": 3
        },
        "with": {
            "steps": 3,
            "sent": 68289,
            "seconds": 24.6,
            "stable": True,
            "runs": 3
        }
    },
    "the words you have, not the trade's": {
        "with": {
            "steps": 12,
            "sent": 278995,
            "seconds": 121.3,
            "stable": True,
            "runs": 3
        },
        "without": {
            "steps": 7,
            "sent": 38127,
            "seconds": 70.4,
            "stable": True,
            "runs": 2
        }
    },
    "two named things at once": {
        "without": {
            "steps": 3,
            "sent": 17766,
            "seconds": 36.2,
            "stable": True,
            "runs": 3
        },
        "with": {
            "steps": 3,
            "sent": 70608,
            "seconds": 32.3,
            "stable": True,
            "runs": 3
        }
    }
}


def schema_table(trial: dict | None = None) -> str:
    """Steps, characters sent and seconds, with the schema and without."""
    trial = trial or SCHEMA_TRIAL
    width = max(len(b) for b in trial)
    head = (f"{'':{width}}  {'':>8}  {'steps':>6}  {'chars sent':>11}"
            f"  {'seconds':>8}  {'same answer':>12}")
    lines = [head, "-" * len(head)]
    for band, both in trial.items():
        for how in ("without", "with"):
            v = both[how]
            name = band if how == "without" else ""
            lines.append(f"{name:{width}}  {how:>8}  {v['steps']:>6}  "
                         f"{v['sent']:>11,}  {v['seconds']:>8.1f}  "
                         f"{('yes' if v['stable'] else 'NO'):>12}")
    lines.append("")
    lines.append("medians of three runs; 'same answer' is whether the three "
                 "agreed with each other")
    return "\n".join(lines)
