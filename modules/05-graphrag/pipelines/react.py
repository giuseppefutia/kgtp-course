"""The agent: the same tools as the rest of the module, in an order it chooses.

    from pipelines.react import agent
    agent(session, "Which city departments has Bigane Paving Company worked for?")

    call_model --(tool calls?)--> run_tools --> call_model --> ... --> END

Reason and act, interleaved -- the model calls a tool, reads what came back, and
decides the next one. Two nodes and one conditional edge, like the other graphs
in this module: what makes this one an agent is not the wiring, it is that the
edge is decided by the model's reply and not by us.

Nothing here retrieves anything new: `search_descriptions` and `search_titles`
are `pipelines.search`, `find_entity`, `contracts_of`, `about_entity` and
`about_contracts` are `pipelines.graph`, and the notebook has already run all
six by hand. What changes is who decides the order, and when.

Three things in this file are not the agent and are the reason it works:

- **the judge** (decision 40) drops weak results inside the tool, before the
  model sees them. A threshold the caller is free to ignore is not a threshold.
- **`resolve_id`** (decision 39) accepts an identifier a tool issued in this
  conversation and refuses one the model invented.
- **`render_answer`** (decision 42) writes the final list from the graph. The
  model chooses the purchase orders; it does not retype them.

Conversations are not reproducible even at temperature 0 -- see decision 50 --
so a single run demonstrates nothing. `benchmark/cases.py` runs the agent cases
three times and needs two.
"""

from __future__ import annotations

import json
import re
from operator import add
from typing import Annotated, Any, Literal

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from pipelines.config import setting
from pipelines.schema import build as schema_text
from pipelines.models import NO_THINKING
from pipelines.graph import (
    CONTRACT_PATTERN,
    ENUMERATION,
    about_contracts,
    about_entity,
    contract_line,
    contracts_of,
    find_entity,
    render_about,
    render_contracts,
    render_entities,
    render_entity,
)
from pipelines.search import T1, T2, rewrite, vector

LLM_URL = setting("llm", "base_url")
LLM_KEY = setting("llm", "api_key")
LLM_MODEL = setting("llm", "model")


# A title is short and a description is not: the prose descriptions run to 409
# characters at the median, and cutting them to a title's length hides the half
# that tells one contract from another.
TITLE_CHARS = 110
DESCRIPTION_CHARS = 500

# The dense index over descriptions separates by score: measured 15/9/2026,
# questions with an answer among the 130 descriptions score 0.80-0.88, questions
# without one 0.71-0.76 (decision 34). Below this line nothing fitted.
#
# The line belongs with the embedding that produced it: see A30 for what happens
# when the questions are embedded differently.
RELEVANT = 0.78

TOOLS = [
    {"type": "function", "function": {
        "name": "search_descriptions",
        "description": ("Find contracts by what they are about, in plain language. "
                        "Searches the {descriptions:,} contracts whose documents describe "
                        "their scope. Returns purchase orders with their description."),
        "parameters": {"type": "object", "required": ["question"], "properties": {
            "question": {"type": "string"}, "k": {"type": "integer"}}}}},
    {"type": "function", "function": {
        "name": "search_titles",
        "description": ("Find contracts by exact words in their title, over all {titles:,} "
                        "contracts. Titles are terse and inconsistent, so pass the output "
                        "of reformulate_query rather than the question."),
        "parameters": {"type": "object", "required": ["query"], "properties": {
            "query": {"type": "string"}, "k": {"type": "integer"}}}}},
    {"type": "function", "function": {
        "name": "reformulate_query",
        "description": "Turn a question into the words a Chicago purchase order title would use.",
        "parameters": {"type": "object", "required": ["question"], "properties": {
            "question": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "find_entity",
        "description": ("Resolve the name of a company or a department to graph "
                        "identifiers. Give it a name written in the question, not text a "
                        "search returned. Not for subjects or kinds of work: for those, "
                        "search. Call this before contracts_of; never guess an identifier."),
        "parameters": {"type": "object", "required": ["name"], "properties": {
            "name": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "contracts_of",
        "description": ("All contracts of an entity. Takes an id from find_entity or "
                        "about_contracts. Pass `within`, another such id, to keep only the "
                        "contracts that belong to both -- a vendor's contracts with one "
                        "department. Use it "
                        "instead of comparing two lists yourself."),
        "parameters": {"type": "object", "required": ["id"], "properties": {
            "id": {"type": "string"}, "within": {"type": "string"},
            "limit": {"type": "integer"}}}}},
    {"type": "function", "function": {
        "name": "about_contracts",
        "description": ("For purchase orders returned by a search: who the vendor is, "
                        "which department awarded it, its contract type, and how many "
                        "contracts that vendor holds across which departments. Use it to "
                        "go from contracts found by text to facts only the graph has."),
        "parameters": {"type": "object", "required": ["purchase_orders"], "properties": {
            "purchase_orders": {"type": "array", "items": {"type": "string"}}}}}},
    {"type": "function", "function": {
        "name": "about_entity",
        "description": ("Everything an entity amounts to: how many contracts, ALL the "
                        "departments it has worked with, the contract types, the years. "
                        "Takes an id from find_entity. Use this, not about_contracts, when "
                        "the question asks which departments or types an entity works with: "
                        "it returns the complete set, where about_contracts describes the "
                        "purchase orders you happen to have sampled."),
        "parameters": {"type": "object", "required": ["id"], "properties": {
            "id": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "answer",
        "description": ("Finish. `summary` is a short answer in the person's language. When the "
                        "answer is a set of contracts, put their purchase orders in "
                        "`purchase_orders`: the list is written from the graph, so do not "
                        "repeat it in the summary. If nothing relevant was found, leave the "
                        "list empty and say so."),
        # `purchase_orders` stays optional. Requiring it was tried on 23/9/2026
        # and reverted the same day: it did not fix what it was aimed at -- that
        # turned out to be the accents in the question, see the register -- and
        # it made the agent finish sooner and worse, answering the Bigane
        # question with 2 of 4 departments instead of 4, three runs out of three,
        # by summarising the contracts it had sampled instead of reading the
        # vendor's reach line.
        "parameters": {"type": "object", "required": ["summary"], "properties": {
            "summary": {"type": "string"},
            "purchase_orders": {"type": "array", "items": {"type": "string"}}}}}},
]

SYSTEM = """You answer questions about City of Chicago contracts, using the tools.

Two kinds of tools. Text tools find contracts: search_descriptions by meaning,
search_titles by exact words. Graph tools know facts no document states: who the
vendor really is, which department, and what else that vendor does.

- A question about a named company or department: find_entity, then contracts_of.
  Never write a name or an identifier you were not given.
- Two conditions on the same contracts -- a vendor AND a department: resolve both
  with find_entity, then one contracts_of with `within`. Never compare lists.
- A question about a kind of work: search_descriptions; if it finds little, try
  reformulate_query then search_titles.
- A question that needs both -- contracts found by topic, then something about
  their vendors or departments: search first, then pass the purchase orders to
  about_contracts.

Never answer that nothing was found, and never suggest search terms to the
person, while a tool you have not tried could still find it: try them yourself.

If find_entity returns several entities they are different, not spellings of one;
say which you used.

Always finish by calling `answer`. Put the purchase orders of the contracts that
answer the question in `purchase_orders`, copied from the tools; the list is
written for you, so do not repeat it in `summary`. If nothing relevant was found,
call answer with an empty list and say so -- do not list unrelated results."""


# ------------------------------------------------------------------ the judge

# Relevance is judged inside the search tools, before the agent sees a result.
# Two failures on 16/9/2026 had the same root: the agent reasoned over whatever a
# search returned. It passed a teenagers' summer-jobs contract to the bridge in
# an answer about early childhood, and it listed unrelated identification systems
# after writing that none of its results matched. A rule in the prompt fixed the
# first and not the second; a result the agent never receives cannot be listed.
#
# One narrow question per search -- which of these are about the topic -- rather
# than "is the answer right". The judge is the same model as the agent, and a
# narrow yes-or-no is where it is least likely to share the agent's blind spot.
USE_JUDGE = True

JUDGE_PROMPT = """A search was run to help answer a question about City of Chicago
contracts. Decide which results are genuinely about what was searched for.

A result that only shares a word with the search does not count. A contract for
"water pumps" is not about "water quality testing"; a contract for "security
guard uniforms" is not about "security guard services".

Question: {question}
Searched for: {topic}

Results:
{results}

Answer with JSON and nothing else: {{"keep": [the numbers of the results to keep]}}"""


def judge(question: str, topic: str, rows: list[dict], text_of) -> tuple[list[dict], str]:
    """Keep the results that are about the topic; say how many were dropped.

    Fails open: if the judge cannot be reached or answers nonsense, every result
    is kept and the tool says so. Dropping everything on a judge error would turn
    an unavailable endpoint into "nothing exists", which is the one answer the
    agent must never give by mistake.
    """
    if not USE_JUDGE or not rows:
        return rows, ""
    from openai import OpenAI

    listing = "\n".join(f"{i}. {text_of(r)}" for i, r in enumerate(rows, 1))
    try:
        api = OpenAI(base_url=LLM_URL, api_key=LLM_KEY, timeout=60.0, max_retries=8)
        reply = api.chat.completions.create(
            model=LLM_MODEL, temperature=0, max_tokens=120, extra_body=NO_THINKING,
            messages=[{"role": "user", "content": JUDGE_PROMPT.format(
                question=question, topic=topic, results=listing)}])
        content = reply.choices[0].message.content or ""
        match = re.search(r"\{.*?\}", content, re.S)
        keep = set(json.loads(match.group(0)).get("keep", [])) if match else None
    except Exception:                               # noqa: BLE001 - fails open, and says so
        keep = None
    if keep is None:
        return rows, "\n(relevance check unavailable: results are unfiltered)"
    kept = [r for i, r in enumerate(rows, 1) if i in keep]
    dropped = len(rows) - len(kept)
    note = f"\n({dropped} of {len(rows)} results dropped as not about the search)" if dropped else ""
    return kept, note


def counts(session) -> dict:
    """Sizes quoted in the tool descriptions, read rather than written down.

    `descriptions` moves every time the summariser runs, and a number inside a
    prompt is invisible to `checks.check_numbers`.
    """
    row = session.run(
        "MATCH (c:Contract) WHERE c.name IS NOT NULL WITH count(c) AS titles "
        "MATCH (d:ContractDescription {tier: 'T1'}) "
        "RETURN titles, count(d) AS descriptions").single()
    return {"titles": row["titles"], "descriptions": row["descriptions"]}


def tools_for(session) -> list[dict]:
    sizes = counts(session)
    filled = json.loads(json.dumps(TOOLS))
    for tool in filled:
        tool["function"]["description"] = tool["function"]["description"].format(**sizes)
    return filled


RENDER = """
UNWIND range(0, size($pos) - 1) AS i
OPTIONAL MATCH (c:Contract {id: $pos[i]})
RETURN i, $pos[i] AS po, c.name AS name ORDER BY i
"""


def render_answer(session, summary: str, pos) -> str:
    """The final answer, with its list of contracts written from the graph.

    The model writes the summary and chooses the purchase orders; it does not
    retype the list. On 17/9/2026 the agent completed a three-step chain, was
    handed the right 22 contracts, and in three runs out of four answered with
    their titles instead of their numbers -- titles that repeat across contracts
    and quote other purchase orders inside them. A reader could identify 5 of the
    22. Neither labelling the identifier in the tool output nor a rule in the
    prompt stopped it. Copying identifiers into an argument list is something the
    agent does reliably; rewriting 22 lines of prose is not.

    An identifier the graph does not know is kept and marked, so an invented
    contract shows instead of disappearing.
    """
    if isinstance(pos, str):
        pos = re.findall(r"[A-Za-z]*\d+[A-Za-z]*", pos)
    pos = list(dict.fromkeys(str(p).strip() for p in (pos or []) if str(p).strip()))
    text = (summary or "").strip()
    if not pos:
        return text
    lines = []
    for row in session.run(RENDER, pos=pos):
        if row["name"] is None:
            lines.append(f"purchase_order={row['po']}  (NOT IN THE GRAPH)")
        else:
            lines.append(contract_line(row["po"], row["name"], 90))
    return f"{text}\n\n{len(pos)} contracts:\n" + "\n".join(lines)


def resolve_id(raw: str, issued: set[str] | None) -> str | None:
    """An identifier as the agent wrote it, matched to one a tool actually issued.

    Prefixed and well-formed, it stands. Unprefixed, it is accepted only if it is
    the tail of exactly one identifier issued earlier in this conversation. On
    17/9/2026, after the prompt changed to introduce `answer`, the agent started
    writing `L3430` for `vendor:L3430` and `CHICAGO DEPARTMENT OF PUBLIC HEALTH`
    for its department id, and once wrote `L1000`, which it had never been given.
    Three strict rejections later it gave up. Completing an identifier the tool
    itself handed over is not guessing; accepting one it never issued would be.
    """
    raw = (raw or "").strip()
    kind, _, value = raw.partition(":")
    if kind in CONTRACT_PATTERN and value:
        return raw
    if not issued or not raw:
        return None
    matches = [i for i in issued if i.partition(":")[2].lower() == raw.lower()]
    return matches[0] if len(matches) == 1 else None


def run_tool(session, name: str, args: dict, chooser=None, question: str = "",
             issued: set[str] | None = None) -> str:

    try:
        if name == "search_descriptions":
            topic = args.get("question", "")
            rows = [dict(r) for r in session.run(
                T1, v=vector(topic), n=20, k=int(args.get("k") or 5))]
            best = max((r["score"] for r in rows), default=0.0)
            text = lambda r: " ".join(str(r["name"]).split())[:DESCRIPTION_CHARS]
            if best >= RELEVANT:
                rows, note = judge(question or topic, topic, rows, text)
            else:
                note = ""
                rows = []
            found = "\n".join(f"{r['po']}: {text(r)}" for r in rows)
            if found:
                return found + note
            # Said by the tool, not only by the prompt, and only when nothing
            # fitted -- by score, or by the judge. On 16/9/2026 the agent found
            # nothing here for `disinfestazione` and answered "try pest control",
            # handing the search back; an unconditional version of this hint then
            # made it abandon good early-childhood results.
            sizes = counts(session)
            return (f"no description matches the search (best score {best:.2f}).{note}\n"
                    f"These descriptions cover only {sizes['descriptions']:,} of "
                    f"{sizes['titles']:,} contracts: call reformulate_query and then "
                    f"search_titles before concluding that nothing exists.")

        if name == "search_titles":
            topic = args.get("query", "")
            rows = [dict(r) for r in session.run(T2, q=topic, k=int(args.get("k") or 8))]
            text = lambda r: " ".join(str(r["name"]).split())[:TITLE_CHARS]
            # Full-text scores do not compare across queries, so there is no
            # measured line here as there is for descriptions: the judge is the
            # only filter.
            rows, note = judge(question or topic, topic, rows, text)
            found = "\n".join(contract_line(r["po"], r["name"], TITLE_CHARS) for r in rows)
            return (found + note) if found else f"no title matches the search.{note}"

        if name == "reformulate_query":
            return rewrite(args.get("question", ""))

        if name == "find_entity":
            term = args.get("name", "")
            rows = find_entity(session, term)
            if not rows:
                return f"no entity with contracts matches '{term}'"
            if chooser and len(rows) > 1:
                rows = [chooser(term, rows)]
            if issued is not None:
                issued.update(r["id"] for r in rows)
            return render_entities(rows)

        if name == "contracts_of":
            given = [str(args.get("id", "")), str(args.get("within") or "")]
            ids = [resolve_id(given[0], issued), resolve_id(given[1], issued) if given[1] else ""]
            bad = [g for g, i in zip(given, ids) if g and not i]
            if bad or not ids[0]:
                known = sorted(issued)[:8] if issued else []
                hint = (f" Identifiers you have been given: {', '.join(known)}." if known else
                        " Identifiers look like vendor:L7644 or department:DEPT OF WATER.")
                return (f"not an identifier from find_entity or about_contracts: "
                        f"{bad or given[:1]}.{hint}")
            rows = contracts_of(session, ids[0], ids[1] or None)
            return render_contracts(rows, ids[0], ids[1] or None,
                                    int(args.get("limit") or 50))

        if name == "about_entity":
            entity = resolve_id(str(args.get("id", "")), issued)
            if not entity:
                return (f"not an identifier from find_entity: {args.get('id')!r}. "
                        f"Call find_entity first.")
            return render_entity(about_entity(session, entity))

        if name == "about_contracts":
            pos = args.get("purchase_orders") or []
            if isinstance(pos, str):
                # Tolerated: the model sometimes sends "58936, 58950" as one string.
                pos = re.findall(r"[A-Za-z]*\d+[A-Za-z]*", pos)
            pos = [str(p).strip() for p in pos if str(p).strip()][:20]
            if not pos:
                return "give purchase orders from a search"
            return render_about(about_contracts(session, pos), issued)
    except Exception as error:      # noqa: BLE001 - reported to the agent, which can try again
        # The endpoints are hosted runtimes behind a tunnel and dropped three
        # times on 15/9/2026. A tool that raises ends the conversation; a tool
        # that reports lets the agent do something else.
        return f"the tool failed: {type(error).__name__}. Try another tool or query."
    return f"no such tool: {name}"



# ------------------------------------------------------------------ the graph


class ReactState(TypedDict, total=False):
    """What the two nodes hand each other, and what the caller gets back out.

    Three of these are the reason the agent needs a state at all, and not just a
    function called twice:

    - `issued` is every identifier the tools have handed over so far, and it is
      what `resolve_id` checks a model-written identifier against. Reset it
      between steps and a correct `contracts_of` becomes a rejection.
    - `nudged` is spent once per conversation, not once per step.
    - `sent` and `trace` accumulate, so they carry an `add` reducer: a node
      returns the characters and the entries of its own step, and LangGraph adds
      them to what came before. A node that returned the whole list instead
      would have to read it first, and the two would drift.

    `session`, `api` and `chooser` are here because a node takes one argument:
    whatever the caller passed to `agent` has to travel in the state.
    """
    question: str
    session: Any            # the caller's Neo4j session
    api: Any                # the OpenAI client, built once per conversation
    tools: list[dict]
    chooser: Any
    echo: bool
    steps: int              # model calls allowed
    step: int               # model calls made
    messages: list[dict]
    issued: set[str]
    nudged: bool
    answer: str
    trace: Annotated[list[dict], add]
    sent: Annotated[int, add]


def call_model(state: ReactState) -> ReactState:
    """Ask the model what to do next, with the tools in front of it.

    `sent` counts what the step cost to ask, so it is counted before the reply
    arrives: the price of a step is the conversation so far plus the tool
    declarations, which is what grows, and the reply is at most 900 tokens.
    """
    messages = state["messages"]
    cost = (sum(len(str(m.get("content") or "")) for m in messages)
            + len(json.dumps(state["tools"])))
    reply = state["api"].chat.completions.create(
        model=LLM_MODEL, messages=messages, tools=state["tools"],
        temperature=0, max_tokens=900, extra_body=NO_THINKING)
    message = reply.choices[0].message
    calls = message.tool_calls or []
    messages = messages + [
        {"role": "assistant", "content": message.content or "",
         "tool_calls": [{"id": c.id, "type": "function", "function": {
             "name": c.function.name,
             "arguments": c.function.arguments}} for c in calls]}]
    done = {"messages": messages, "step": state["step"] + 1, "sent": cost}
    if calls:
        return done

    if not state["nudged"]:
        # Finishing in prose loses the list: the model rewrites contracts by
        # title, and titles repeat. On 17/9/2026 one run in three did this after
        # the right 22 contracts were already in hand. The graph asks once for
        # `answer`, rather than the prompt asking always -- the prompt already
        # said so, and the model finished in prose anyway.
        done["nudged"] = True
        done["messages"] = messages + [{"role": "user", "content": (
            "Finish by calling the `answer` tool: a short summary, and the purchase "
            "orders of the contracts that answer the question in `purchase_orders`.")}]
        return done

    # The served model sometimes leaves its own tool-call marker in the text.
    text = (message.content or "").replace("<tool_call>", "").strip()
    if state["echo"]:
        print(f"\n  step {state['step'] + 1}: answers\n   "
              + (text or "(empty)").replace("\n", "\n   "))
    done["answer"] = text
    return done


def run_tools(state: ReactState) -> ReactState:
    """Run every tool the model asked for, and hand each result back.

    `answer` is not a tool like the others: it ends the conversation, so
    anything the model batched after it does not run.
    """
    step, echo = state["step"], state["echo"]
    messages = list(state["messages"])
    entries: list[dict] = []
    for call in messages[-1]["tool_calls"]:
        name = call["function"]["name"]
        try:
            args = json.loads(call["function"]["arguments"] or "{}")
        except json.JSONDecodeError:
            args = {}
        if name == "answer":
            text = render_answer(state["session"], args.get("summary", ""),
                                 args.get("purchase_orders"))
            entries.append({"step": step, "tool": "answer", "args": args,
                            "result": text})
            if echo:
                print(f"\n  step {step}: answer\n   " + text.replace("\n", "\n   "))
            return {"messages": messages, "trace": entries, "answer": text}
        result = run_tool(state["session"], name, args, state["chooser"],
                          state["question"], state["issued"])
        entries.append({"step": step, "tool": name, "args": args, "result": result})
        if echo:
            print(f"\n  step {step}: {name}({json.dumps(args)[:110]})")
            print("     -> " + result.replace("\n", "\n        ")[:600])
        messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
    # `issued` is updated in place by the tools; returned so that the node says
    # what it touched.
    return {"messages": messages, "trace": entries, "issued": state["issued"]}


def next_step(state: ReactState) -> Literal["call_model", "run_tools", "__end__"]:
    """Where the conversation goes next: a tool, the model again, or out.

    The one decision in this file that we do not make, and the only one: both
    edges out of the two nodes go through here, so there is a single place where
    the conversation can end.

    The budget is not a safety net, it is part of the measurement: an agent that
    keeps asking is failing, and without the cap that failure looks like a hang
    instead of a result. `benchmark/cases.py` has a case that ends here -- the
    agent calls `search_titles` until the budget is gone -- and the case exists
    to show when it stops.
    """
    if state.get("answer") is not None:
        return END
    if state["messages"][-1].get("tool_calls"):
        return "run_tools"
    return "call_model" if state["step"] < state["steps"] else END


def build():
    graph = StateGraph(ReactState)
    graph.add_node(call_model)
    graph.add_node(run_tools)
    # One router, three narrow declarations. Wiring `next_step` on all three
    # edges without a map was correct at run time and a lie on paper:
    # LangGraph reads the possible destinations off the router's return type, so
    # every node was declared to reach every node -- nine edges, of which the
    # conversation can only take six. `run_tools -> run_tools` cannot happen at
    # all (after a tool result the last message has no `tool_calls`), and it was
    # drawn in the picture of the four architectures anyway.
    #
    # The maps below say what each node can actually reach. `START` is a plain
    # edge because the entry is not a decision: the first turn is the question,
    # it carries no tool calls, and `step` is below `steps`.
    graph.add_edge(START, "call_model")
    graph.add_conditional_edges("call_model", next_step,
                               {"run_tools": "run_tools",
                                "call_model": "call_model", END: END})
    graph.add_conditional_edges("run_tools", next_step,
                               {"call_model": "call_model", END: END})
    return graph.compile()


def agent(session, question: str, steps: int = 12, chooser=None,
             echo: bool = True, schema: bool = False) -> dict:
    """Run the agent; return what was called and what was answered.

    Returned as well as printed so `benchmark.cases` can check which tools were
    used and in what order, not only the final prose.
    """
    from openai import OpenAI

    # Eight retries for the same reason `chat_model` has eight: the proxy allows
    # ten requests a minute and one agent run makes more. Three was enough while
    # the model was thinking -- the thinking paced the calls. With thinking off
    # the lesson runs in four minutes instead of twenty-five, and on 5/11/2026
    # it started failing here with a 429 that reads to a student as a broken
    # notebook.
    api = OpenAI(base_url=LLM_URL, api_key=LLM_KEY, timeout=180.0, max_retries=8)
    final = build().invoke(
        {"question": question, "session": session, "api": api,
         "tools": tools_for(session), "chooser": chooser, "echo": echo,
         "steps": steps, "step": 0, "nudged": False, "issued": set(),
         "messages": [{"role": "system", "content": SYSTEM + (
             # The whole measured schema appended to the instructions, to answer
             # one question and no other: does the agent choose better when it
             # can see the shape of the graph? It cannot write Cypher -- the
             # tools do not let it -- so this is seventeen thousand characters
             # of context it has no way to act on directly. `pipelines/compare.py`
             # has what it changed.
             "\n\nThe graph you are querying has this shape.\n\n"
             + schema_text(session) if schema else "")},
                      {"role": "user", "content": question}]},
        # Counted in nodes, not in steps: a conversation of `steps` model calls
        # runs each of the two nodes up to `steps` times. LangGraph's own limit
        # defaults to 25, which on 5/11/2026 raised GraphRecursionError after
        # the 13th model call of the 16 `benchmark/cases.py` allows -- an
        # exception where the battery expects the answer "stopped without one".
        # `next_step` is the cap that matters; this one stays out of its way.
        {"recursion_limit": steps * 2 + 2})
    answer = final.get("answer")
    if answer is None and echo:
        print(f"\n  stopped after {steps} steps without an answer")
    if echo:
        # The same line `Answer.cost()` prints for RAG and GraphRAG, so the
        # three can be compared without re-reading each. `sent` is the one
        # number that separates an agent from a pipeline: it grows with every
        # turn, because the whole conversation goes back up on the next call.
        print(f"\n[ {final.get('step') or 0} steps   "
              f"{len(final.get('trace') or [])} tool calls   "
              f"{final.get('sent') or 0:,} chars sent ]")
    return {"trace": final.get("trace") or [], "answer": answer,
            "calls": final.get("step") or 0, "sent": final.get("sent") or 0}
