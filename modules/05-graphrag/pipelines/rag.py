"""RAG: retrieve pages, assemble them, answer from them. The graph is not read.

    from pipelines.rag import rag
    rag("What is the late-delivery penalty on this contract?").show()

The baseline everything else is measured against, and the one that cannot
aggregate: "which contracts carry a penalty above X" is not a question
retrieval answers, because the answer is not written on any one page.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from pipelines.nodes import answer_from_context, assemble_context, retrieve_pages
from pipelines.state import Answer, InputState, RetrievalState


def build():
    graph = StateGraph(RetrievalState, input_schema=InputState)
    graph.add_node(retrieve_pages)
    graph.add_node(assemble_context)
    graph.add_node(answer_from_context)
    graph.add_edge(START, "retrieve_pages")
    graph.add_edge("retrieve_pages", "assemble_context")
    graph.add_edge("assemble_context", "answer_from_context")
    graph.add_edge("answer_from_context", END)
    return graph.compile()


def rag(session, question: str, k: int = 5, dense: bool = True) -> Answer:
    final = build().invoke({"session": session, "question": question,
                            "k": k, "dense": dense})
    return Answer(question, final["answer"],
                  sources=[{key: p[key] for key in ("purchase_order", "page", "score")}
                           for p in final["pages"]],
                  context=final["context"], path=final["steps"])
