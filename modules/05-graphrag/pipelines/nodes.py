"""The nodes of the RAG and GraphRAG graphs.

One function per node, each taking the state and returning the part of it that
changed. Kept out of the graph definitions for the same reason `rag/tools.py`
is kept out of `rag/workflow.py`: the graph should be readable as a shape, and
a shape is unreadable when every box carries its own body.
"""

from __future__ import annotations

from pipelines.models import chat_model, invoke
from pipelines.prompt import ANSWER_PROMPT
from pipelines.retrievers import neighbours, retrieve
from pipelines.state import RetrievalState


def retrieve_pages(state: RetrievalState) -> RetrievalState:
    """Find the pages this question retrieves."""
    pages = retrieve(state["session"], state["question"], k=state.get("k", 5),
                     dense=state.get("dense", True))
    return {"pages": pages, "steps": ["retrieve"]}


def _revision(page: dict) -> str:
    """Which filing this page is from, when the id says so.

    A purchase order is filed once per revision and each filing has its own page
    2, with different text on it. Without this, two different pages print as
    `PO 214209 p2` twice and read as one page retrieved twice.
    """
    document = str(page.get("document") or "")
    return f", {document.rsplit('_', 1)[-1]}" if "_r" in document else ""


def assemble_context(state: RetrievalState) -> RetrievalState:
    """Turn the retrieved pages into the text the model will see."""
    context = "\n\n".join(
        f"[purchase order {p['purchase_order']}, page {p['page']}"
        f"{_revision(p)}]\n{p['text'][:1500]}"
        for p in state["pages"])
    return {"context": context, "steps": ["assemble"]}


def attach_neighbours(state: RetrievalState) -> RetrievalState:
    """The same pages, each preceded by what the graph knows about its contract.

    This one node is the whole difference between the RAG and the GraphRAG in
    this module. A page says what the contract commits to; the graph says who
    signed it, for whom, and how many times it was revised -- and neither source
    contains the other's half.

    The neighbours are attached here, at query time. The paper attaches them
    when the index is built, which is not the same thing: until that is redone
    its way the comparison between the two is not like for like, and saying so
    is part of the result.
    """
    blocks, said = [], {}
    for page in state["pages"]:
        po = page["purchase_order"]
        # Once per contract, not once per page. Six pages of one purchase order
        # used to mean six identical queries and the same `graph:` line six
        # times in the context -- measured 5/11/2026 on the intraosseous
        # question, where all six retrieved pages belong to order 214209. The
        # model gains nothing from a fact repeated, and the repetition is paid
        # for in every call. `docs/DECISIONS.md` entry 2: subgraph
        # deduplication is one of the things the paper this module follows is
        # for.
        if po not in said:
            n = neighbours(state["session"], po)
            said[po] = (
                f"vendors: {', '.join(n.get('vendors') or []) or 'none recorded'}; "
                f"departments: {', '.join(n.get('departments') or []) or 'none recorded'}; "
                f"revisions: {n.get('revisions', 0)}")
        facts = f"graph: {said[po]}\n"
        blocks.append(
            f"[purchase order {po}, page {page['page']}{_revision(page)}]\n"
            f"{facts}{page['text'][:1500]}")
    return {"context": "\n\n".join(blocks), "steps": ["attach_neighbours"]}


def answer_from_context(state: RetrievalState) -> RetrievalState:
    """Answer the question from the assembled context, and only from it."""
    reply = invoke(chat_model(max_tokens=ANSWER_PROMPT.get("max_tokens", 400)), [
        ("system", ANSWER_PROMPT["system"]),
        ("user", ANSWER_PROMPT["user"].format(context=state["context"],
                                              question=state["question"])),
    ])
    return {"answer": reply.content, "steps": ["answer"]}
