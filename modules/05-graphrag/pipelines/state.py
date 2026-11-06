"""The state each graph carries, and what the caller gets back.

Two shapes on purpose. Inside a graph the state is a `TypedDict`, because that
is what LangGraph merges between nodes and what makes a node's contract
readable. Outside, the caller gets an `Answer`, because an answer alone cannot
be argued with: `sources` says what was read, `context` says what the model was
shown, `steps` says how it got there. Most failures in this module are
invisible in the answer and obvious in one of the other three.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from operator import add
from typing import Annotated, Any

from typing_extensions import NotRequired, TypedDict


class InputState(TypedDict):
    """What a caller hands a retrieval graph.

    Everything the caller passes has to be declared here. LangGraph filters
    `invoke()` against the input schema and drops whatever is not in it,
    without an error. Until 2/11/2026 this carried `question` alone, so
    `rag(question, k=10, dense=False)` ran with k=5 and dense=True and said
    nothing -- the arguments were accepted, and gone by the first node.
    """
    question: str
    session: NotRequired[Any]       # the caller's Neo4j session
    k: NotRequired[int]
    dense: NotRequired[bool]


class RetrievalState(TypedDict, total=False):
    """Shared by the RAG and the GraphRAG graphs: they differ by one node."""
    question: str
    session: Any           # the caller's Neo4j session, carried to the retriever
    # `k` and `dense` live here as well as in InputState, and both are needed:
    # LangGraph keeps only the keys the *state* schema declares, so until
    # 2/11/2026 `nodes.retrieve_pages` read `state.get("k", 5)` out of a state
    # that never carried k. Both arguments were silently the default.
    k: int
    dense: bool
    pages: list[dict]
    context: str
    answer: str
    steps: Annotated[list[str], add]


class AgentState(TypedDict, total=False):
    question: str
    messages: list[dict]
    calls: list[dict]
    answer: str
    steps: Annotated[list[str], add]


@dataclass
class Answer:
    question: str
    answer: str
    sources: list[dict] = field(default_factory=list)
    context: str = ""
    steps: list[dict] = field(default_factory=list)
    path: list[str] = field(default_factory=list)

    def cost(self) -> str:
        """One line, the same shape in all four systems: what it took.

        Added 5/11/2026. The four print in three different shapes -- which is
        right, because a retrieval, a repair loop and a conversation are not the
        same event -- and that left nothing a reader could compare without
        re-reading each. The sizes are the comparable part, and until this line
        existed they appeared only in the measurement at the end.

        Characters, not tokens: a token count would need the server's tokeniser
        and would be a guess here. The ratios are what the line is for.
        """
        bits = [f"{len(self.path)} nodes" if self.path else ""]
        if self.steps:
            bits.append(f"{len(self.steps)} tool calls")
        if self.context:
            bits.append(f"{len(self.context):,} chars of context")
        return "   ".join(b for b in bits if b)

    def show(self, chars: int = 600) -> None:
        """Print the answer, then everything it was built from.

        Printed, not rendered. A version on 5/11/2026 turned the answer into
        HTML so the model's Markdown would come out as bold and bullets instead
        of asterisks; it was rejected on sight. Plain text is what the rest of
        the notebook is, and an answer that looks like a web page looks like
        something other than what the model returned.
        """
        print(f"Q: {self.question}\n\nA: {self.answer}\n")
        line = self.cost()
        if line:
            print(f"[ {line} ]\n")
        if self.path:
            print(f"nodes: {' -> '.join(self.path)}\n")
        for step in self.steps:
            print(f"   {step['tool']}({str(step['arguments'])[:90]})")
            print(f"      -> {str(step['result'])[:130]}")
        if self.steps:
            print()
        top = max((s["score"] for s in self.sources), default=0) or 1
        for source in self.sources:
            bar = "#" * max(1, round(18 * source["score"] / top))
            # The revision, because the page number does not identify a page:
            # each filing of an order has its own page 2.
            document = str(source.get("document") or "")
            revision = document.rsplit("_", 1)[-1] if "_r" in document else ""
            print(f"   PO {source['purchase_order']:>7} p{source['page']:<4}"
                  f" {revision:<3} {source['score']:>6}  {bar}")
        if self.context and chars:
            print(f"\n-- context sent to the model, {len(self.context)} chars --")
            print(self.context[:chars] + ("..." if len(self.context) > chars else ""))
