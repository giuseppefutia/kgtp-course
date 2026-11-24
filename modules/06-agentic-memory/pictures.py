"""The drawings of module 6, one function per picture.

    from pictures import recall_picture, memory_picture

Out of the notebook for the reason module 5 measures in its own `pictures.py`:
its four drawings were 15,116 characters against 10,147 for everything the
notebook actually ran, and the longest cells in a module about retrieval were
all coordinates.

`checks`, `xml`, `fit` and `frame` are imported from there rather than copied.
They carry six validations and a day apiece on which a reader saw something the
checks did not, and a second copy of that would drift away from the first.

**Every function takes its data as arguments.** Neither opens a session: a
picture can only show what the cell above it produced.

Conventions are module 4's, carried through module 5:

- **orange is what is not there.** Here that is the one message a recall policy
  needed and did not return, drawn in its lane as an empty orange outline.
- `#CFD8DC` for messages, `#607D8B` with white text for entities, `#0091EA` for
  titles and numbers, a dashed outline and no fill for what is not data.
- `xml()` on every string from the data -- a vendor is called
  `A & M AMUSEMENT INC`, and one unescaped ampersand stops the whole image.
- `fit()` on every label, or `MAYORS OFFICE OF WORKFORCE DEVELOPMENT` draws
  over its neighbour.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

# Module 5's helpers, loaded by path under a name of their own. Both files are
# called `pictures.py`, so `from pictures import checks` inside this one resolves
# to this one: the import succeeds, finds nothing, and reports a circular import
# that looks like a problem with the package rather than with the filename.
_FIVE = Path(__file__).resolve().parent.parent / "05-graphrag" / "pictures.py"
_spec = importlib.util.spec_from_file_location("pictures_module5", _FIVE)
_five = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_five)

checks, fit, frame, xml = _five.checks, _five.fit, _five.frame, _five.xml

# The arrowhead definition, from the same file. `frame()` emits the svg tag and
# the white ground and nothing else, so a drawing that writes
# `marker-end="url(#tip)"` without this draws lines with no heads -- and the
# checks report "arrowheads clear of each other", because they count the
# attribute rather than the marker it points at.
ARROW = _five.ARROW

MESSAGE = "#CFD8DC"
ENTITY = "#607D8B"
ACCENT = "#0091EA"
MISSING = "#FF6D00"
INK = "#263238"

__all__ = ["checks", "recall_picture", "memory_picture"]


def recall_picture(subjects: list[str], policies: dict, *,
                   useful: int, width: float | None = None) -> str:
    """One cell per message, one row per recall policy.

    `subjects` is a short label per turn, in order -- "uniforms", "snow" -- and
    every turn is drawn as **two** cells, the question above and the answer
    below, because that is what a turn is and what the policies return.

    Two earlier versions of this figure were wrong in the same way. The first
    numbered the columns 1 to 9, so it reported that recency had returned
    7, 8 and 9 -- true, and unreadable, since the point is what those three
    were about. The second kept one cell per turn while the policies count
    messages, so the row labelled "last 6" lit three cells and the figure
    contradicted its own label.

    `policies` maps a label to `{"picked": [message indices, zero-based],
    "named": "the company it answered"}`. `useful` is the turn whose answer the
    question needed, counted from one.

    Drawn because the table it accompanies gives a count of rows and cannot
    show the shape of the choice: recency takes a run at the end, cosine
    scatters across turns, the last two take one cell.
    """
    turns = len(subjects)
    left, top, gap, lane, cell = 196.0, 124.0, 8.0, 40.0, 16.0
    box = max(62.0, max(len(s) for s in subjects) * 10 * 0.55 + 10)
    w = left + turns * (box + gap) + 180
    h = top + 30 + len(policies) * lane + 36
    parts = [frame(w, h, width), ARROW]

    parts.append(f'<text x="24" y="30" fill="{ACCENT}" font-size="15" '
                 f'font-weight="600">which messages each policy brought '
                 f'back</text>')
    parts.append(f'<text x="24" y="50" font-size="11" fill="{INK}" '
                 f'fill-opacity="0.75">two cells per turn: the question above, '
                 f'the answer below</text>')

    for n, subject in enumerate(subjects):
        x = left + n * (box + gap)
        mark = n + 1 == useful
        parts.append(
            f'<rect x="{x}" y="{top - 36}" width="{box}" height="26" rx="4" '
            f'fill="{ACCENT if mark else MESSAGE}" stroke="{INK}" '
            f'stroke-opacity="0.3"/>')
        parts.append(
            f'<text x="{x + box / 2}" y="{top - 18}" text-anchor="middle" '
            f'font-size="10" font-weight="{"700" if mark else "400"}" '
            f'fill="{"#FFFFFF" if mark else INK}">{xml(subject)}</text>')
    parts.append(f'<text x="24" y="{top - 18}" font-size="11" fill="{INK}" '
                 f'fill-opacity="0.8">the conversation</text>')
    parts.append(
        f'<text x="{left + box / 2}" y="{top - 46}" text-anchor="middle" '
        f'font-size="10" fill="{ACCENT}">the answer is in here</text>')

    useful_answer = (useful - 1) * 2 + 1          # the assistant message of it
    y = top + 8
    for label, policy in policies.items():
        picked = set(policy.get("picked") or ())
        parts.append(f'<text x="24" y="{y + 20}" font-size="11" fill="{INK}">'
                     f'{xml(label)}</text>')
        for n in range(turns):
            x = left + n * (box + gap)
            for half, index in ((0, n * 2), (1, n * 2 + 1)):
                top_y = y + 2 + half * (cell + 2)
                if index in picked:
                    fill = ACCENT if index == useful_answer else MESSAGE
                    parts.append(
                        f'<rect x="{x}" y="{top_y}" width="{box}" '
                        f'height="{cell}" rx="2" fill="{fill}" stroke="{INK}" '
                        f'stroke-opacity="0.25"/>')
                elif index == useful_answer:
                    parts.append(
                        f'<rect x="{x}" y="{top_y}" width="{box}" '
                        f'height="{cell}" rx="2" fill="none" '
                        f'stroke="{MISSING}" stroke-width="2"/>')
                else:
                    parts.append(
                        f'<rect x="{x}" y="{top_y}" width="{box}" '
                        f'height="{cell}" rx="2" fill="none" stroke="{INK}" '
                        f'stroke-opacity="0.12"/>')
        named = policy.get("named") or ""
        right = named.upper().startswith("J & D")
        parts.append(
            f'<text x="{left + turns * (box + gap) + 8}" y="{y + 22}" '
            f'font-size="11" font-weight="{"600" if right else "400"}" '
            f'fill="{ACCENT if right else MISSING}">'
            f'{xml(named)}  ({len(picked)} msg)</text>')
        y += lane

    parts.append(
        f'<text x="24" y="{h - 12}" font-size="10" fill="{INK}" '
        f'fill-opacity="0.75">filled = brought back · blue = the answer the '
        f'question needs · orange outline = needed and missed</text>')
    return "\n".join(parts) + "\n</svg>"


def memory_picture(shape: dict, *, width: float | None = None) -> str:
    """The memory graph as it stands, drawn from a count of what is in it.

    `shape` is what the count query above it returns:

        {"session": str, "messages": int,
         "entities": [{"name": str, "messages": int}, ...],
         "traces": int, "tool_calls": int}

    Anything absent is simply not drawn, so the same function serves the three
    places this notebook touches the store: after the messages are written, and
    again when entities and traces have joined them. Drawn each time rather than
    once at the end, because what the picture shows is the store **growing** --
    and a single figure at the end would show only where it stopped.

    The one structural claim the module makes is in the entity column: an entity
    named by several messages is one node those messages share, and that is
    where a log of turns becomes a graph. The count on each box is how many
    messages point at it.
    """
    entities = (shape.get("entities") or [])[:5]
    traces = shape.get("traces") or 0
    rows = max(len(entities), 1)
    left, top, step = 40.0, 76.0, 54.0
    w = 780.0
    h = top + rows * step + (56 if traces else 0) + 34
    parts = [frame(w, h, width), ARROW]
    session = str(shape.get("session") or "")
    parts.append(f'<text x="24" y="30" fill="{ACCENT}" font-size="15" '
                 f'font-weight="600">the memory graph, as it stands</text>')
    parts.append(f'<text x="24" y="50" font-size="11" fill="{INK}" '
                 f'fill-opacity="0.75">{xml(fit(session, 420, 11))}</text>')

    mx, ex = left + 215, left + 430
    middle = top + (rows - 1) * step / 2

    # The conversation, dashed: a container rather than data.
    parts.append(f'<rect x="{left}" y="{middle - 17}" width="135" height="36" rx="4" '
                 f'fill="none" stroke="{INK}" stroke-dasharray="4 3"/>')
    parts.append(f'<text x="{left + 67}" y="{middle - 2}" text-anchor="middle" '
                 f'font-size="11" fill="{INK}">:Conversation</text>')
    parts.append(f'<text x="{left + 67}" y="{middle + 12}" text-anchor="middle" '
                 f'font-size="11" fill="{ACCENT}" font-weight="600">'
                 f'{shape.get("messages") or 0} :Message</text>')

    if not entities:
        parts.append(f'<rect x="{mx}" y="{middle - 16}" width="200" height="34" rx="4" '
                     f'fill="none" stroke="{MISSING}" stroke-width="2"/>')
        parts.append(f'<text x="{mx + 100}" y="{middle + 5}" text-anchor="middle" '
                     f'font-size="11" fill="{MISSING}">no :Entity yet</text>')
        parts.append(f'<line x1="{left + 135}" y1="{middle}" x2="{mx}" y2="{middle}" '
                     f'stroke="{INK}" stroke-opacity="0.4" marker-end="url(#tip)"/>')
    for n, entity in enumerate(entities):
        y = top + n * step
        count = entity.get("messages") or 0
        parts.append(f'<rect x="{mx}" y="{y - 14}" width="120" height="30" rx="4" '
                     f'fill="{MESSAGE}" stroke="{INK}" stroke-opacity="0.35"/>')
        parts.append(f'<text x="{mx + 60}" y="{y + 5}" text-anchor="middle" '
                     f'font-size="11" fill="{INK}">'
                     f'{count} :Message{"s" if count != 1 else ""}</text>')
        parts.append(f'<line x1="{left + 135}" y1="{middle}" x2="{mx}" y2="{y}" '
                     f'stroke="{INK}" stroke-opacity="0.35" marker-end="url(#tip)"/>')
        parts.append(f'<rect x="{ex}" y="{y - 14}" width="300" height="30" rx="4" '
                     f'fill="{ENTITY}"/>')
        parts.append(f'<text x="{ex + 10}" y="{y + 5}" font-size="11" fill="#FFFFFF">'
                     f'{xml(fit(str(entity.get("name") or ""), 285, 11))}</text>')
        parts.append(f'<line x1="{mx + 120}" y1="{y}" x2="{ex}" y2="{y}" '
                     f'stroke="{INK}" stroke-opacity="0.35" marker-end="url(#tip)"/>')
    if entities:
        parts.append(f'<text class="edge" x="{(mx + 120 + ex) / 2}" y="{top - 14}" '
                     f'text-anchor="middle" font-size="10" fill="{INK}" '
                     f'fill-opacity="0.8">:MENTIONS</text>')
    parts.append(f'<text class="edge" x="{(left + 135 + mx) / 2}" y="{middle - 24}" '
                 f'text-anchor="middle" font-size="10" fill="{INK}" '
                 f'fill-opacity="0.8">:HAS_MESSAGE</text>')

    if traces:
        y = top + rows * step + 14
        parts.append(f'<rect x="{mx}" y="{y - 14}" width="120" height="30" rx="4" '
                     f'fill="{MESSAGE}" stroke="{INK}" stroke-opacity="0.35"/>')
        parts.append(f'<text x="{mx + 60}" y="{y + 5}" text-anchor="middle" '
                     f'font-size="11" fill="{INK}">{traces} :ReasoningTrace</text>')
        parts.append(f'<rect x="{ex}" y="{y - 14}" width="300" height="30" rx="4" '
                     f'fill="{MESSAGE}" stroke="{INK}" stroke-opacity="0.35"/>')
        parts.append(f'<text x="{ex + 10}" y="{y + 5}" font-size="11" fill="{INK}">'
                     f'{shape.get("tool_calls") or 0} :ToolCall, the path each turn took'
                     f'</text>')
        parts.append(f'<line x1="{mx + 120}" y1="{y}" x2="{ex}" y2="{y}" '
                     f'stroke="{INK}" stroke-opacity="0.35" marker-end="url(#tip)"/>')

    parts.append(f'<text x="24" y="{h - 10}" font-size="11" fill="{INK}" '
                 f'fill-opacity="0.75">an entity named by several messages is one node '
                 f'they share; orange is what the store does not hold yet</text>')
    return "\n".join(parts) + "\n</svg>"


def procedure_picture(paths: dict, *, skipped: str, carried: str,
                      width: float | None = None) -> str:
    """Two runs of one question, as the sequence of calls each one made.

    `paths` maps a label to the list of tool names that run called, in order.
    `skipped` is the call the shorter run did not make, and `carried` is the
    value that travelled from one call's result into the next one's argument --
    which is the thing the template knows and the longer run had to go and ask
    for.

    Drawn because this is the one claim in the module that is a sequence. The
    table it accompanies gives two step counts, and two numbers cannot show
    that the extra step asked for something the first call had already
    returned.
    """
    labels = list(paths)
    longest = max(len(steps) for steps in paths.values())
    box, gap, left, top, lane = 158.0, 26.0, 196.0, 92.0, 104.0
    w = left + longest * (box + gap) + 20
    h = top + len(labels) * lane + 46
    parts = [frame(w, h, width), ARROW]
    parts.append(f'<text x="24" y="32" fill="{ACCENT}" font-size="15" '
                 f'font-weight="600">the same question, {len(labels)} runs</text>')
    parts.append(f'<text x="24" y="54" font-size="11" fill="{INK}" '
                 f'fill-opacity="0.75">the shorter run does not stop to ask for '
                 f'something the first call already returned</text>')

    for row, label in enumerate(labels):
        y = top + row * lane
        steps = paths[label]
        parts.append(f'<text x="24" y="{y + 4}" font-size="12" fill="{INK}" '
                     f'font-weight="600">{xml(fit(label, 160, 12))}</text>')
        parts.append(f'<text x="24" y="{y + 22}" font-size="11" fill="{INK}" '
                     f'fill-opacity="0.7">{len(steps)} tool calls</text>')
        for n, step in enumerate(steps):
            x = left + n * (box + gap)
            out = step == skipped
            parts.append(
                f'<rect x="{x}" y="{y - 14}" width="{box}" height="34" rx="4" '
                f'fill="{"none" if out else MESSAGE}" '
                f'stroke="{MISSING if out else INK}" '
                f'stroke-width="{2 if out else 1}" '
                f'stroke-opacity="{1 if out else 0.35}"/>')
            parts.append(
                f'<text x="{x + box / 2}" y="{y + 7}" text-anchor="middle" '
                f'font-size="11" fill="{MISSING if out else INK}">'
                f'{xml(fit(step, box - 14, 11))}</text>')
            if n:
                parts.append(f'<line x1="{x - gap}" y1="{y + 3}" x2="{x}" '
                             f'y2="{y + 3}" stroke="{INK}" stroke-opacity="0.4" '
                             f'marker-end="url(#tip)"/>')

        # The value that travels, drawn under the run that had to go and ask for
        # it and over the one that did not.
        if skipped in steps:
            a = left + steps.index(skipped) * (box + gap)
            parts.append(f'<text x="{a + box / 2}" y="{y + 42}" '
                         f'text-anchor="middle" font-size="10" fill="{MISSING}">'
                         f'asks for what step 1 returned</text>')
        else:
            parts.append(
                f'<path d="M {left + box / 2} {y + 24} Q {left + box} {y + 48} '
                f'{left + box + gap + box / 2} {y + 24}" fill="none" '
                f'stroke="{ACCENT}" stroke-opacity="0.8" marker-end="url(#tip)"/>')
            parts.append(f'<text class="edge" x="{left + box + gap / 2}" '
                         f'y="{y + 62}" text-anchor="middle" font-size="10" '
                         f'fill="{ACCENT}">{xml(fit(carried, 300, 10))}</text>')
    return "\n".join(parts) + "\n</svg>"


# The three families the eight tools fall into, and what each family reaches.
# Taken from the sentence `react.SYSTEM` opens with -- "Two kinds of tools. Text
# tools find contracts... Graph tools know facts no document states" -- plus the
# two that belong to neither: one rewrites a question, one ends the run.
FAMILIES = (
    ("text", "find contracts by what is written",
     ("search_descriptions", "search_titles")),
    ("graph", "facts no document states",
     ("find_entity", "contracts_of", "about_contracts", "about_entity")),
    ("neither", "one rewrites a question, one ends the run",
     ("reformulate_query", "answer")),
)


def agent_picture(tool_names: list[str], *, example: dict | None = None,
                  width: float | None = None) -> str:
    """The agent as it stands before this module touches it: a loop, and a reach.

    `tool_names` is what the model is shown -- `[t["function"]["name"] for t in
    tools_for(session)]` -- and the names are checked against the families
    below rather than trusted: a tool added to module 5 and not to this list
    would otherwise be drawn as if it did not exist.

    Two halves, because the starting point is two facts and students arriving
    from module 5 have seen each half separately. On the left the loop:
    `call_model` and `run_tools`, with the conditional edge decided by the model
    rather than by the previous node's result. On the right everything that edge
    can reach, grouped by what it touches.

    `example` is one real turn -- `{"question": str, "calls": [tool names]}`,
    taken from `agent(...)["trace"]` -- drawn underneath as the sequence that
    actually ran. Without it the two halves say what the agent *could* do; with
    it the strip says what it did, which is the part that differs per question.

    What the picture is here to make obvious is what is **not** in it: nothing
    on either side survives the call. `messages` grows inside the loop and is
    gone when it returns, and no box on the right writes anything down.

    Nothing is shortened. Every label is sized to its longest member instead,
    because an ellipsis in a figure hides exactly the end of the name that
    distinguishes `about_contracts` from `about_entity`.
    """
    left, top = 36.0, 96.0
    node_w, node_h = 150.0, 46.0
    col = left + node_w + 136
    rows = sum(1 + len(names) for _, _, names in FAMILIES)
    # Wide enough for the longest tool name and the longest family note, at the
    # 0.55 em per character `fit` assumes -- so that nothing has to be cut.
    longest_name = max(len(n) for _, _, names in FAMILIES for n in names)
    longest_note = max(len(note) for _, note, _ in FAMILIES)
    reach_w = max(longest_name * 10 * 0.55 + 20, 60 + longest_note * 10 * 0.55 + 16)
    w = col + reach_w + 24
    h = max(top + rows * 27 + 30, top + 210)
    strip = 0.0
    if example:
        strip = 92.0
        h += strip
    parts = [frame(w, h, width), ARROW]

    parts.append(f'<text x="24" y="32" fill="{ACCENT}" font-size="15" '
                 f'font-weight="600">the agent module 5 built</text>')
    parts.append(f'<text x="24" y="52" font-size="11" fill="{INK}" '
                 f'fill-opacity="0.75">a loop, and everything it can reach — and '
                 f'nothing here outlives one call</text>')

    # The loop, left. START and END dashed: they are not data.
    model_y, tools_y = top + 10, top + 110
    for y, label, lower in ((model_y, "call_model", "chooses a tool, or answers"),
                            (tools_y, "run_tools", "runs what it chose")):
        parts.append(f'<rect x="{left}" y="{y}" width="{node_w}" height="{node_h}" '
                     f'rx="5" fill="{MESSAGE}" stroke="{INK}" stroke-opacity="0.4"/>')
        parts.append(f'<text x="{left + node_w / 2}" y="{y + 20}" '
                     f'text-anchor="middle" font-size="12" font-weight="600" '
                     f'fill="{INK}">{label}</text>')
        parts.append(f'<text x="{left + node_w / 2}" y="{y + 36}" '
                     f'text-anchor="middle" font-size="10" fill="{INK}" '
                     f'fill-opacity="0.75">{xml(lower)}</text>')

    mid = left + node_w / 2
    parts.append(f'<line x1="{mid - 34}" y1="{model_y + node_h}" x2="{mid - 34}" '
                 f'y2="{tools_y}" stroke="{INK}" stroke-opacity="0.45" '
                 f'marker-end="url(#tip)"/>')
    parts.append(f'<line x1="{mid + 34}" y1="{tools_y}" x2="{mid + 34}" '
                 f'y2="{model_y + node_h}" stroke="{INK}" stroke-opacity="0.45" '
                 f'marker-end="url(#tip)"/>')
    parts.append(f'<text class="edge" x="{mid}" y="{model_y + node_h + 34}" '
                 f'text-anchor="middle" font-size="10" fill="{INK}" '
                 f'fill-opacity="0.8">messages</text>')

    parts.append(f'<rect x="{left + 18}" y="{model_y - 42}" width="{node_w - 36}" '
                 f'height="26" rx="4" fill="none" stroke="{INK}" '
                 f'stroke-dasharray="4 3"/>')
    parts.append(f'<text x="{mid}" y="{model_y - 24}" text-anchor="middle" '
                 f'font-size="10" fill="{INK}">a question</text>')
    parts.append(f'<line x1="{mid}" y1="{model_y - 16}" x2="{mid}" y2="{model_y}" '
                 f'stroke="{INK}" stroke-opacity="0.45" marker-end="url(#tip)"/>')

    parts.append(f'<rect x="{left + 18}" y="{tools_y + node_h + 18}" '
                 f'width="{node_w - 36}" height="26" rx="4" fill="none" '
                 f'stroke="{MISSING}" stroke-dasharray="4 3"/>')
    parts.append(f'<text x="{mid}" y="{tools_y + node_h + 36}" '
                 f'text-anchor="middle" font-size="10" fill="{MISSING}">'
                 f'nothing is written down</text>')

    # The reach, right.
    known = {name for _, _, names in FAMILIES for name in names}
    y = top - 16
    for family, reaches, names in FAMILIES:
        parts.append(f'<text x="{col}" y="{y}" font-size="11" font-weight="600" '
                     f'fill="{ACCENT}">{family}</text>')
        parts.append(f'<text x="{col + 58}" y="{y}" font-size="10" fill="{INK}" '
                     f'fill-opacity="0.7">{xml(reaches)}</text>')
        y += 8
        for name in names:
            y += 19
            there = name in tool_names
            parts.append(
                f'<rect x="{col}" y="{y - 13}" width="{reach_w}" height="18" '
                f'rx="3" fill="{"none" if not there else ENTITY}" '
                f'stroke="{MISSING if not there else "none"}"/>')
            parts.append(f'<text x="{col + 8}" y="{y}" font-size="10" '
                         f'fill="{MISSING if not there else "#FFFFFF"}">'
                         f'{xml(name)}{"" if there else "  (not declared)"}</text>')
        y += 20
    extra = sorted(set(tool_names) - known)
    if extra:
        parts.append(f'<text x="{col}" y="{y}" font-size="10" fill="{MISSING}">'
                     f'{xml(", ".join(extra))} — declared, not grouped here</text>')
    parts.append(f'<line x1="{left + node_w}" y1="{tools_y + 20}" x2="{col - 10}" '
                 f'y2="{top + 60}" stroke="{INK}" stroke-opacity="0.35" '
                 f'marker-end="url(#tip)"/>')

    if example:
        base = h - strip + 16
        parts.append(f'<line x1="24" y1="{base - 22}" x2="{w - 24}" '
                     f'y2="{base - 22}" stroke="{INK}" stroke-opacity="0.18"/>')
        parts.append(f'<text x="24" y="{base - 2}" font-size="11" '
                     f'font-weight="600" fill="{ACCENT}">one question, and what '
                     f'it actually called</text>')
        parts.append(f'<text x="24" y="{base + 16}" font-size="11" fill="{INK}" '
                     f'fill-opacity="0.8">{xml(example["question"])}</text>')
        calls = list(example["calls"])
        box_w = max(118.0, (w - 48 - (len(calls) - 1) * 22) / max(len(calls), 1))
        for n, call in enumerate(calls):
            x = 24 + n * (box_w + 22)
            last = call == "answer"
            parts.append(
                f'<rect x="{x}" y="{base + 32}" width="{box_w}" height="26" '
                f'rx="4" fill="{"none" if last else MESSAGE}" stroke="{INK}" '
                f'stroke-opacity="{0.3 if not last else 0.45}" '
                f'stroke-dasharray="{"4 3" if last else "none"}"/>')
            parts.append(
                f'<text x="{x + box_w / 2}" y="{base + 49}" text-anchor="middle" '
                f'font-size="10" fill="{INK}">{xml(call)}</text>')
            if n:
                parts.append(f'<line x1="{x - 22}" y1="{base + 45}" x2="{x}" '
                             f'y2="{base + 45}" stroke="{INK}" '
                             f'stroke-opacity="0.4" marker-end="url(#tip)"/>')
    return "\n".join(parts) + "\n</svg>"


def written_picture(labels: list[dict], relationships: list[dict],
                    sample: dict, *, width: float | None = None) -> str:
    """What the library just wrote: the labels, the edges, and one node in full.

    All three arguments come from the graph's own answer rather than from a
    schema drawn by hand:

        labels        [{"label": str, "n": int}, ...]
        relationships [{"type": str, "from": str, "to": str, "n": int}, ...]
        sample        {"label": str, "fields": {name: value, ...}}

    `sample` carries values and not only field names. Names alone say that a
    message has a `role` and a `timestamp` and leave the reader to guess what
    goes in them; `user` and `2026-11-19T15:41:02` say it.

    Drawn because the counts alone do not answer the question the cell above
    raises -- *what* did those two calls create. And because two of the edges
    are not in the documentation: the pages that describe this layer name
    `HAS_MESSAGE` and stop, while `FIRST_MESSAGE` and `NEXT_MESSAGE` are in the
    data. The graph is the authority, so the figure reads the graph.
    """
    left, top, row = 30.0, 112.0, 30.0
    w = 860.0
    fields = list(sample["fields"].items())
    h = top + max(len(labels), len(relationships)) * row + 34 * len(fields) + 46
    parts = [frame(w, h, width), ARROW]
    parts.append(f'<text x="24" y="32" fill="{ACCENT}" font-size="15" '
                 f'font-weight="600">what those two calls wrote</text>')
    parts.append(f'<text x="24" y="52" font-size="11" fill="{INK}" '
                 f'fill-opacity="0.75">read back from the graph, not from the '
                 f'library</text>')

    col2 = left + 250
    # Headers sit a full line above the first row, not on it: an earlier version
    # put both at the same y and the word "labels" was drawn over the first box.
    parts.append(f'<text x="{left}" y="{top - 26}" font-size="11" '
                 f'font-weight="600" fill="{ACCENT}">labels</text>')
    parts.append(f'<text x="{col2}" y="{top - 26}" font-size="11" '
                 f'font-weight="600" fill="{ACCENT}">relationships</text>')

    for n, item in enumerate(labels):
        y = top + n * row
        parts.append(f'<rect x="{left}" y="{y}" width="200" height="22" '
                     f'rx="3" fill="{MESSAGE}" stroke="{INK}" '
                     f'stroke-opacity="0.3"/>')
        parts.append(f'<text x="{left + 8}" y="{y + 15}" font-size="11" '
                     f'fill="{INK}">:{xml(item["label"])}</text>')
        parts.append(f'<text x="{left + 192}" y="{y + 15}" text-anchor="end" '
                     f'font-size="11" font-weight="600" fill="{ACCENT}">'
                     f'{item["n"]}</text>')

    for n, edge in enumerate(relationships):
        y = top + n * row
        text = f'({edge["from"]})-[:{edge["type"]}]->({edge["to"]})'
        parts.append(f'<text x="{col2}" y="{y + 15}" font-size="11" '
                     f'fill="{INK}">{xml(text)}</text>')
        parts.append(f'<text x="{w - 30}" y="{y + 15}" text-anchor="end" '
                     f'font-size="11" font-weight="600" fill="{ACCENT}">'
                     f'{edge["n"]}</text>')

    # One node in full, underneath: the answer to "and what do they hold".
    base = top + max(len(labels), len(relationships)) * row + 34
    parts.append(f'<line x1="24" y1="{base - 18}" x2="{w - 24}" y2="{base - 18}" '
                 f'stroke="{INK}" stroke-opacity="0.18"/>')
    parts.append(f'<text x="24" y="{base}" font-size="11" font-weight="600" '
                 f'fill="{ACCENT}">one :{xml(sample["label"])}, in full</text>')
    for n, (name, value) in enumerate(fields):
        y = base + 14 + n * 34
        parts.append(f'<rect x="24" y="{y}" width="112" height="26" rx="4" '
                     f'fill="{ENTITY}"/>')
        parts.append(f'<text x="80" y="{y + 17}" text-anchor="middle" '
                     f'font-size="10" fill="#FFFFFF">{xml(name)}</text>')
        shown = " ".join(str(value).split())
        parts.append(f'<text x="148" y="{y + 17}" font-size="10" fill="{INK}" '
                     f'fill-opacity="0.85">{xml(fit(shown, w - 176, 10))}</text>')
    return "\n".join(parts) + "\n</svg>"


def text_over_box(doc: str) -> str:
    """The seventh check: a caption drawn over a box that is not its own.

    `checks` compares boxes with boxes and edge labels with boxes, and neither
    catches a column header drawn at the same y as the first row of its own
    column -- which is how "labels" came to be printed over the first label on
    19/11/2026.

    Ownership comes from the order of the document, not from the geometry: every
    function here emits a box and then its caption, so the box that owns a text
    is the last one written before it. A text inside any *other* box is the
    defect. Reading geometry alone cannot tell the two apart -- both are a
    baseline inside a rectangle.
    """
    items = []
    for m in re.finditer(
            r'<rect x="(-?[\d.]+)" y="(-?[\d.]+)" width="([\d.]+)" height="([\d.]+)"'
            r'|<text[^>]*x="(-?[\d.]+)" y="(-?[\d.]+)"[^>]*>([^<]*)<', doc):
        if m.group(1) is not None:
            items.append(("rect", tuple(float(v) for v in m.groups()[:4])))
        else:
            items.append(("text", (float(m.group(5)), float(m.group(6)), m.group(7))))

    over, boxes = [], []
    for kind, value in items:
        if kind == "rect":
            boxes.append(value)
            continue
        tx, ty, label = value
        for n, (bx, by, bw, bh) in enumerate(boxes):
            if bw > 700 and bh > 300:
                continue                              # the canvas itself
            if n == len(boxes) - 1:
                continue                              # the box this caption is in
            if bx - 1 < tx < bx + bw + 1 and by + 1 < ty < by + bh - 1:
                over.append(label.strip()[:28] or "(empty)")
                break
    return "no text over a box" if not over else f"TEXT OVER A BOX: {over}"


def decides_picture(turns: list[dict], *, width: float | None = None) -> str:
    """Two questions, one agent, and the tool it chose to call on only one.

        turns  [{"question": str, "path": [tool, ...],
                 "recalled": None | {"asked": str, "returned": str}}, ...]

    The claim of section 5 is a decision, and a decision is only visible against
    the case where it went the other way. So both turns are drawn on the same
    grid: where one begins with `recall`, the other begins with an empty orange
    slot in the same position -- the module's convention for what is not there.

    What `recall` handed back is drawn under the lane that called it. Printed
    alone it is a line of output among others; under the chip that produced it,
    it is the reason the next three calls could run.
    """
    box, gap, left, lane = 150.0, 22.0, 24.0, 128.0
    longest = max(len(t["path"]) + (0 if t["recalled"] else 1) for t in turns)
    w = left * 2 + longest * box + (longest - 1) * gap
    h = 76 + len(turns) * lane
    parts = [frame(w, h, width), ARROW]
    parts.append(f'<text x="24" y="32" fill="{ACCENT}" font-size="15" '
                 f'font-weight="600">the same agent, asked two questions</text>')
    parts.append(f'<text x="24" y="52" font-size="11" fill="{INK}" '
                 f'fill-opacity="0.75">nothing tells it which one needs the '
                 f'memory: it has the tool, and one line about when</text>')

    for row, turn in enumerate(turns):
        top = 92.0 + row * lane
        parts.append(f'<text x="{left}" y="{top}" font-size="12" fill="{INK}" '
                     f'font-weight="600">{xml(fit(turn["question"], w - 60, 12))}'
                     f'</text>')

        # The empty slot keeps the two lanes on one grid: `about_contracts` sits
        # under `about_contracts` whether or not a recall came first.
        steps = ([(s, "call") for s in turn["path"]] if turn["recalled"]
                 else [("recall", "absent")] + [(s, "call") for s in turn["path"]])
        y = top + 16
        for n, (step, kind) in enumerate(steps):
            x = left + n * (box + gap)
            out = kind == "absent"
            first = step == "recall"
            parts.append(
                f'<rect x="{x}" y="{y}" width="{box}" height="32" rx="4" '
                f'fill="{"none" if out else (ACCENT if first else MESSAGE)}" '
                f'stroke="{MISSING if out else INK}" '
                f'stroke-width="{2 if out else 1}" '
                f'stroke-dasharray="{"4 3" if out else "none"}" '
                f'stroke-opacity="{1 if out else 0.35}"/>')
            parts.append(
                f'<text x="{x + box / 2}" y="{y + 20}" text-anchor="middle" '
                f'font-size="11" '
                f'fill="{MISSING if out else ("#FFFFFF" if first else INK)}">'
                f'{xml(fit(step, box - 14, 11))}</text>')
            if n:
                parts.append(f'<line x1="{x - gap}" y1="{y + 16}" x2="{x}" '
                             f'y2="{y + 16}" stroke="{INK}" stroke-opacity="0.4" '
                             f'marker-end="url(#tip)"/>')

        if turn["recalled"]:
            parts.append(f'<rect x="{left}" y="{y + 44}" width="{w - 48}" '
                         f'height="30" rx="4" fill="{MESSAGE}" fill-opacity="0.5" '
                         f'stroke="{ACCENT}" stroke-opacity="0.5"/>')
            parts.append(f'<text x="{left + 10}" y="{y + 63}" font-size="10" '
                         f'fill="{INK}">{xml(fit("recall returned: " + " ".join(turn["recalled"]["returned"].split()), w - 80, 10))}</text>')
        else:
            parts.append(f'<text x="{left}" y="{y + 60}" font-size="10" '
                         f'fill="{MISSING}">not called -- this question names '
                         f'everything it needs</text>')
    return "\n".join(parts) + "\n</svg>"
