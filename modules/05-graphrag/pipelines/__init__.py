"""The four systems module 5 compares, as things you can call.

    from pipelines import rag, graphrag, text2cypher
    from pipelines.react import agent

Each returns an `Answer` carrying what was read, what the model was shown, and
which nodes ran. They existed only inside the benchmark before, which scores
them rather than showing them: you cannot learn what RAG is from code whose
output is a number.

The names above are resolved on first use, not on import. `pipelines.graph`
holds the primitives the pipelines, the agent's tools and the benchmark all
share, and it needs nothing but a Neo4j session -- importing it used to pull
LangGraph in through this file, which put it out of reach of exactly the callers
it exists for.
"""

_LAZY = {"rag": "pipelines.rag", "graphrag": "pipelines.graphrag",
         "text2cypher": "pipelines.text2cypher",
         "Answer": "pipelines.state"}

# `agent` is not here: it is `pipelines.react.agent` and it needs a session, so
# it does not share the shape of the three above. `pipelines/agent.py`, the
# two-tool one that wrote its own Cypher, was dropped on 5/11/2026.
__all__ = ["rag", "graphrag", "text2cypher", "Answer"]


def __getattr__(name):
    """Resolve one of them on first use, and bind the function over it.

    Importing `pipelines.rag` makes Python set `rag` on this package to the
    *module*, which then shadows this hook: `from pipelines import rag` handed
    back a module and `rag(...)` raised `TypeError: module object is not
    callable`. Measured 23/9/2026 by `tools/verify.py` on `lab.ipynb`. The
    rebinding below restores what `from pipelines.rag import rag` used to do.
    """
    if name in _LAZY:
        import importlib
        value = getattr(importlib.import_module(_LAZY[name]), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(__all__)
