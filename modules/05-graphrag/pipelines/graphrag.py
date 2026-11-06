"""GraphRAG: the same pages, each with its one-hop neighbourhood attached.

    from pipelines.graphrag import graphrag
    graphrag("Who is the vendor and which department signed?").show()

One node different from `rag.py` -- `attach_neighbours` instead of
`assemble_context` -- and that node is the entire claim of the approach. The
paper reports this is enough to match everything more elaborate; measured on
this graph on 1/9/2026 it sits mid-table, which is a result rather than a
refutation until the neighbours are attached at indexing time as the paper
does.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from pipelines.nodes import answer_from_context, attach_neighbours, retrieve_pages
from pipelines.state import Answer, InputState, RetrievalState


def build():
    graph = StateGraph(RetrievalState, input_schema=InputState)
    graph.add_node(retrieve_pages)
    graph.add_node(attach_neighbours)
    graph.add_node(answer_from_context)
    graph.add_edge(START, "retrieve_pages")
    graph.add_edge("retrieve_pages", "attach_neighbours")
    graph.add_edge("attach_neighbours", "answer_from_context")
    graph.add_edge("answer_from_context", END)
    return graph.compile()


def graphrag(session, question: str, k: int = 5, dense: bool = True) -> Answer:
    final = build().invoke({"session": session, "question": question,
                            "k": k, "dense": dense})
    return Answer(question, final["answer"],
                  sources=[{key: p[key] for key in ("purchase_order", "page", "score")}
                           for p in final["pages"]],
                  context=final["context"], path=final["steps"])
