"""The drawings of module 5, one function per picture.

    from pictures import toy_picture, loop_picture, rag_picture, graphrag_picture

Out of the notebook since 4/11/2026, and the reason is a measurement: the four
drawings were 15,116 characters against 10,147 for everything else the notebook
runs. Sixty per cent of its code was geometry, and the four longest cells in a
module about retrieval were all about coordinates.

Module 4 keeps its drawings inline, and that is right there: the similarity
graph of one vendor group *is* the subject of its section. Here the pictures
illustrate pipelines, and how a box is positioned is not the lesson.

**Every function takes its data as arguments.** None of them opens a session or
a driver, so none can fetch a figure of its own: a picture can only show what
the cell above it produced, which is the property the inline versions had and
the one worth keeping.

The conventions are module 4's, and they are load-bearing:

- **orange is what is not there** -- a value a reducer dropped, the half of a
  page the context cut, a vendor name no document carries, a step that is a path
  and not an edge. Never decoration.
- `#CFD8DC` for structured nodes, `#ACDBF8` for what was read from documents,
  `#607D8B` with white text for resolved entities, `#0091EA` for titles and
  numbers. A dashed outline and no fill for what is not data at all -- START,
  END, a question.
- `xml()` on every string that came from the data. One unescaped ampersand does
  not draw badly, it stops the whole image: a vendor is called
  `A & M AMUSEMENT INC`.
- `fit()` on every label, or a long department name draws over its neighbour.

`checks()` runs the four validations that catch what the eye does not: the
document parses, nothing is outside the canvas, no edge label sits on a box, and
no ampersand escaped unescaped. Call it on anything added here.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

ARROW = ('<defs><marker id="tip" viewBox="0 0 8 8" refX="7" refY="4"'
         ' markerWidth="7" markerHeight="7" orient="auto">'
         '<path d="M 0 0 L 8 4 L 0 8 z" fill="context-stroke"/></marker></defs>')

# Two palettes, and which one a drawing uses is information.
#
# A picture of the Chicago graph -- Page, Document, Contract, Organization --
# takes module 4's colours, because that is what those colours have meant since
# module 4 and a reader has already learnt them.
#
# A picture of a *program* -- the toy, the repair loop, the agent's loop -- takes
# LangGraph's own, read out of what its `draw_mermaid()` emits: `#f2f0ff` for a
# node, `#bfb6fc` for the end, no fill for the start, and a dashed edge where
# the route is chosen at run time. Both palettes were the same until 5/11/2026,
# which made every pipeline look like a knowledge graph.
#
# Orange stays orange in both. It means the same thing everywhere: this is not
# there.
GRAPH = {"structured": "#CFD8DC", "from_documents": "#ACDBF8",
         "entity": "#607D8B", "title": "#0091EA", "missing": "#FF9900"}

# Graphite, not the lilac `draw_mermaid()` emits. Fidelity to the library was
# the wrong thing to optimise: the lilac reads as decoration, and a diagram of
# machinery should be quiet so that the orange and the data carry all the
# colour. Rejected on sight, 5/11/2026.
FLOW = {"node": "#EFEFF2", "end": "#D6D6DE", "edge": "#767684",
        "ink": "#2E2E3A", "title": "#4A4A5C", "missing": "#FF9900"}

# A picture is shown at its own size -- `width` defaults to the viewBox width,
# so one coordinate is one pixel and a 12-point label renders at twelve points.
#
# It scaled to a fixed 760 until 5/11/2026, which is why the labels could not be
# read: a 1040-wide drawing shown at 760 puts 11-point type at 8, and a Jupyter
# output area around 700 wide shrinks it again. Legibility is not a font size,
# it is the ratio between the font and the canvas -- so the way to bigger labels
# is a *narrower* drawing, never a larger one.
#
# Pass `width` to override, for the rare picture worth showing small.
FIT = 700          # what a notebook cell holds without scrolling sideways

# One knob for every picture at once: how much bigger than its own coordinates
# it is shown. 1.0 is one coordinate to one pixel. Raising it scales the whole
# drawing, type included, so nothing is relatively smaller than before -- it is
# the one adjustment that cannot make a label harder to read.
#
# Here to be turned. A picture that needs a size of its own takes `width=` and
# ignores this.
ZOOM = 1.35


def frame(w: float, h: float, width: float | None = None) -> str:
    """The opening tag. `width` overrides `ZOOM` for one picture."""
    shown = w * ZOOM if width is None else width
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}"'
            f' width="{shown:.0f}"'
            f' font-family="Arial, Helvetica, sans-serif">'
            f'<rect width="{w:.0f}" height="{h:.0f}" fill="#FFFFFF"/>')


def xml(text) -> str:
    """What SVG cannot swallow, escaped."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fit(text: str, width: float, size: float) -> str:
    """Shorten a label to what its box holds, at roughly 0.55 em per character."""
    room = int((width - 16) / (size * 0.55))
    return text if len(text) <= room else text[:room - 1] + "\u2026"


def tools_picture(tools: list, *, width: float | None = None) -> str:
    """The eight tools, apart, before any of them is called.

    The agent's column in `systems_picture` is two nodes and a cycle, which says
    what the shape is and nothing about what it can reach. This is the other
    half: the inventory the model picks from, each with the first sentence of
    the description **the model itself is shown**, so the picture cannot flatter
    the tool with a purpose the prompt does not claim.

    Grouped by what they touch, because that grouping is the thing worth
    learning: two tools read text, three read the graph, one rewrites a
    question, one ends the run. The model is told nothing else about them.

    `tools` is `tools_for(session)` -- the declarations as they are sent.
    """
    READS = {"search_descriptions": "text", "search_titles": "text",
             "reformulate_query": "neither", "find_entity": "graph",
             "contracts_of": "graph", "about_contracts": "graph",
             "about_entity": "graph", "answer": "neither"}
    ORDER = ["text", "graph", "neither"]
    SAYS = {"text": "read text", "graph": "read the graph",
            "neither": "touch no data"}

    BW, BH, GAP, PAD = 318, 50, 14, 22
    W = PAD * 2 + BW * 2 + 24
    groups = [(k, [t for t in tools if READS.get(t["function"]["name"]) == k])
              for k in ORDER]
    rows = sum(-(-len(g) // 2) for _, g in groups)
    H = 52 + rows * (BH + GAP) + len(groups) * 24

    svg = [frame(W, H, width), ARROW,
           f'<text x="{W / 2}" y="28" font-size="13" font-weight="bold"'
           f' fill="{FLOW["title"]}" text-anchor="middle">eight tools, and the'
           f' model is told this much about each</text>']

    y = 48
    for kind, group in groups:
        if not group:
            continue
        svg.append(f'<text x="{PAD}" y="{y + 14}" font-size="11"'
                   f' font-weight="bold" fill="{FLOW["edge"]}">'
                   f'{len(group)} {xml(SAYS[kind])}</text>')
        y += 24
        for i, tool in enumerate(group):
            f = tool["function"]
            x = PAD + (i % 2) * (BW + 24)
            if i and i % 2 == 0:
                y += BH + GAP
            svg.append(f'<rect x="{x}" y="{y}" width="{BW}" height="{BH}"'
                       f' rx="7" fill="{FLOW["end"] if f["name"] == "answer" else FLOW["node"]}"'
                       f' stroke="{FLOW["edge"]}" stroke-width="1.4"/>')
            svg.append(f'<text x="{x + 12}" y="{y + 19}" font-size="11"'
                       f' font-weight="bold" fill="{FLOW["ink"]}">'
                       f'{xml(f["name"])}'
                       f'({xml(", ".join(f["parameters"]["required"]))})</text>')
            svg.append(f'<text x="{x + 12}" y="{y + 37}" font-size="9.5"'
                       f' fill="{FLOW["edge"]}">'
                       f'{xml(fit(f["description"].split(". ")[0], BW - 6, 9.5))}</text>')
        y += BH + GAP
    svg.append('</svg>')
    return "\n".join(svg)


def systems_picture(graphs: dict, *, width: float | None = None) -> str:
    """The four architectures side by side, as the shapes they actually are.

    A map, placed before any of them runs: four columns, top to bottom, the
    direction `draw_mermaid()` uses. Read the four and the differences are one
    glance -- three fixed routes of three to six nodes, and one two-node cycle.

    **The nodes and edges are read out of the compiled graphs**, not typed here:
    `graphs` is `{name: build().get_graph()}`, so a node renamed in
    `pipelines/` renames itself in the picture. A dashed edge is one LangGraph
    reports as `conditional` -- the route decided at run time, which is the
    second idea of the toy and the whole of the fourth architecture.

    An entry may also be a plain list of node names, drawn as a straight line.
    That was how the agent was passed until 5/11/2026, when it was still a
    hand-written loop — and it stayed a list for a while after it became a
    graph, which is why the one architecture with a cycle was drawn without
    one. Anything that has a `get_graph()` should be passed as a graph.
    """
    # Sized to `FIT`, not the other way round: four columns inside a notebook
    # cell at 1:1, so the node names render at their nominal eleven points.
    #
    # The gutter between columns is 44 and not 20, because it is not a margin:
    # it carries the lane edges, and the agent needs three tracks in it -- the
    # return up, the two ways out, and the self-loop bulging past them. All
    # four shared one track until 5/11/2026, which drew the one architecture
    # with a cycle as a single thick vertical line. `W` grows to keep the boxes
    # the width they were.
    # The box width is fixed -- `answer_from_context` has to fit at eleven
    # points -- and the picture is as wide as that makes it. The gutter is 50
    # because it carries three things that must not touch: the right-hand lanes
    # (two tracks on Text2Cypher), the left-hand lanes, and the agent's
    # self-loop bulging 24 to the left of its own column.
    GUTTER, TRACK, LOOP = 50, 11, 24
    BW, BH, GAP = 150, 34, 28
    COL = BW + GUTTER
    W = COL * len(graphs) + 20
    deepest = max(len(_rank(g)) for g in graphs.values())
    H = 92 + deepest * (BH + GAP)

    svg = [frame(W, H, width), ARROW,
           f'<text x="{W / 2}" y="26" font-size="13" font-weight="bold"'
           f' fill="{FLOW["title"]}" text-anchor="middle">four architectures,'
           f' and three of them decide their route before the question'
           f' arrives</text>']

    for i, (name, graph) in enumerate(graphs.items()):
        x = 10 + i * COL + 10
        rows = _rank(graph)
        svg.append(f'<text x="{x + BW / 2}" y="56" font-size="11"'
                   f' font-weight="bold" fill="{FLOW["ink"]}"'
                   f' text-anchor="middle">{xml(name)}</text>')
        at = {}
        for r, names in enumerate(rows):
            y = 70 + r * (BH + GAP)
            for k, node in enumerate(names):
                w = BW / len(names) - (6 if len(names) > 1 else 0)
                nx = x + k * (BW / len(names))
                at[node] = (nx + w / 2, y, y + BH, w)
                kind = ("start" if node == "__start__" else
                        "end" if node == "__end__" else "node")
                label = {"__start__": "START", "__end__": "END"}.get(node, node)
                svg += flow_node(nx, y, w, BH, "", label, kind=kind)
        # Three kinds of edge, and the first version drew them all as one
        # straight line between centres. That put `guardrail -> __end__` --
        # which skips five rows -- vertically through every box between them,
        # and it put the agent's four same-row edges on top of each other.
        #
        # So: a step down is a straight line, anything longer or upward is
        # routed down a lane beside the column, and a node that points at
        # itself gets a small arc on its own side.
        # Two lanes, and the choice is forced: a node with a neighbour to its
        # right cannot leave on that side without crossing it. `correct` did
        # exactly that until 5/11/2026, striking a line through the word
        # `execute` on its way to the lane.
        # Which side a node may leave on. A neighbour on one side settles it;
        # with both sides free the direction decides, and that is the rule the
        # agent needs: **left goes back, right goes out**. The return from
        # `run_tools` and the self-loop then share the left, the two ways to
        # END share the right, and the column says what it does.
        no_right = {n for names in rows if len(names) > 1 for n in names[:-1]}
        no_left = {n for names in rows if len(names) > 1 for n in names[1:]}
        # One track per lane edge, counted as they are drawn: two edges sharing
        # a track are one line on the page, and the reader cannot tell a cycle
        # from a dead end.
        used = {True: 0, False: 0}
        loops = []
        for a, b, chosen in _edges(graph):
            src, dst = at.get(a), at.get(b)
            if not src or not dst:
                continue
            if a == b:
                # On its own right edge, using the node's width and not the
                # column's: a row of two nodes has half-width boxes, and
                # `BW / 2` put the arc outside the one it belonged to.
                # On the **left**, while everything else leaves on the right.
                # It entered the top edge until 5/11/2026, a few pixels from
                # where the START arrow lands, and read as a second arrow out
                # of START. Left for "back to itself", right for "somewhere
                # else", is a rule the reader can hold.
                loops.append((src, chosen))
            elif dst[1] == src[1]:
                svg.append(_arc(src[0] + src[3] / 2, src[1], src[2],
                                chosen, reach=18))
            elif dst[1] == src[2] + GAP:
                # Several nodes on one row can point at the same node below, and
                # aiming them all at its centre landed two arrowheads on the
                # same pixel. Each arrives above its own source instead.
                into = dst[0] + max(-dst[3] / 2 + 10,
                                    min(dst[3] / 2 - 10, src[0] - dst[0]))
                svg += flow_edge(src[0], src[2], into, dst[1], chosen=chosen)
            else:
                # The lane is picked by the source and the target has to agree:
                # one lane per edge, so it enters on the side it arrives from.
                side = (False if a in no_right else
                        True if a in no_left else
                        dst[1] > src[1])
                track = 9 + used[side] * TRACK
                used[side] += 1
                svg.append(_round(src, dst, x + BW + track if side else x - track,
                                  side, chosen))
        # Drawn last, and outside every track this column used: a self-loop
        # that cuts through the lanes reads as a junction.
        for src, chosen in loops:
            svg.append(_arc(src[0] - src[3] / 2, src[1], src[2], chosen,
                            reach=-(LOOP + used[False] * TRACK)))
    svg.append('</svg>')
    return "\n".join(svg)


def _arc(x, top, bottom, chosen, reach=26, into=None) -> str:
    """A node pointing at itself: out of its right edge, round, and back in.

    `into` is the x of the entry point on the **top** edge. It exists because
    the return edge of the agent arrives at the right edge too, and a self-loop
    coming back in at the same place put two arrowheads seventeen pixels apart:
    one cycle drawn twice, is how it read. Entering from above separates them,
    at the cost of crossing the lane once -- two lines at a right angle, which
    the eye resolves and two arrowheads do not.

    Without `into` it closes on the right edge, which is what a same-row edge
    needs.
    """
    dash = ' stroke-dasharray="5 4"' if chosen else ''
    mid = (top + bottom) / 2
    if into is None:
        return (f'<path d="M {x:.0f} {bottom:.0f} C {x + reach:.0f} {bottom:.0f},'
                f' {x + reach:.0f} {top:.0f}, {x:.0f} {top:.0f}" fill="none"'
                f' stroke="{FLOW["edge"]}" stroke-width="1.3"{dash}'
                f' marker-end="url(#tip)"/>')
    return (f'<path d="M {x:.0f} {mid:.0f} C {x + reach:.0f} {mid:.0f},'
            f' {x + reach:.0f} {top - reach:.0f}, {into:.0f} {top - reach:.0f}'
            f' L {into:.0f} {top:.0f}" fill="none"'
            f' stroke="{FLOW["edge"]}" stroke-width="1.3"{dash}'
            f' marker-end="url(#tip)"/>')


def _round(src, dst, lane, right, chosen) -> str:
    """An edge that skips rows, or goes back up one: out of the source's
    **edge**, down or up a lane beside the column, and in at the target's edge
    on the same side.

    Both ends were eight pixels inside the box until 5/11/2026, taken from the
    node's centre plus a flat forty. On a narrow column that put the start of
    the line in the middle of the word it was leaving, so an edge going
    somewhere else read as an edge going *through* the box. The two ends are
    now the right edge and the vertical middle, which is where a reader looks
    for them.
    """
    dash = ' stroke-dasharray="5 4"' if chosen else ''
    x1 = src[0] + (src[3] / 2 if right else -src[3] / 2)
    x2 = dst[0] + (dst[3] / 2 if right else -dst[3] / 2)
    # Out at the middle, in near the **bottom**. Both at the middle put this
    # arrowhead seventeen pixels from the self-loop's, which comes back in at
    # the top of the same edge -- one pixel inside the eighteen the sixth check
    # calls crowding, and it looked it.
    y1 = (src[1] + src[2]) / 2
    y2 = dst[2] - 9
    return (f'<path d="M {x1:.0f} {y1:.0f} L {lane:.0f} {y1:.0f}'
            f' L {lane:.0f} {y2:.0f} L {x2:.0f} {y2:.0f}" fill="none"'
            f' stroke="{FLOW["edge"]}" stroke-width="1.3"{dash}'
            f' marker-end="url(#tip)"/>')


def _edges(graph):
    """(source, target, conditional) for a compiled graph, or for a plain list
    of node names read as a straight line."""
    if isinstance(graph, (list, tuple)):
        return [(graph[i], graph[i + 1], False) for i in range(len(graph) - 1)]
    return [(e.source, e.target, bool(e.conditional)) for e in graph.edges]


def _rank(graph):
    """Nodes in rows, by how far they are from the start. A node reachable at
    two depths takes the shallower, so a cycle does not push its own head down."""
    names = list(graph) if isinstance(graph, (list, tuple)) else list(graph.nodes)
    edges = _edges(graph)
    depth = {names[0]: 0}
    for _ in names:
        for a, b, _c in edges:
            if a in depth and (b not in depth or depth[b] > depth[a] + 1):
                if b != names[0]:
                    depth[b] = depth[a] + 1
    # `__end__` is pinned to the bottom. By depth it lands wherever the first
    # edge reaches it -- in text2cypher the guardrail can end the run at row 2
    # -- and then the edge from `answer` runs back up to it and is drawn as a
    # cycle, which it is not. Mermaid pins it for the same reason.
    deepest = max([d for n, d in depth.items() if n != "__end__"] or [0])
    if "__end__" in depth:
        depth["__end__"] = deepest + 1
    rows = {}
    for n in names:
        rows.setdefault(depth.get(n, deepest + 1), []).append(n)
    return [rows[k] for k in sorted(rows)]


def flow_node(x, y, w, h, upper: str, lower: str, *, kind="node") -> list[str]:
    """One node of a program, in LangGraph's own shape and colours.

    `kind` is `start`, `node` or `end`: a start is a stadium with no fill and an
    end is the filled one, which is how `draw_mermaid()` marks them. Returned as
    a list of strings so a caller can place it and keep its own ordering.
    """
    radius = h / 2 if kind in ("start", "end") else 7
    fill = "none" if kind == "start" else FLOW["end" if kind == "end" else "node"]
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}"'
           f' fill="{fill}" stroke="{FLOW["edge"]}" stroke-width="1.4"/>']
    if upper:
        out.append(f'<text x="{x + w / 2}" y="{y + h / 2 - 4}" font-size="9"'
                   f' fill="{FLOW["edge"]}" text-anchor="middle">'
                   f'{xml(fit(upper, w, 9))}</text>')
        out.append(f'<text x="{x + w / 2}" y="{y + h / 2 + 11}" font-size="11"'
                   f' font-weight="bold" fill="{FLOW["ink"]}" text-anchor="middle">'
                   f'{xml(fit(lower, w, 11))}</text>')
    else:
        out.append(f'<text x="{x + w / 2}" y="{y + h / 2 + 4}" font-size="11"'
                   f' font-weight="bold" fill="{FLOW["ink"]}" text-anchor="middle">'
                   f'{xml(fit(lower, w, 11))}</text>')
    return out


def flow_edge(x1, y1, x2, y2, label="", *, chosen=False, side=1) -> list[str]:
    """One edge. `chosen` marks a route decided at run time, which LangGraph
    draws dashed -- `-.->` in its mermaid -- and which is the whole of what the
    toy's second idea is about."""
    dash = ' stroke-dasharray="5 4"' if chosen else ''
    out = [f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}"'
           f' stroke="{FLOW["edge"]}" stroke-width="1.6"{dash}'
           f' marker-end="url(#tip)"/>']
    if label:
        out.append(f'<text class="edge" x="{(x1 + x2) / 2 + 10 * side:.0f}"'
                   f' y="{(y1 + y2) / 2 + 4:.0f}" font-size="9" font-weight="bold"'
                   f' fill="{FLOW["edge"]}"'
                   f' text-anchor="{"start" if side > 0 else "end"}">'
                   f'{xml(label)}</text>')
    return out


def checks(doc: str) -> str:
    """The four validations, as a line to print.

    The canvas is read out of the document's own `viewBox` rather than passed
    in. It used to be an argument, and on 4/11/2026 a drawing was rebuilt at
    920x440 while its cell still said `checks(picture, 1000, 340)`: the check
    reported OUTSIDE THE CANVAS about a picture that fitted. A dimension written
    in two places diverges.

    Reported, not raised: a picture that is slightly wrong is still worth
    looking at, and a traceback instead of an image says nothing about which
    rule broke.
    """
    out = []
    seen = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', doc)
    if not seen:
        return "no viewBox: cannot check anything"
    width, height = float(seen.group(1)), float(seen.group(2))
    try:
        ET.fromstring(doc)
        out.append("parses")
    except ET.ParseError as error:
        out.append(f"DOES NOT PARSE: {error}")
    ys = [float(v) for v in re.findall(r'y="(-?[\d.]+)"', doc)]
    xs = [float(v) for v in re.findall(r'x="(-?[\d.]+)"', doc)]
    inside = ys and xs and min(ys) >= 0 and max(ys) <= height \
        and min(xs) >= 0 and max(xs) <= width
    out.append("inside the canvas" if inside else "OUTSIDE THE CANVAS")
    loose = re.search(r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;)", doc)
    out.append("no loose ampersand" if not loose else "LOOSE AMPERSAND")

    # The fourth check, and the one that was missing on 4/11/2026 when a reader
    # reported arrows running over the nodes: an edge label that lands inside a
    # box. Only labels marked `class="edge"` are tested -- a caption drawn inside
    # its own box is not a defect, and an earlier version of this check guessed
    # the difference from whether the text was centred, which flagged eight
    # perfectly good left-aligned captions in the first drawing that used them.
    boxes = [tuple(float(v) for v in m.groups()) for m in re.finditer(
        r'<rect x="(-?[\d.]+)" y="(-?[\d.]+)" width="([\d.]+)" height="([\d.]+)"', doc)]
    labels = [(float(m.group(1)), float(m.group(2))) for m in re.finditer(
        r'<text class="edge" x="(-?[\d.]+)" y="(-?[\d.]+)"', doc)]
    on_a_box = 0
    for lx, ly in labels:
        for bx, by, bw, bh in boxes:
            if bw >= width - 1 and bh >= height - 1:
                continue                       # the background, not a box
            if bx + 4 < lx < bx + bw - 4 and by + 4 < ly < by + bh - 4:
                on_a_box += 1
                break
    # A drawing with no `class="edge"` label reports a pass here, and that is
    # correct only when it has no edge labels at all. `react_picture` is the one
    # such drawing -- its arrows carry no names. If a new picture labels its
    # arrows and forgets the marker, this check passes while testing nothing,
    # which is worse than not having it: four of six pictures were in that state
    # for an hour on 4/11/2026.
    out.append(f"{len(labels)} edge label(s), none on a box" if not on_a_box
               else f"{on_a_box} of {len(labels)} LABEL(S) ON A BOX")

    # The fifth, added the same evening as the fourth and for the same reason: a
    # reader said a drawing looked "all wrong" and it was two boxes on top of
    # each other. Nothing in the first four compares a box with another box, so
    # a figure could overlap itself and still report four passes.
    real = [b for b in boxes if not (b[2] >= width - 1 and b[3] >= height - 1)]
    overlaps = sum(
        1 for i, (ax, ay, aw, ah) in enumerate(real)
        for bx, by, bw, bh in real[i + 1:]
        if ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by)
    out.append("no boxes overlap" if not overlaps
               else f"{overlaps} OVERLAPPING BOX PAIR(S)")

    # The sixth, and the third of these added because a reader saw something the
    # checks did not. The Counter's self-loop used to re-enter the top of its own
    # node twelve pixels from the arrow arriving from START: two arrowheads on
    # one edge of one box, which parses, fits, overlaps nothing, and looks wrong.
    # Any two heads closer than this are crowding whether or not that was the
    # cause.
    heads = [(float(m.group(1)), float(m.group(2))) for m in re.finditer(
        r'<line[^>]*x2="(-?[\d.]+)" y2="(-?[\d.]+)"[^>]*marker-end', doc)]
    heads += [(float(m.group(1)), float(m.group(2))) for m in re.finditer(
        r'<path d="M[^"]*?([\d.]+) ([\d.]+)"[^>]*marker-end', doc)]
    close = sum(1 for i, a in enumerate(heads) for b in heads[i + 1:]
                if (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 < 18 ** 2)
    out.append("arrowheads clear of each other" if not close
               else f"{close} PAIR(S) OF CROWDED ARROWHEADS")
    return f"{width:.0f}x{height:.0f}, " + ", ".join(out)


def toy_picture(trail: list, *, reducer: bool, width: float | None = None) -> str:
    """One lane of the toy graph, top to bottom, the direction mermaid uses.

    Called twice, once per cell, rather than drawing both lanes at once: with
    one picture the contrast is handed over before the reader has run the second
    cell, with two it arrives where the surprise is.

    Vertical and narrow on purpose. It was 900 wide and horizontal until
    5/11/2026, and at that width the labels rendered at eight points -- a
    narrower canvas at the same font size is a bigger label, which is the only
    way to get legibility without a bigger image.

    `trail` is what the graph returned. `reducer` only chooses the heading and
    whether to mark the value that went missing: the drawing never recomputes
    the result, so it cannot disagree with the cell above it.
    """
    W, BW, BH, GAP = 400, 230, 44, 30
    X = (W - BW) / 2
    # `first` ran in both graphs and returned ['first']. Without a reducer the
    # second node replaced it, so the lane whose third box reads ['second'] is
    # one where a value was dropped -- and that is what the orange marks.
    rows = [("", "trail: []", "start"), ("first", "['first']", "node"),
            ("second", str(trail), "node"), ("", str(trail), "end")]
    H = 74 + len(rows) * (BH + GAP) + (26 if not reducer else 0)
    heading = ("Annotated[list[str], add]" if reducer else "list[str] — no reducer")

    svg = [frame(W, H, width), ARROW,
           f'<text x="{W / 2}" y="26" font-size="13" font-weight="bold"'
           f' fill="{FLOW["title"]}" text-anchor="middle">{xml(heading)}</text>',
           f'<text x="{W / 2}" y="44" font-size="11" fill="{FLOW["edge"]}"'
           f' text-anchor="middle">'
           f'{"the reducer appends" if reducer else "and nothing warned"}</text>']

    for i, (upper, lower, kind) in enumerate(rows):
        y = 62 + i * (BH + GAP)
        svg += flow_node(X, y, BW, BH, upper, lower, kind=kind)
        if i:
            svg += flow_edge(W / 2, y - GAP, W / 2, y)
        if i == 1 and not reducer:
            svg.append(f'<text class="edge" x="{X + BW + 10}" y="{y + 28}"'
                       f' font-size="11" font-weight="bold"'
                       f' fill="{FLOW["missing"]}">returned here</text>')
        if i == 2 and not reducer:
            svg.append(f'<text class="edge" x="{X + BW + 10}" y="{y + 28}"'
                       f' font-size="11" font-weight="bold"'
                       f' fill="{FLOW["missing"]}">replaced here</text>')
    if not reducer:
        svg.append(f'<text x="{W / 2}" y="{H - 10}" font-size="11"'
                   f' fill="{FLOW["missing"]}" text-anchor="middle">no error, no'
                   f' warning</text>')
    svg.append('</svg>')
    return "\n".join(svg)


def loop_picture(passes: list, final: dict, *, width: float | None = None) -> str:
    """One node, one conditional edge, and the turns the loop actually took.

    Vertical like the lane above it, so the two pictures of the toy read as the
    same kind of object. The dashed edges are the conditional one taken two
    ways: back to `bump` while the counter is under three, out to END once it is
    not. That dashed line is the whole second idea of the toy, and it is the
    shape the agent's loop has.

    Drawn from `passes` and `final`, the stream and the result above.
    """
    # Wide enough for the self-loop to sit beside the node instead of over it.
    W, BW, BH, GAP = 500, 200, 44, 34
    X = (W - BW) / 2
    H = 74 + 3 * (BH + GAP) + 24 + len(passes) * 20

    svg = [frame(W, H, width), ARROW,
           f'<text x="{W / 2}" y="26" font-size="13" font-weight="bold"'
           f' fill="{FLOW["title"]}" text-anchor="middle">one node, one'
           f' edge</text>',
           f'<text x="{W / 2}" y="44" font-size="11" fill="{FLOW["edge"]}"'
           f' text-anchor="middle">chosen by the previous result</text>']

    ys = [62 + k * (BH + GAP) for k in range(3)]
    svg += flow_node(X, ys[0], BW, BH, "", "n: 0", kind="start")
    svg += flow_node(X, ys[1], BW, BH, "bump", "n + 1")
    svg += flow_node(X, ys[2], BW, BH, "", str(final), kind="end")
    svg += flow_edge(W / 2, ys[0] + BH, W / 2, ys[1])
    svg += flow_edge(W / 2, ys[1] + BH, W / 2, ys[2], "-> END", chosen=True, side=1)

    # The edge back up: the same conditional edge, taken the other way. Out of
    # the right edge low, round, and back into the right edge high, so the
    # arrowhead reads as "up, and in again".
    #
    # The first version hooked round the left and re-entered the top, landing
    # its arrowhead twelve pixels from the one arriving from START: two heads on
    # one edge of one box, which is what made it ugly. A self-loop belongs
    # beside its node, on a side nothing else uses.
    right, lo, hi = X + BW, ys[1] + BH - 10, ys[1] + 10
    bulge = right + 54
    svg.append(f'<path d="M {right} {lo} C {bulge} {lo}, {bulge} {hi},'
               f' {right} {hi}" fill="none" stroke="{FLOW["edge"]}"'
               f' stroke-width="1.6" stroke-dasharray="5 4"'
               f' marker-end="url(#tip)"/>')
    svg.append(f'<text class="edge" x="{bulge + 8}" y="{ys[1] + BH / 2 + 4}"'
               f' font-size="11" font-weight="bold" fill="{FLOW["edge"]}">'
               f'while n &lt; 3</text>')

    svg.append(f'<text x="{W / 2}" y="{ys[2] + BH + 28}" font-size="11"'
               f' font-weight="bold" fill="{FLOW["title"]}" text-anchor="middle">'
               f'what ran</text>')
    for i, step in enumerate(passes):
        n = step["bump"]["n"]
        svg.append(f'<text x="{W / 2}" y="{ys[2] + BH + 48 + i * 20}"'
                   f' font-size="11" fill="{FLOW["ink"]}" text-anchor="middle">'
                   f'bump {i + 1}: n = {n}'
                   f'   {"&#8594; bump" if n < 3 else "&#8594; END"}</text>')
    svg.append('</svg>')
    return "\n".join(svg)


def rag_picture(answer, pages: list, *, dense: bool = False,
                width: float | None = None) -> str:
    """Three pages into one context, and how much of each the context carries.

    The only drawing here with both palettes, on purpose. The question, the
    index and the context are parts of a **program**, so they take LangGraph's
    lilac; the three pages are rows out of the Chicago graph, so they keep the
    pale blue that has meant "read from a document" since module 4. The colour
    says which side of the system each box is on, which is the thing RAG is:
    a fixed program reading pages."""

    # Drawn from the same call the cell above made, so the picture cannot claim a
    # page the retriever did not return. Orange is what the context left out: the
    # node that assembles it keeps the first 1,500 characters of each page, and
    # nothing downstream can tell that the rest existed.
    CUT = 1500
    W, H, BW, BH = 980, 290, 150, 44


    def box(x, y, w, h, fill, lines, outline=False):
        dash = ' stroke-dasharray="4 3"' if outline else ''
        svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6"'
                   f' fill="{"none" if outline else fill}"'
                   f' stroke="{"#B7B7B7" if outline else "#FFFFFF"}"'
                   f' stroke-width="{1.4 if outline else 2}"{dash}/>')
        step = h / (len(lines) + 1)
        for i, (text, size, colour) in enumerate(lines, 1):
            svg.append(f'<text x="{x + w / 2}" y="{y + step * i + size / 3:.0f}"'
                       f' font-size="{size}" font-weight="bold" fill="{colour}"'
                       f' text-anchor="middle">{xml(fit(text, w, size))}</text>')


    svg = [frame(W, H, width),
           f'<defs><marker id="tip" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7"'
           f' markerHeight="7" orient="auto"><path d="M 0 0 L 8 4 L 0 8 z"'
           f' fill="context-stroke"/></marker></defs>',
           f'<text x="{W / 2}" y="22" font-size="13" font-weight="bold" fill="#0091EA"'
           f' text-anchor="middle">three pages in, one context out — and the context'
           f' is shorter than the pages</text>']

    box(20, 108, BW, BH, "", [("the question", 9, "#90A4AE"),
                              ("liquidated damages", 10.5, "#546E7A")], outline=True)
    index, how = (("page_embedding", f"dense, k={len(pages)}") if dense
                  else ("page_text", f"full-text, k={len(pages)}"))
    box(240, 108, 160, BH, FLOW["node"], [(index, 9, FLOW["edge"]),
                                          (how, 10.5, FLOW["ink"])])
    svg.append(f'<line x1="{20 + BW}" y1="130" x2="240" y2="130" stroke="#B7B7B7"'
               f' stroke-width="1.6" marker-end="url(#tip)"/>')
    FAN = 60 + (len(answer.sources) - 1) * 70 + 22
    svg.append('<path d="M 400 130 L 435 130" fill="none" stroke="#B7B7B7"'
               ' stroke-width="1.6"/>')
    svg.append(f'<path d="M 435 82 L 435 {FAN}" fill="none" stroke="#B7B7B7"'
               f' stroke-width="1.6"/>')

    # le tre pagine, con quanto ne vede il modello
    for i, src in enumerate(answer.sources):
        y = 60 + i * 70
        full = len(pages[i]["text"])
        box(470, y, 210, BH, "#ACDBF8",
            [(f"PO {src['purchase_order']}  p{src['page']}  score {src['score']}", 9, "#546E7A"),
             (f"{full:,} chars, {min(CUT, full):,} shown", 10.5, "#263238")])
        # Into the page's left **side**, off a shared bar. Three curves out of
        # one point put three arrowheads nine pixels apart, which the sixth
        # check counts and the eye reads as one thick arrow.
        svg.append(f'<path d="M 435 {y + 22} L 470 {y + 22}" fill="none"'
                   f' stroke="#B7B7B7" stroke-width="1.6"'
                   f' marker-end="url(#tip)"/>')
        if full > CUT:
            # Above the line, not on it. The merge bar runs out of this box at
            # the row's middle, which is exactly where this label sat until
            # 5/11/2026 -- the line struck the orange text through.
            svg.append(f'<text class="edge" x="686" y="{y + 12}" font-size="10"'
                       f' font-weight="bold" fill="#FF9900">'
                       f'&#8722;{full - CUT:,} cut</text>')

    box(790, 108, 170, BH, FLOW["node"],
        [("the context", 9, FLOW["edge"]),
         (f"{len(answer.context):,} characters", 10.5, FLOW["ink"])])
    # The merge is the picture's point: three pages become one context, so it
    # is drawn as three lines joining a bar and one arrow leaving it, not as
    # three arrows landing on the same box.
    TOP, LOW = 82, 60 + (len(answer.sources) - 1) * 70 + 22
    for i in range(len(answer.sources)):
        y = 60 + i * 70 + 22
        svg.append(f'<path d="M 680 {y} L 740 {y}" fill="none"'
                   f' stroke="#B7B7B7" stroke-width="1.6"/>')
    svg.append(f'<path d="M 740 {TOP} L 740 {LOW}" fill="none"'
               f' stroke="#B7B7B7" stroke-width="1.6"/>')
    svg.append('<path d="M 740 130 L 790 130" fill="none" stroke="#B7B7B7"'
               ' stroke-width="1.6" marker-end="url(#tip)"/>')

    svg.append(f'<text x="{W / 2}" y="{H - 10}" font-size="10.5" fill="{FLOW["edge"]}"'
               f' text-anchor="middle">the cut is a decision of the assembling node,'
               f' and it is not in the answer</text>')
    svg.append('</svg>')
    return "\n".join(svg)


def graphrag_picture(pages: list, facts: dict, *, width: float | None = None) -> str:
    """Where the text stops and the graph answers.

    Six rows, one thing per row, 34 pixels of gap between them for the arrows.
    Two earlier versions were wrong in ways the checks now catch. The first drew
    one dotted arrow from the contract back to the pages, labelled `3 hops, via
    Document`: it crossed the figure, its label landed on a node, and it asked
    the reader to take three edges on trust. The second put the vendor and the
    department at the same height as the contract, so the boxes sat on top of
    each other -- which is what the fifth check in `checks()` now counts.

    The direction of each arrow is the content, not decoration.
    `(Contract)-[:HAS_PAGE]->(Page)` returns zero rows: a page hangs off a
    Document of a ContractRecord, because every revision of a purchase order is
    filed separately. Three of the six arrows therefore point **up**, at the row
    above, and the only one leaving the contract downward is the one that
    answers the question.
    """
    po = pages[0]["purchase_order"]
    graph = facts[po]
    vendor, department = graph["vendors"][0], graph["departments"][0]
    W, BH = 920, 46
    WIDE, NARROW = 400, 300            # a row of two boxes, and a row of one
    MID = (W - NARROW) / 2
    LEFT, RIGHT = 30, W - 30 - WIDE
    ROW = [50, 130, 210, 290, 370, 450]
    H = ROW[-1] + BH + 24
    SPINE = MID + NARROW / 2

    svg = [frame(W, H, width), ARROW,
           f'<text x="{W / 2}" y="26" font-size="13" font-weight="bold"'
           f' fill="#0091EA" text-anchor="middle">the text reaches a page, the'
           f' contract is three rows below it, and the vendor is on neither'
           f' page</text>']

    def box(x, y, w, fill, upper, lower, orange=False, outline=False):
        edge = (' stroke="#FF9900" stroke-width="2" stroke-dasharray="5 3"' if orange
                else ' stroke="#B7B7B7" stroke-width="1.4" stroke-dasharray="4 3"'
                if outline else ' stroke="#FFFFFF" stroke-width="2"')
        svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{BH}" rx="6"'
                   f' fill="{"none" if outline else fill}"{edge}/>')
        svg.append(f'<text x="{x + w / 2}" y="{y + 18}" font-size="9"'
                   f' fill="{"#FF9900" if orange else "#607D8B"}"'
                   f' text-anchor="middle">{xml(fit(upper, w, 9))}</text>')
        svg.append(f'<text x="{x + w / 2}" y="{y + 34}" font-size="11"'
                   f' font-weight="bold" fill="{"#FF9900" if orange else "#263238"}"'
                   f' text-anchor="middle">{xml(fit(lower, w, 11))}</text>')

    def arrow(x1, y1, x2, y2, label="", colour="#B7B7B7", side=1):
        """One edge, drawn the way it is stored, with its name beside it.

        The label sits in the 34-pixel gap between two rows and is offset to one
        side of the line, never on it: `side=-1` puts it left of the arrow and
        anchors it to the right, so a long name grows away from the figure.
        """
        # A quadratic through a control point on the vertical, so a branch to a
        # box three hundred pixels sideways leaves and arrives perpendicular to
        # its row instead of cutting across as a flat diagonal. Straight when
        # the two ends share a column, which is most of the spine.
        if abs(x2 - x1) < 2:
            svg.append(f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}"'
                       f' y2="{y2:.0f}" stroke="{colour}" stroke-width="1.6"'
                       f' marker-end="url(#tip)"/>')
        else:
            svg.append(f'<path d="M {x1:.0f} {y1:.0f} C {x1:.0f} {(y1 + y2) / 2:.0f},'
                       f' {x2:.0f} {(y1 + y2) / 2:.0f}, {x2:.0f} {y2:.0f}"'
                       f' fill="none" stroke="{colour}" stroke-width="1.6"'
                       f' marker-end="url(#tip)"/>')
        if label:
            svg.append(f'<text class=\"edge\" x="{(x1 + x2) / 2 + 10 * side:.0f}"'
                       f' y="{(y1 + y2) / 2 + 4:.0f}" font-size="9"'
                       f' font-weight="bold"'
                       f' fill="{"#FF9900" if colour != "#B7B7B7" else "#607D8B"}"'
                       f' text-anchor="{"start" if side > 0 else "end"}">'
                       f'{xml(label)}</text>')

    def fan(y_from, y_to, xs, label):
        """One box to several on the next row: a stem, a bar, a drop into each.

        The sideways branches were quadratic curves until 5/11/2026, and two of
        them leaving the same point three hundred pixels apart read as a
        squashed X. A fan has no diagonal and no crossing: the stem carries the
        label once, so the pair of pages stops looking like one labelled edge
        and one with its label missing.

        Works in both directions -- `y_to` above `y_from` draws the same shape
        upside down, which is what `(Document)-[:HAS_PAGE]->(Page)` needs.
        """
        up = y_to < y_from
        bar = (y_from + y_to) / 2
        stem = bar + (4 if up else -4)
        svg.append(f'<path d="M {SPINE:.0f} {y_from:.0f} L {SPINE:.0f}'
                   f' {stem:.0f}" fill="none" stroke="#B7B7B7"'
                   f' stroke-width="1.6"/>')
        svg.append(f'<path d="M {min(xs):.0f} {bar:.0f} L {max(xs):.0f}'
                   f' {bar:.0f}" fill="none" stroke="#B7B7B7"'
                   f' stroke-width="1.6"/>')
        for x in xs:
            svg.append(f'<path d="M {x:.0f} {bar:.0f} L {x:.0f} {y_to:.0f}"'
                       f' fill="none" stroke="#B7B7B7" stroke-width="1.6"'
                       f' marker-end="url(#tip)"/>')
        svg.append(f'<text class="edge" x="{SPINE + 8:.0f}"'
                   f' y="{bar - 5:.0f}" font-size="9" font-weight="bold"'
                   f' fill="#607D8B" text-anchor="start">{xml(label)}</text>')

    def elbow(x_from, y_from, x_to, y_to, label, colour="#B7B7B7", up=False):
        """A box on the row above to one off to the side: out of a **side**, one
        right angle, in at a **top**. The reverse order of arguments draws it
        the other way, in at the side.

        This is the lateral attachment the spine edges do not need: a vertical
        arrow into the top of a box three hundred pixels sideways has to lean,
        and leaning is what made the bottom row unreadable.
        """
        # Which leg comes first decides where the arrowhead lands. Going out of
        # a side and down into a top wants horizontal first. Coming up out of a
        # top and in at a side wants vertical first -- drawn the other way on
        # 5/11/2026 it ran along the target's edge and the head arrived in the
        # corner, pointing at nothing.
        if up:
            path = (f"M {x_from:.0f} {y_from:.0f} L {x_from:.0f} {y_to:.0f}"
                    f" L {x_to:.0f} {y_to:.0f}")
            lx, ly = (x_from + x_to) / 2, y_to - 7
        else:
            path = (f"M {x_from:.0f} {y_from:.0f} L {x_to:.0f} {y_from:.0f}"
                    f" L {x_to:.0f} {y_to:.0f}")
            lx, ly = (x_from + x_to) / 2, y_from - 6
        svg.append(f'<path d="{path}" fill="none" stroke="{colour}"'
                   f' stroke-width="1.6" marker-end="url(#tip)"/>')
        svg.append(f'<text class="edge" x="{lx:.0f}" y="{ly:.0f}" font-size="9"'
                   f' font-weight="bold"'
                   f' fill="{colour if colour != "#B7B7B7" else "#607D8B"}"'
                   f' text-anchor="middle">{xml(label)}</text>')

    # row 1, the question. row 2, the pages the full-text index returned.
    box(MID, ROW[0], NARROW, "", "the question", "intraosseous systems", outline=True)
    for x, page in zip((LEFT, RIGHT), pages[:2]):
        shown = " ".join(page["text"].split()).upper()
        box(x, ROW[1], WIDE, "#ACDBF8",
            f"Page   PO {page['purchase_order']}  p{page['page']}",
            "names the department" if department.upper()[:16] in shown
            else "names neither the vendor nor the department")
    PAGES_AT = (LEFT + WIDE / 2, RIGHT + WIDE / 2)
    fan(ROW[0] + BH, ROW[1], PAGES_AT, "page_text")

    # rows 3 to 5, what stands between a page and its contract.
    box(MID, ROW[2], NARROW, "#CFD8DC", "Document", "one filing of one revision")
    box(MID, ROW[3], NARROW, "#CFD8DC", "ContractRecord",
        f"{graph['revisions']} revisions of this order")
    box(MID, ROW[4], NARROW, "#CFD8DC", "Contract", po)
    fan(ROW[2], ROW[1] + BH, PAGES_AT, "HAS_PAGE")
    arrow(SPINE, ROW[3], SPINE, ROW[2] + BH, "HAS_DOCUMENT")
    arrow(SPINE, ROW[3] + BH, SPINE, ROW[4], "INCLUDED_IN_CONTRACT")

    # row 6, the one hop that answers and the one that does not.
    box(LEFT, ROW[5], WIDE, "#ACDBF8", "Organization — on no page", vendor, orange=True)
    box(RIGHT, ROW[5], WIDE, "#CFD8DC", "Department", department)
    # Out of the contract's sides, not its bottom: the two boxes below are at
    # the margins, and the one hop that answers has to be seen leaving.
    elbow(MID, ROW[4] + BH / 2, LEFT + WIDE / 2, ROW[5], "HAS_VENDOR",
          colour="#FF9900")
    elbow(RIGHT + WIDE / 2, ROW[5], MID + NARROW, ROW[4] + BH / 2,
          "ASSIGNS_CONTRACT", up=True)
    svg.append('</svg>')
    return "\n".join(svg)


def text2cypher_picture(steps: list, *, width: float | None = None) -> str:
    """Every draft the repair loop wrote, and who objected to each.

    One row per draft, because the drafts are what this pipeline is about and a
    log of twenty lines hides them. What changes between the rows is usually one
    word -- the property the filter is on -- so the rows are aligned on it.

    LangGraph's palette, because this is a picture of a pipeline and not of the
    Chicago graph -- the two were the same until 5/11/2026.

    `steps` is `Answer.steps` as `text2cypher` returns it: the drafts in order,
    each with what the validator said, and the execution last. The drawing never
    reruns anything, so it cannot show a draft the pipeline did not write.
    """
    import re as _re

    drafts = [s for s in steps if str(s["tool"]).startswith("draft")]
    ran = next((s for s in steps if s["tool"] == "execute"), None)
    W, BH, ROWH = 1000, 40, 78
    H = 92 + len(drafts) * ROWH + (74 if ran else 0)

    svg = [frame(W, H, width), ARROW,
           f'<text x="{W / 2}" y="26" font-size="13" font-weight="bold"'
           f' fill="{FLOW["title"]}" text-anchor="middle">every draft, and what the'
           f' validator said about that draft</text>',
           f'<text x="{W / 2}" y="46" font-size="10" fill="{FLOW["edge"]}"'
           f' text-anchor="middle">the filter is the only thing that moves'
           f' between the rows</text>']

    for i, step in enumerate(drafts):
        y = 68 + i * ROWH
        query = " ".join(str(step["arguments"]).split())
        # The filter is what the loop is arguing about, so it is what the row
        # shows; the rest of the query is identical in every draft.
        held = _re.search(r"\{(\w+):\s*([^}]*)\}", query)
        filtre = f"{{{held.group(1)}: {held.group(2).strip()}}}" if held else query[:60]
        svg.append(f'<rect x="30" y="{y}" width="330" height="{BH}" rx="6"'
                   f' fill="{FLOW["node"]}" stroke="{FLOW["edge"]}" stroke-width="1.4"/>')
        svg.append(f'<text x="44" y="{y + 16}" font-size="9" fill="{FLOW["edge"]}">'
                   f'{xml(step["tool"])}</text>')
        svg.append(f'<text x="44" y="{y + 31}" font-size="11" font-weight="bold"'
                   f' fill="{FLOW["ink"]}">{xml(fit(filtre, 320, 11))}</text>')

        said = step["result"]
        objections = said if isinstance(said, list) else [str(said)]
        # Orange, because an objection the loop could not act on is the thing
        # that is missing: a correction that would have helped.
        quiet = not isinstance(said, list)
        svg.append(f'<text x="390" y="{y + 14}" font-size="9" font-weight="bold"'
                   f' fill="{FLOW["edge"] if quiet else FLOW["missing"]}">'
                   f'{"nothing objected" if quiet else "the model objects:"}</text>')
        for k, line in enumerate(objections[:2]):
            svg.append(f'<text x="390" y="{y + 28 + k * 13}" font-size="9"'
                       f' fill="{FLOW["ink"]}">{xml(fit(str(line), 600, 9))}</text>')
        if i:
            svg.append(f'<line x1="195" y1="{y - 38}" x2="195" y2="{y}"'
                       f' stroke="{FLOW["edge"]}" stroke-width="1.6"'
                       f' marker-end="url(#tip)"/>')
            svg.append(f'<text class="edge" x="205" y="{y - 20}" font-size="9"'
                       f' font-weight="bold" fill="{FLOW["edge"]}">correct</text>')

    if ran:
        y = 68 + len(drafts) * ROWH + 16
        svg.append(f'<rect x="30" y="{y}" width="330" height="{BH}" rx="6"'
                   f' fill="{FLOW["node"]}" stroke="{FLOW["missing"]}"'
                   f' stroke-width="2" stroke-dasharray="5 3"/>')
        svg.append(f'<text x="44" y="{y + 16}" font-size="9" fill="{FLOW["missing"]}">'
                   f'ran the last draft, out of corrections</text>')
        svg.append(f'<text x="44" y="{y + 31}" font-size="11" font-weight="bold"'
                   f' fill="{FLOW["missing"]}">{xml(fit(str(ran["result"]), 320, 11))}</text>')
        svg.append(f'<line x1="195" y1="{y - 22}" x2="195" y2="{y}"'
                   f' stroke="{FLOW["missing"]}" stroke-width="1.6" marker-end="url(#tip)"/>')
        svg.append(f'<text x="390" y="{y + 25}" font-size="10" font-weight="bold"'
                   f' fill="{FLOW["missing"]}">nothing approved this draft — the budget of'
                   f' two corrections ran out</text>')
    svg.append('</svg>')
    return "\n".join(svg)


def react_picture(trace: list, sent: int, *, width: float | None = None) -> str:
    """The agent's loop: the model on one side, the tools on the other.

    Two nodes and a cycle. `react.py` became a `StateGraph` on 5/11/2026 --
    `call_model` and `run_tools`, with a router on every edge -- so all four
    architectures are now graphs, and what singles this one out is not the
    absence of a framework: it is that its conditional edge is decided by the
    model rather than by the previous node's result.

    The picture is that shape with the calls that happened written into it,
    because the shape alone is the same for every question and the calls are
    not.

    LangGraph's palette, like the other pictures of programs.

    `trace` is `agent(...)["trace"]`; `sent` is its `sent`, the characters put
    in front of the model, which is the price of the route.
    """
    # 44-tall boxes on a 46-pixel pitch left two pixels between rows, so the
    # arrow from one step to the next was two pixels long and the rows read as
    # one block. The pitch is now the box plus a real gap.
    W, BH, GAP = 980, 44, 26
    H = 120 + len(trace) * (BH + GAP) + 30
    LX, RX, LW, RW = 40, 430, 330, 510

    svg = [frame(W, H, width), ARROW,
           f'<text x="{W / 2}" y="26" font-size="13" font-weight="bold"'
           f' fill="{FLOW["title"]}" text-anchor="middle">the model names a tool, the'
           f' tool runs, the result goes back — until it calls `answer`</text>']

    # the two sides of the loop, named once
    for x, w, label in ((LX, LW, "the model chooses"), (RX, RW, "the tool runs, here")):
        svg.append(f'<rect x="{x}" y="56" width="{w}" height="26" rx="6"'
                   f' fill="{FLOW["end"]}" stroke="{FLOW["edge"]}" stroke-width="1.4"/>')
        svg.append(f'<text x="{x + w / 2}" y="73" font-size="10"'
                   f' font-weight="bold" fill="{FLOW["ink"]}" text-anchor="middle">'
                   f'{xml(label)}</text>')

    for i, step in enumerate(trace):
        y = 94 + i * (BH + GAP)
        final = step["tool"] == "answer"
        svg.append(f'<rect x="{LX}" y="{y}" width="{LW}" height="{BH}" rx="6"'
                   f' fill="{FLOW["end"] if final else FLOW["node"]}" stroke="{FLOW["edge"]}"'
                   f' stroke-width="1.4"/>')
        svg.append(f'<text x="{LX + 14}" y="{y + 17}" font-size="9"'
                   f' fill="{FLOW["edge"]}">step {step["step"]}</text>')
        svg.append(f'<text x="{LX + 14}" y="{y + 32}" font-size="11"'
                   f' font-weight="bold" fill="{FLOW["ink"]}">{xml(step["tool"])}</text>')
        svg.append(f'<text x="{RX}" y="{y + 17}" font-size="9" fill="{FLOW["edge"]}">'
                   f'{xml(fit(str(step["args"]), RW, 9))}</text>')
        svg.append(f'<text x="{RX}" y="{y + 32}" font-size="9" fill="{FLOW["ink"]}">'
                   f'{xml(fit(" ".join(str(step["result"]).split()), RW, 9))}</text>')
        svg.append(f'<line x1="{LX + LW}" y1="{y + 22}" x2="{RX - 6}"'
                   f' y2="{y + 22}" stroke="{FLOW["edge"]}" stroke-width="1.4"'
                   f' marker-end="url(#tip)"/>')
        if i:
            svg += flow_edge(LX + LW / 2, y - GAP, LX + LW / 2, y)

    svg.append(f'<text x="{W / 2}" y="{H - 12}" font-size="10.5" fill="{FLOW["title"]}"'
               f' font-weight="bold" text-anchor="middle">{sent:,} characters put'
               f' in front of the model to get here</text>')
    svg.append('</svg>')
    return "\n".join(svg)
