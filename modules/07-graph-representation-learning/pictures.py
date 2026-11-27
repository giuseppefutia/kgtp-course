"""The drawings of module 7, kept out of the lesson.

    from pictures import club

The lesson calls these; it does not contain them. What a reader needs to see in
a cell is *which data* is being drawn, not the twenty lines of matplotlib that
place a label -- those are the same twenty lines every time, and in the notebook
they bury the one argument that changes.

Same arrangement as `pictures.py` in modules 5 and 6, with one difference: those
build SVG strings by hand, because the student environment had no matplotlib.
This module installs it, so the figures here are matplotlib and the drawings of
the graph itself stay SVG.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

# Module 1's colours, where the room met this graph: blue is Mr. Hi's faction,
# orange is the president's, pale grey the backdrop. A reader who learnt them
# there should not have to learn them twice.
BLUE = "#4986e8"
ORANGE = "#FFA500"
FADED = "#c2cedd"
INK = "#16212A"
UNKNOWN = "#B9C4CC"   # a side we were not told
# A dark red rather than a bright one: the ring has to read on top of an orange
# node as well as a blue one, and #FF0000 on #FFA500 is two oranges.
WRONG = "#B3261E"


def sides(y, known=None):
    """One colour per member, from a 0/1 array of factions.

    With `known`, the members whose side we were not told come out grey. The
    figure in the section that opens "four numbers per member" used to paint all
    thirty-four in their true colours while the text said we knew eight, which
    contradicted the page it sat on -- and invited the reader to think the
    colours were predictions.
    """
    if known is None:
        return [BLUE if side == 0 else ORANGE for side in y]
    return [(BLUE if side == 0 else ORANGE) if told else UNKNOWN
            for side, told in zip(y, known)]


def club(graph, pos, colours, title, *, ax=None, ring=(), wrong=(),
         members=None):
    """One picture of the club, coloured by whatever the caller passes in.

    `pos` arrives from outside rather than being computed here. The lesson draws
    this graph four times under four different colourings, and a layout
    recomputed per figure moves the nodes -- which reads as a different graph,
    the one thing these pictures must never suggest.

    `ring` outlines the members whose side the model was told. It is the only
    thing that separates the figures from each other besides the colours, and
    without it a reader cannot tell what the model was working from.

    `wrong` rings its members in red, a little thicker than the black of `ring`.
    The first version drew them as squares -- shape rather than colour, since
    colour already means a faction here -- and at 250 points a square and a
    circle are not told apart. The ring is the channel that reads.
    """
    members = list(graph.nodes()) if members is None else members
    outlined = set(ring)
    alone = ax is None
    if alone:
        _, ax = plt.subplots(figsize=(5.4, 4.2))
    missed = set(wrong)

    def ring_of(node):
        if node in missed:
            return WRONG, 2.6
        if node in outlined:
            return INK, 1.8
        return "white", 0.8

    rings = [ring_of(n) for n in members]
    nx.draw_networkx_edges(graph, pos, ax=ax, edge_color=FADED, width=1.0)
    nx.draw_networkx_nodes(
        graph, pos, ax=ax, node_color=colours, node_size=250,
        edgecolors=[c for c, _ in rings], linewidths=[w for _, w in rings])
    nx.draw_networkx_labels(graph, pos, ax=ax, font_size=6.5, font_color="white")
    ax.set_title(title, fontsize=10)
    ax.axis("off")
    if alone:
        plt.show()
    return ax


# The diverging ramp for a standardised value: cool for negative, warm for
# positive, near-white in the middle. Blue is the faction colour everywhere else
# in this module, so the figure that uses this ramp draws its nodes in grey --
# one hue cannot mean a side in one picture and a sign in the next.
#
# The warm pole is #CC7A00 and not the #FFA500 of the factions because the
# validator refuses that one on a white ground: lightness 0.79, contrast 1.97:1.
# #CC7A00 passes the band and the contrast, and the two poles still separate at
# dE 27.7 under protanopia -- well past the 8 that is the floor.
COLD = (0x49, 0x86, 0xE8)
WARM = (0xCC, 0x7A, 0x00)
MIDDLE = (0xF4, 0xF6, 0xF8)


def heat(value, span=2.5):
    """A cell's fill, from a standardised value. Clamped at +/- `span` sigma."""
    t = max(-1.0, min(1.0, value / span))
    pole = WARM if t > 0 else COLD
    k = abs(t)
    return "#%02X%02X%02X" % tuple(
        round(MIDDLE[i] + k * (pole[i] - MIDDLE[i])) for i in range(3))


def _cells(x, y, values, *, cell=44, high=26, decimals=1):
    """One rectangle of square-ish cells, the value written inside each.

    The number goes in the cell because the ramp alone cannot carry it: the warm
    pole sits at 4.4:1 against white and the pale middle at 1.1, so a reader
    cannot tell -0.2 from +0.2 by colour. With the number printed, colour is
    reinforcement and the cell is still readable in grayscale or in print.
    """
    out = []
    for i, v in enumerate(values):
        left = x + i * cell
        out.append(f'<rect x="{left}" y="{y}" width="{cell}" height="{high}" '
                   f'fill="{heat(float(v))}" stroke="#FFFFFF" stroke-width="1"/>')
        out.append(f'<text x="{left + cell / 2:.0f}" y="{y + high / 2 + 3.5:.0f}" '
                   f'text-anchor="middle" font-family="IBM Plex Mono, monospace" '
                   f'font-size="10" fill="{INK}">{float(v):+.{decimals}f}</text>')
    return "".join(out)


def _map_inset(graph, pos, member, friends, box):
    """The whole club, small, with the six nodes this figure is about picked out.

    Added on 19/11/2026 because the six rows on the right say which members are
    being mixed but not *where* they are: without the map a reader has to take
    on trust that 0 and 33 are the hubs, which is the one thing the weights are
    explained by.

    The layout is the lesson's own `pos`, scaled into the box rather than
    recomputed -- the same rule as every other figure here.
    """
    x0, y0, w, h = box
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    pad = 20

    def place(node):
        px, py = pos[node]
        fx = (px - min(xs)) / (max(xs) - min(xs) or 1)
        fy = (py - min(ys)) / (max(ys) - min(ys) or 1)
        # y flipped: spring_layout grows upward, SVG grows downward.
        return x0 + pad + fx * (w - 2 * pad), y0 + h - pad - fy * (h - 2 * pad)

    shown = {member, *friends}
    parts = [f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="#FBFCFD" '
             f'stroke="#E0E6EA" stroke-width="1" rx="4"/>']
    for u, v in graph.edges():
        ux, uy = place(u)
        vx, vy = place(v)
        both = u in shown and v in shown
        parts.append(f'<line x1="{ux:.1f}" y1="{uy:.1f}" x2="{vx:.1f}" '
                     f'y2="{vy:.1f}" stroke="{"#90A4AE" if both else "#E3E8EB"}" '
                     f'stroke-width="{1.4 if both else 0.8}"/>')
    for node in graph.nodes():
        cx, cy = place(node)
        if node == member:
            parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="10" '
                         f'fill="#607D8B" stroke="{INK}" stroke-width="2"/>')
            parts.append(f'<text x="{cx:.1f}" y="{cy + 3.5:.1f}" '
                         f'text-anchor="middle" font-size="9" font-weight="600" '
                         f'font-family="Archivo, system-ui, sans-serif" '
                         f'fill="#FFFFFF">{node}</text>')
        elif node in shown:
            parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="9" '
                         f'fill="#90A4AE" stroke="#FFFFFF" stroke-width="1.5"/>')
            parts.append(f'<text x="{cx:.1f}" y="{cy + 3.3:.1f}" '
                         f'text-anchor="middle" font-size="8.5" '
                         f'font-family="Archivo, system-ui, sans-serif" '
                         f'fill="#FFFFFF">{node}</text>')
        else:
            parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" '
                         f'fill="#CFD8DC" stroke="#FFFFFF" stroke-width="1"/>')
    return "".join(parts)


def forward_pass(member, friends, vectors, weights, mixed, output, *,
                 graph=None, pos=None,
                 columns=("degree", "eigen", "betwn", "close")):
    """One GCN layer on one member, drawn: mix the neighbours, then transform.

    Everything is passed in and nothing is recomputed here. The numbers in the
    picture are the numbers the cell above printed, so the drawing cannot drift
    from the table -- which is the only reason to trust a figure in a lesson.

    `vectors` is keyed by member id and `weights` likewise; `mixed` is the
    weighted average and `output` what the layer returned.
    """
    rows = [member] + list(friends)
    row_h, top = 46, 108
    inset = graph is not None and pos is not None
    shift = 300 if inset else 0
    # 940 e non 830: la striscia di uscita comincia a `out_x` ed e' larga tre
    # celle, quindi finisce a out_x + 132. Con 830 sbordava di 44 pixel, e nel
    # rendering non si vedeva -- il viewBox taglia in silenzio.
    width = 940 + shift
    height = max(top + row_h * len(rows) + 72, 416 if inset else 0)
    node_x = 62 + shift
    strip_x, mix_x, out_x = 104 + shift, 470 + shift, 742 + shift
    middle = top + row_h * len(rows) / 2 - 13

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
             f'width="100%" role="img">',
             f'<rect width="{width}" height="{height}" fill="#FFFFFF"/>']

    def label(x, y, text, *, size=11, anchor="start", colour=None, weight=400):
        return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" '
                f'font-family="Archivo, system-ui, sans-serif" font-weight="{weight}" '
                f'fill="{colour or INK}">{text}</text>')

    parts.append(label(30, 34, "One GCN layer on one member", size=14, weight=600))
    parts.append(label(30, 54, "mix the neighbours as a weighted average, "
                               "then transform — only the transform is learned",
                       size=11, colour="#5A7183"))
    # Le quattro colonne sono centralita' STANDARDIZZATE, non conteggi, e
    # l'intestazione `degree` lo faceva credere: il +0,11 del socio 13 e' cinque
    # amici contro una media di 4,6, non il numero cinque. Chiesto il 19/11/2026.
    parts.append(label(30, 70, "the four columns are standardised centralities, "
                               "not counts: 0 is the club average, 1 is a "
                               "standard deviation",
                       size=9.5, colour="#8A4B00"))
    if inset:
        parts.append(_map_inset(graph, pos, member, friends, (24, top - 34, 258, 290)))
        parts.append(label(153, top + 274, "the club; this figure mixes the six "
                                           "picked out", size=9, anchor="middle",
                           colour="#5A7183"))
    for i, name in enumerate(columns):
        parts.append(label(strip_x + i * 44 + 22, top - 10, name, size=9,
                           anchor="middle", colour="#5A7183"))
    # La formula sopra la colonna dei pesi, e sotto ogni peso la sua istanza coi
    # gradi veri. Chiesto il 19/11/2026: senza, quei numeri si leggono come
    # un'inizializzazione della matrice appresa, che e' l'unico fraintendimento
    # che questa figura esiste per impedire.
    parts.append(label(300 + shift, top - 22, "1 / \u221a(d \u00b7 d)", size=11,
                       weight=600))
    parts.append(label(300 + shift, top - 9, "from the graph, never learned",
                       size=9, colour="#5A7183"))
    parts.append(label(mix_x + 88, top - 10, "mixed", size=9, anchor="middle",
                       colour="#5A7183"))
    parts.append(label(out_x + 66, top - 10, "out", size=9, anchor="middle",
                       colour="#5A7183"))

    for i, node in enumerate(rows):
        y = top + i * row_h
        ring = INK if node == member else "#FFFFFF"
        parts.append(f'<circle cx="{node_x}" cy="{y + 13}" r="15" fill="#607D8B" '
                     f'stroke="{ring}" stroke-width="2"/>')
        parts.append(label(node_x, y + 17, str(node), size=11, anchor="middle",
                           colour="#FFFFFF", weight=600))
        parts.append(_cells(strip_x, y, vectors[node]))
        parts.append(label(300 + shift, y + 11, f"{weights[node]:.3f}", size=11,
                           colour=INK, weight=600))
        if graph is not None:
            # Il grado col cappio: e' quello che la formula usa, non il grado
            # nudo, e la differenza fra 5 e 6 qui cambia il numero.
            d_self = graph.degree(member) + 1
            d_other = graph.degree(node) + 1
            parts.append(label(300 + shift, y + 24,
                               f"1/\u221a({d_self}\u00b7{d_other})", size=9,
                               colour="#5A7183"))
        # Every row feeds the same mixer, so every arrow ends in the same place.
        parts.append(f'<path d="M {360 + shift} {y + 13} C {410 + shift} {y + 13}, '
                     f'{420 + shift} {middle + 13}, {mix_x - 14} {middle + 13}" '
                     f'fill="none" stroke="#B0BEC5" stroke-width="1.2"/>')

    parts.append(_cells(mix_x, middle, mixed))
    parts.append(f'<path d="M {mix_x + 182} {middle + 13} L {out_x - 70} '
                 f'{middle + 13}" stroke="#B0BEC5" stroke-width="1.2"/>')
    # Centrato fra la FINE del mescolato e l'INIZIO dell'uscita: calcolato
    # sull'inizio della freccia invece che sulla sua meta', `learned` sbavava
    # sull'ultima cella.
    fra = (mix_x + 176 + out_x) / 2
    parts.append(label(fra, middle + 6, "x W", size=11, anchor="middle"))
    parts.append(label(fra, middle + 22, "learned", size=9, anchor="middle",
                       colour="#5A7183"))
    parts.append(_cells(out_x, middle, output))

    parts.append(label(30, height - 36,
                       "cool = below the club average, warm = above, in "
                       "standard deviations.", size=10, colour="#5A7183"))
    parts.append(label(30, height - 20,
                       "Member 13's +0.11 under `degree` is five friends against "
                       "an average of 4.6 — not the number five.",
                       size=10, colour="#5A7183"))
    parts.append("</svg>")
    return "".join(parts)


# The module 4 and 5 palette, which a reader has been looking at for two
# sessions: pale grey is a structured record, slate is a resolved entity, blue is
# a title or a number, and orange is the thing that is NOT there.
STRUCTURED = "#CFD8DC"
ENTITY = "#607D8B"
TITLE = "#0091EA"
MISSING = "#FF9900"
UNUSED = "#ECEFF1"


def xml(text):
    """Escape for SVG. A business called `PCS Power & Communication Services`
    does not draw badly with a raw `&` -- it stops the whole image rendering."""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def fit(text, width, size=11):
    """Cut a string to what fits, at roughly 0.55 em per character."""
    room = max(1, int(width / (size * 0.55)))
    text = str(text)
    return text if len(text) <= room else text[:room - 1] + "…"


def chicago_schema(counts, instance):
    """What part of the graph this task reads, and one real owner inside it.

    Both arguments come from the cells above rather than being retyped, so the
    picture cannot drift from the numbers. `counts` is keyed by label;
    `instance` carries two owners of one business and the licence that decides
    their label.
    """
    width, height = 1120, 452
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
             f'width="100%" role="img">',
             f'<rect width="{width}" height="{height}" fill="#FFFFFF"/>']

    def text(x, y, body, *, size=11, anchor="start", colour=INK, weight=400,
             mono=False):
        family = ("IBM Plex Mono, monospace" if mono
                  else "Archivo, system-ui, sans-serif")
        return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" '
                f'font-family="{family}" font-weight="{weight}" fill="{colour}">'
                f'{xml(body)}</text>')

    def box(x, y, w, h, fill, label, note=None, *, ink=INK, dashed=False):
        out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" '
               f'fill="{fill}" stroke="{ENTITY}" stroke-width="1"'
               + (' stroke-dasharray="4 3"' if dashed else "") + '/>']
        out.append(text(x + w / 2, y + (20 if note else h / 2 + 4),
                        fit(label, w - 12), anchor="middle", weight=600,
                        colour=ink, size=11))
        if note:
            out.append(text(x + w / 2, y + 36, fit(note, w - 12, 9.5),
                            anchor="middle", size=9.5, colour=ink, mono=True))
        return "".join(out)

    def arrow(x1, y, x2, label=None, *, colour="#90A4AE", dashed=False):
        out = [f'<line x1="{x1}" y1="{y}" x2="{x2 - 7}" y2="{y}" stroke="{colour}" '
               f'stroke-width="1.3"'
               + (' stroke-dasharray="4 3"' if dashed else "") + '/>',
               f'<path d="M {x2 - 7} {y - 4} L {x2} {y} L {x2 - 7} {y + 4} z" '
               f'fill="{colour}"/>']
        if label:
            out.append(text((x1 + x2) / 2, y - 7, label, anchor="middle", size=9,
                            colour="#5A7183", mono=True))
        return "".join(out)

    # ---------------------------------------------------- band 1: the schema
    parts.append(text(28, 30, "Which part of the graph this task reads",
                      size=14, weight=600))
    parts.append(text(28, 50, "four public files became this graph in modules 3 "
                              "and 4; the owners half is what the task needs",
                      size=10.5, colour="#5A7183"))

    y = 70
    parts.append(box(28, y, 176, 52, STRUCTURED, "PersonRecord",
                     f"{counts['PersonRecord']:,} rows"))
    parts.append(arrow(204, y + 26, 248, "RESOLVED_TO"))
    parts.append(box(248, y, 150, 52, ENTITY, "Person",
                     f"{counts['Person']:,} people", ink="#FFFFFF"))
    parts.append(arrow(398, y + 26, 452, "owns"))
    parts.append(box(452, y, 176, 52, ENTITY, "Organization",
                     f"{counts['Organization']:,} businesses", ink="#FFFFFF"))
    parts.append(arrow(628, y + 26, 682, "HAS_LICENSE"))
    parts.append(box(682, y, 176, 52, STRUCTURED, "LicenseRecord",
                     f"{counts['LicenseRecord']:,} licences"))

    parts.append(text(323, y + 76, "module 4 built this node; without it an "
                                   "owner is a string on a row",
                      size=9.5, anchor="middle", colour=TITLE))
    parts.append(text(770, y + 76, "dates here make the label", size=9.5,
                      anchor="middle", colour=TITLE))

    parts.append(box(888, y, 204, 52, UNUSED, "Document, Page",
                     f"{counts['Document']:,} of {counts['ContractRecord']:,} "
                     f"contracts", ink="#78909C", dashed=True))
    parts.append(text(990, y + 76, "not read by this task", size=9.5,
                      anchor="middle", colour="#90A4AE"))

    # ---------------------------------------------------- band 2: one owner
    top = 212
    parts.append(f'<line x1="28" y1="{top - 18}" x2="{width - 28}" '
                 f'y2="{top - 18}" stroke="#E0E6EA" stroke-width="1"/>')
    parts.append(text(28, top + 4, "One business, two owners, one event",
                      size=14, weight=600))
    parts.append(text(28, top + 24, "the register says what each owner holds. "
                                    "Whether they started something next is the "
                                    "question.", size=10.5, colour="#5A7183"))

    shop_y = top + 92
    parts.append(box(392, shop_y, 230, 52, ENTITY, instance["business"],
                     f"licence started {instance['started']}", ink="#FFFFFF"))
    parts.append(box(682, shop_y, 196, 52, STRUCTURED, "LicenseRecord",
                     instance["started"]))
    parts.append(arrow(622, shop_y + 26, 682, "HAS_LICENSE"))

    for i, who in enumerate(instance["owners"]):
        oy = top + 52 + i * 80
        known = who["known"]
        parts.append(box(28, oy, 230, 52, ENTITY,
                         who["name"], who["title"], ink="#FFFFFF"))
        parts.append(arrow(258, oy + 26, 392, "owns"))
        tag_x, tag_y = 904, oy + 8
        parts.append(f'<rect x="{tag_x}" y="{tag_y}" width="188" height="36" rx="4" '
                     f'fill="{"#E8F5E9" if known else "#FFF4E0"}" '
                     f'stroke="{ENTITY if known else MISSING}" stroke-width="1.4"/>')
        parts.append(text(tag_x + 94, tag_y + 23,
                          "label 1 — on record" if known
                          else "label ? — to fill in",
                          anchor="middle", size=10.5, weight=600,
                          colour=INK if known else "#8A4B00"))
        parts.append(f'<line x1="878" y1="{shop_y + 26}" x2="{tag_x - 6}" '
                     f'y2="{tag_y + 18}" stroke="#B0BEC5" stroke-width="1.1" '
                     f'stroke-dasharray="3 3"/>')

    parts.append(text(28, height - 16,
                      "Both labels come from the same licence. That is the whole "
                      "difficulty of the two sections after this one.",
                      size=10, colour=MISSING, weight=600))
    parts.append("</svg>")
    return "".join(parts)


OBSERVED = "#ACDBF8"      # module 4's pale blue: what the model may read
ASKED = "#FFE2B8"         # a pale warm band: the window the label comes from

FIRST_YEAR, OBSERVE_TO, ASK_FROM, ASK_TO = 2000, 2015, 2018, 2021


def _year_scale(x0, x1):
    """Pixels per year, shared by every figure that draws this timeline."""
    span = ASK_TO - FIRST_YEAR
    return lambda year: x0 + (year - FIRST_YEAR) * (x1 - x0) / span


def _svg(width, height, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="100%" role="img">'
            f'<rect width="{width}" height="{height}" fill="#FFFFFF"/>'
            + "".join(body) + "</svg>")


def _t(x, y, body, *, size=11, anchor="start", colour=INK, weight=400, mono=False):
    family = "IBM Plex Mono, monospace" if mono else "Archivo, system-ui, sans-serif"
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" '
            f'font-family="{family}" font-weight="{weight}" fill="{colour}">'
            f'{xml(body)}</text>')


def _box(x, y, w, h, fill, label, note=None, *, ink=INK, dashed=False, lines=()):
    """A labelled box. `lines` go under the title, and when there are any the
    title moves to the top -- a centred title with three lines under it printed
    the title on top of the first one, which is how this grew the parameter."""
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="{fill}" '
           f'stroke="{ENTITY}" stroke-width="1"'
           + (' stroke-dasharray="4 3"' if dashed else "") + "/>"]
    stacked = bool(note) or bool(lines)
    out.append(_t(x + w / 2, y + (19 if stacked else h / 2 + 4), fit(label, w - 12),
                  anchor="middle", weight=600, colour=ink))
    if note:
        out.append(_t(x + w / 2, y + 34, fit(note, w - 12, 9.5), anchor="middle",
                      size=9.5, colour=ink, mono=True))
    for i, line in enumerate(lines):
        out.append(_t(x + w / 2, y + 36 + i * 15, fit(line, w - 12, 10),
                      anchor="middle", size=10, colour=ink, mono=True))
    return "".join(out)


def _arrow(x1, y, x2, label=None, *, colour="#90A4AE", dashed=False):
    out = [f'<line x1="{x1}" y1="{y}" x2="{x2 - 7}" y2="{y}" stroke="{colour}" '
           f'stroke-width="1.3"' + (' stroke-dasharray="4 3"' if dashed else "") + "/>",
           f'<path d="M {x2 - 7} {y - 4} L {x2} {y} L {x2 - 7} {y + 4} z" '
           f'fill="{colour}"/>']
    if label:
        out.append(_t((x1 + x2) / 2, y - 7, label, anchor="middle", size=9,
                      colour="#5A7183", mono=True))
    return "".join(out)


def chicago_task(counts):
    """The task in one picture: which nodes it reads, and which years.

    Replaces the two separate drawings this section had on 19/11/2026 -- one of
    the schema and one of an instance. Two schema pictures in a row made the
    reader look for a difference between them that was not there.

    It carried a dashed `Document, Page` box saying those nodes are not read.
    Dropped on 19/11/2026: declaring what a figure leaves out asks the reader
    why those nodes exist, which is a question about module 5 and not about this
    task.
    """
    width, height = 900, 448
    body = [_t(28, 30, "The task", size=15, weight=600),
            _t(28, 50, "which nodes it reads, and which years it may read them "
                       "from", size=10.5, colour="#5A7183")]

    y = 74
    # Riquadri da 140 e frecce da 76: `RESOLVED_TO` a corpo 9 e' larga 54 px e
    # con frecce da 46 finiva sopra i riquadri da entrambi i lati.
    body.append(_box(28, y, 140, 50, STRUCTURED, "PersonRecord",
                     f"{counts['PersonRecord']:,}"))
    body.append(_arrow(168, y + 25, 244, "RESOLVED_TO"))
    body.append(_box(244, y, 140, 50, ENTITY, "Person", f"{counts['Person']:,}",
                     ink="#FFFFFF"))
    body.append(_arrow(384, y + 25, 460, "owns"))
    body.append(_box(460, y, 140, 50, ENTITY, "Organization",
                     f"{counts['Organization']:,}", ink="#FFFFFF"))
    body.append(_arrow(600, y + 25, 676, "HAS_LICENSE"))
    body.append(_box(676, y, 140, 50, STRUCTURED, "LicenseRecord",
                     f"{counts['LicenseRecord']:,}"))
    body.append(_t(314, y + 72, "the node module 4 resolved: without it an owner "
                                "is a string on a row", size=9.5, anchor="middle",
                  colour=TITLE))
    body.append(_t(746, y + 72, "every date comes from here", size=9.5,
                   anchor="middle", colour=TITLE))

    # ----------------------------------------------------------- the clock
    top = 212
    body.append(f'<line x1="28" y1="{top}" x2="{width - 28}" y2="{top}" '
                f'stroke="#E0E6EA" stroke-width="1"/>')
    body.append(_t(28, top + 26, "Two windows, and the gap between them is "
                                 "deliberate", size=13, weight=600))

    axis_y = top + 92
    x0, x1 = 60, width - 60
    at_year = _year_scale(x0, x1)
    body.append(f'<rect x="{at_year(FIRST_YEAR)}" y="{axis_y - 26}" '
                f'width="{at_year(OBSERVE_TO) - at_year(FIRST_YEAR)}" height="52" '
                f'rx="3" fill="{OBSERVED}"/>')
    body.append(f'<rect x="{at_year(ASK_FROM)}" y="{axis_y - 26}" '
                f'width="{at_year(ASK_TO) - at_year(ASK_FROM)}" height="52" '
                f'rx="3" fill="{ASKED}"/>')
    body.append(f'<line x1="{x0}" y1="{axis_y + 26}" x2="{x1}" y2="{axis_y + 26}" '
                f'stroke="{ENTITY}" stroke-width="1"/>')
    for year in range(FIRST_YEAR, ASK_TO + 1):
        tick = at_year(year)
        every = year % 5 == 0 or year in (OBSERVE_TO, ASK_FROM, ASK_TO)
        body.append(f'<line x1="{tick}" y1="{axis_y + 26}" x2="{tick}" '
                    f'y2="{axis_y + (33 if every else 30)}" stroke="{ENTITY}" '
                    f'stroke-width="{1.2 if every else 0.7}"/>')
        if every:
            body.append(_t(tick, axis_y + 46, year, size=9.5, anchor="middle",
                           colour="#5A7183", mono=True))

    mid_obs = (at_year(FIRST_YEAR) + at_year(OBSERVE_TO)) / 2
    mid_ask = (at_year(ASK_FROM) + at_year(ASK_TO)) / 2
    body.append(_t(mid_obs, axis_y - 4, "everything the model reads", size=11.5,
                   anchor="middle", weight=600))
    body.append(_t(mid_obs, axis_y + 14, "titles, counts, dates, sector",
                   size=9.5, anchor="middle", colour="#37474F"))
    # Sotto gli anni e non dentro la banda: la banda copre tre anni su ventuno,
    # cioe' 111 px, e queste due righe sono larghe 140.
    body.append(f'<line x1="{mid_ask}" y1="{axis_y + 28}" x2="{mid_ask}" '
                f'y2="{axis_y + 60}" stroke="{MISSING}" stroke-width="1.2"/>')
    body.append(_t(mid_ask, axis_y + 74, "the one bit it must guess", size=11.5,
                   anchor="middle", weight=600, colour="#8A4B00"))
    body.append(_t(mid_ask, axis_y + 90, "a new licence: yes or no", size=9.5,
                   anchor="middle", colour="#8A4B00"))
    gap = (at_year(OBSERVE_TO) + at_year(ASK_FROM)) / 2
    body.append(_t(gap, axis_y - 36, "2016-17", size=9, anchor="middle",
                   colour="#90A4AE", mono=True))
    body.append(_t(gap, axis_y + 2, "neither", size=9, anchor="middle",
                   colour="#90A4AE"))

    return _svg(width, height, body)


def owner_timelines(owners):
    """Three owners, their filings, and the one that is hidden.

    `owners` carries, per person, the years she filed and what happened in the
    window: `kept`, `quiet`, or `None` for the one the model is asked about.
    """
    row_h = 84
    width, height = 1120, 110 + row_h * len(owners) + 30
    x0, x1 = 300, width - 60
    at_year = _year_scale(x0, x1)
    body = [_t(28, 30, "Three owners up to 2015, and what came after",
               size=15, weight=600),
            _t(28, 50, "same cadence on the left; the question is the band on "
                       "the right", size=10.5, colour="#5A7183")]

    head = 86
    body.append(f'<rect x="{at_year(FIRST_YEAR)}" y="{head - 14}" '
                f'width="{at_year(OBSERVE_TO) - at_year(FIRST_YEAR)}" '
                f'height="{row_h * len(owners) + 18}" fill="{OBSERVED}" '
                f'opacity="0.45" rx="3"/>')
    body.append(f'<rect x="{at_year(ASK_FROM)}" y="{head - 14}" '
                f'width="{at_year(ASK_TO) - at_year(ASK_FROM)}" '
                f'height="{row_h * len(owners) + 18}" fill="{ASKED}" '
                f'opacity="0.55" rx="3"/>')
    body.append(_t((at_year(FIRST_YEAR) + at_year(OBSERVE_TO)) / 2, head - 22,
                   "observed", size=9.5, anchor="middle", colour="#37474F"))
    body.append(_t((at_year(ASK_FROM) + at_year(ASK_TO)) / 2, head - 22, "asked",
                   size=9.5, anchor="middle", colour="#8A4B00"))

    for i, who in enumerate(owners):
        y = head + 18 + i * row_h
        body.append(_t(28, y - 2, who["name"], size=12, weight=600))
        body.append(_t(28, y + 15, f"{who['businesses']} business"
                                   f"{'es' if who['businesses'] > 1 else ''}, "
                                   f"{who['records']} record"
                                   f"{'s' if who['records'] > 1 else ''} resolved "
                                   f"into one", size=9.5, colour="#5A7183"))
        body.append(f'<line x1="{x0}" y1="{y + 6}" x2="{x1}" y2="{y + 6}" '
                    f'stroke="#CFD8DC" stroke-width="1"/>')
        for year in who["before"]:
            body.append(f'<circle cx="{at_year(year)}" cy="{y + 6}" r="5" '
                        f'fill="{ENTITY}" stroke="#FFFFFF" stroke-width="1.2"/>')
        if who["answer"] is None:
            body.append(_t((at_year(ASK_FROM) + at_year(ASK_TO)) / 2, y + 12,
                           "?", size=26, anchor="middle", colour=MISSING,
                           weight=600))
            body.append(_t((at_year(ASK_FROM) + at_year(ASK_TO)) / 2, y + 30,
                           "hidden from the model", size=9, anchor="middle",
                           colour="#8A4B00"))
        else:
            for year in who["window"]:
                body.append(f'<circle cx="{at_year(year)}" cy="{y + 6}" r="5" '
                            f'fill="{TITLE}" stroke="#FFFFFF" stroke-width="1.2"/>')
            body.append(_t(28, y + 30, who["answer"], size=10, weight=600,
                           colour="#37474F"))
        if not who["window"] and who["answer"] is not None:
            # Sotto la linea della cronologia e non a cavallo: a `y + 11` la
            # linea, che passa a `y + 6`, le attraversava la parola.
            body.append(_t((at_year(ASK_FROM) + at_year(ASK_TO)) / 2, y + 22,
                           "nothing", size=10, anchor="middle", colour="#8A4B00"))

    for year in (FIRST_YEAR, 2005, 2010, OBSERVE_TO, ASK_FROM, ASK_TO):
        body.append(_t(at_year(year), height - 14, year, size=9.5,
                       anchor="middle", colour="#5A7183", mono=True))
    return _svg(width, height, body)


def _brace(x0, x1, y, label, note, colour):
    """A horizontal brace under a run of columns, with its name under it.

    Added on 19/11/2026: the figure said "her own columns" and "a business's
    columns" and that was not enough -- fifty-two squares in a row need to be
    told apart by what they mean, not by which half they are in.
    """
    mid = (x0 + x1) / 2
    return ("".join([
        f'<path d="M {x0} {y} L {x0} {y + 5} L {x1} {y + 5} L {x1} {y}" '
        f'fill="none" stroke="{colour}" stroke-width="1.2"/>',
        f'<line x1="{mid}" y1="{y + 5}" x2="{mid}" y2="{y + 10}" '
        f'stroke="{colour}" stroke-width="1.2"/>',
        _t(mid, y + 24, label, size=10.5, anchor="middle", weight=600,
           colour=colour),
        _t(mid, y + 38, note, size=9, anchor="middle", colour="#5A7183"),
    ]))


def message_passing(person, rows, columns, *, business, groups, rounds=3):
    """One owner's row before and after message passing, and what arrived.

    The companion of `forward_pass` on the karate club, on the other graph: there
    the point was that mixing is a weighted average, here it is what the mixing
    *moves*. An owner's row is zeros wherever a business's columns are, and one
    round fills them in.

    `groups` is the categories, as (first column, last column, name, note), and
    it is passed in rather than inferred: a figure that guesses where the title
    block ends is a figure that silently mislabels it the day a title is added.
    """
    cell, high = 19, 22
    left, top = 150, 176
    width = max(1040, left + cell * len(columns) + 60)
    height = 496
    body = [_t(28, 32, "What one round of message passing moves", size=15,
               weight=600),
            _t(28, 52, f"{person}, who owns {business}. One square per column, "
                       f"{len(columns)} of them.", size=10.5, colour="#5A7183")]

    # Le graffe sopra le strisce, una per categoria, su due livelli alternati:
    # "what she owns" copre quattro colonne, cioe' 76 px, e la sua etichetta e'
    # larga 80 -- a un livello solo finiva sopra quella accanto.
    for n, (first, last, name, note) in enumerate(groups):
        x0 = left + first * cell
        x1 = left + (last + 1) * cell - 1
        kind = TITLE if first >= 27 else ENTITY
        mid = (x0 + x1) / 2
        alto = n % 2 == 1
        base = top - 14
        testa = top - (66 if alto else 36)
        body.append(f'<path d="M {x0} {base} L {x0} {base - 5} '
                    f'L {x1} {base - 5} L {x1} {base}" fill="none" '
                    f'stroke="{kind}" stroke-width="1.2"/>')
        # Il richiamo si fermava a `testa + 6` e la nota sta a `testa + 14`:
        # la linea le passava in mezzo. Qui arriva sotto la nota, e al livello
        # basso non si disegna affatto -- fra la graffa e la scritta non ci sono
        # i quattro pixel che lo renderebbero leggibile, e la graffa sta comunque
        # subito sotto il suo nome.
        if base - 5 - (testa + 22) >= 4:
            body.append(f'<line x1="{mid}" y1="{base - 5}" x2="{mid}" '
                        f'y2="{testa + 22}" stroke="{kind}" stroke-width="1"/>')
        body.append(_t(mid, testa, name, size=10.5, anchor="middle",
                       weight=600, colour=kind))
        body.append(_t(mid, testa + 14, note, size=9, anchor="middle",
                       colour="#5A7183"))

    def strip(y, values, label, note):
        out = [_t(28, y + 14, label, size=11.5, weight=600),
               _t(28, y + 30, note, size=9.5, colour="#5A7183")]
        for i, v in enumerate(values):
            x = left + i * cell
            filled = abs(float(v)) > 1e-6
            out.append(f'<rect x="{x}" y="{y}" width="{cell - 1}" '
                       f'height="{high}" rx="1.5" '
                       f'fill="{heat(float(v)) if filled else "#F7F9FA"}" '
                       f'stroke="#FFFFFF" stroke-width="0.8"/>')
            if filled:
                out.append(_t(x + (cell - 1) / 2, y + high / 2 + 3.2,
                              f"{float(v):.2f}".lstrip("0") or "0",
                              size=6.6, anchor="middle", colour=INK, mono=True))
        return "".join(out)

    before, after = np.asarray(rows["before"]), np.asarray(rows["after"])
    arrived = [i for i in range(len(columns))
               if abs(before[i]) < 1e-6 <= abs(after[i])]

    body.append(strip(top, before, "before",
                      "her row, straight from the register"))
    # Fra le due strisce e non a sinistra di esse: a sinistra la freccia passava
    # sopra la nota "her row, straight from the register", che e' larga 180 px.
    body.append(_t(left, top + 48, "+ the average of her neighbours", size=10,
                   colour="#5A7183"))
    after_y = top + 72
    body.append(strip(after_y, after, "after one round",
                      f"{len(arrived)} columns that were empty are not now"))

    # Una riga sola coi nomi, non una tacca per colonna: le colonne arrivate sono
    # adiacenti a 19 px l'una dall'altra e un nome come `licences/50` e' largo il
    # triplo, cosi' le tacche finivano sopra le etichette vicine.
    if arrived:
        x0 = left + arrived[0] * cell
        x1 = left + (arrived[-1] + 1) * cell - 1
        body.append(f'<path d="M {x0} {after_y + 26} L {x0} {after_y + 32} '
                    f'L {x1} {after_y + 32} L {x1} {after_y + 26}" fill="none" '
                    f'stroke="{MISSING}" stroke-width="1.6"/>')
        body.append(_t(x0, after_y + 50,
                       "arrived: " + ", ".join(columns[i] for i in arrived),
                       size=10, colour="#8A4B00", weight=600, mono=True))

    body.append(_t(28, height - 44,
                   "Three rounds, so she reaches her businesses, then her "
                   "co-owners, then their businesses.", size=10,
                   colour="#5A7183"))
    body.append(_t(28, height - 28,
                   "Her own degree — how many she holds — never moves: every "
                   "model in the table below has it already.", size=10,
                   colour="#5A7183"))
    return _svg(width, height, body)


def training_loop(shape, *, layers, reach):
    """One epoch, and which rows are allowed to touch what.

    `layers` is passed in and not written into the drawing: it said "3 rounds"
    as a string while the network held its own number, and the two would have
    drifted in silence the first time the network changed.

    `reach` names what each layer arrives at -- one line per layer. It is the
    whole reason the layer count matters, and in this graph it is not obvious:
    the owners are a bipartite graph, so a co-owner is two layers away and never
    one.

    The figure exists for one sentence that is easy to say and hard to believe:
    the whole graph goes through every forward pass -- every node's columns and
    every edge, test rows included -- and only the training *labels* enter the
    loss. Written down it sounds like cheating; drawn, it is obviously the only
    thing a graph model could do.
    """
    width, height = 1120, 420
    body = [_t(28, 30, "One epoch", size=15, weight=600),
            _t(28, 50, "the whole graph goes in; only the training labels come "
                       "out as a loss", size=10.5, colour="#5A7183")]

    graph_y = 92
    body.append(_box(28, graph_y, 212, 92, OBSERVED, "the whole graph",
                     lines=[f"{shape['nodes']:,} nodes",
                            f"{shape['edges']:,} directed edges",
                            f"{shape['columns']} columns each"]))
    body.append(_arrow(240, graph_y + 46, 322, f"{layers} layers"))
    body.append(_box(322, graph_y, 186, 92, "#F4F6F8", "message passing",
                     lines=["mix the neighbours,", "then transform",
                            f"{layers}x — once per layer"]))
    body.append(_arrow(508, graph_y + 46, 590, None))
    body.append(_box(590, graph_y, 186, 92, "#F4F6F8", "one score per node",
                     lines=[f"{shape['nodes']:,} of them,",
                            "most of which we ignore"]))

    # One line per layer: a layer is a hop, and on a bipartite graph the hops
    # land alternately on a business and on a person.
    reach_y = graph_y + 118
    body.append(_t(28, reach_y, "one layer is one hop", size=11.5, weight=600))
    for n, where in enumerate(reach, start=1):
        y = reach_y + 18 + (n - 1) * 17
        body.append(f'<circle cx="38" cy="{y - 4}" r="8" fill="{ENTITY}"/>')
        body.append(_t(38, y - 0.5, n, size=9.5, anchor="middle",
                       colour="#FFFFFF", weight=600))
        body.append(_t(54, y, where, size=10, colour="#37474F"))

    # ------------------------------------------------- who touches what
    rows = [("training rows", shape["train"], "enter the loss", ENTITY, "#FFFFFF"),
            ("validation rows", shape["valid"], "pick the epoch", OBSERVED, INK),
            ("test rows", shape["test"], "read once, at the end", ASKED, INK)]
    for i, (name, count, does, fill, ink) in enumerate(rows):
        y = graph_y + 8 + i * 48
        body.append(f'<rect x="{830}" y="{y}" width="{262}" height="38" rx="4" '
                    f'fill="{fill}" stroke="{ENTITY}" stroke-width="1"/>')
        body.append(_t(844, y + 17, name, size=11, weight=600, colour=ink))
        body.append(_t(844, y + 31, f"{count:,} owners — {does}", size=9.5,
                       colour=ink, mono=True))
        body.append(f'<path d="M 776 {graph_y + 46} C 800 {graph_y + 46}, '
                    f'806 {y + 19}, 830 {y + 19}" fill="none" stroke="#B0BEC5" '
                    f'stroke-width="1.1"/>')

    # ------------------------------------------------- the gradient's way back
    back_y = 318
    # A sinistra dei tre blocchetti (che iniziano a 830) e non dentro: passava
    # sopra "validation rows", "test rows" e i loro conteggi.
    body.append(f'<path d="M 816 {graph_y + 27} L 816 {back_y} L 415 {back_y} '
                f'L 415 {graph_y + 100}" fill="none" stroke="{MISSING}" '
                f'stroke-width="1.6" stroke-dasharray="5 4"/>')
    body.append(f'<path d="M 411 {graph_y + 107} L 415 {graph_y + 100} '
                f'L 419 {graph_y + 107} z" fill="{MISSING}"/>')
    # Su due righe, ancorata a sinistra, e **sopra** la gamba orizzontale: su
    # una riga sola e centrata arrivava a 817 e toccava il tratto verticale che
    # scende a 816; a cavallo di `back_y` la gamba orizzontale le attraversava
    # entrambe. Sopra, le due righe stanno fra i salti (che finiscono a 262) e
    # la gamba (318), e non tocca nulla.
    body.append(_t(430, back_y - 32, "the loss on those rows,", size=10.5,
                   colour="#8A4B00", weight=600))
    body.append(_t(430, back_y - 16, "and the only thing it changes: the matrices",
                   size=10.5, colour="#8A4B00", weight=600))

    body.append(_t(28, height - 16,
                   "Every node's columns and every edge are in every pass, test "
                   "rows included — a graph model cannot look at part of a graph. "
                   "What it never sees is a test owner's answer.",
                   size=10, colour="#5A7183"))
    return _svg(width, height, body)


def two_splits(pair, counts):
    """The same two owners under the two splits. The figure the section turns on.

    `pair` is one business and the two owners whose label is the same licence;
    `counts` how many such pairs each split cuts. Orange is the edge that should
    not be there -- the convention since module 4.
    """
    width, height = 1040, 332
    body = [_t(28, 30, "The same two owners, split two ways", size=15,
               weight=600),
            _t(28, 50, f"{pair['business']} took one licence, on "
                       f"{pair['started']}. Both owners are labelled 1 by that "
                       f"one licence.", size=10.5, colour="#5A7183")]

    def panel(x0, title, note, divided, cut):
        out = [f'<rect x="{x0}" y="78" width="470" height="196" rx="5" '
               f'fill="#FCFDFD" stroke="{MISSING if divided else "#E0E6EA"}" '
               f'stroke-width="{1.8 if divided else 1}"/>',
               _t(x0 + 18, 102, title, size=12.5, weight=600,
                  colour="#8A4B00" if divided else INK),
               _t(x0 + 18, 118, note, size=9.5, colour="#5A7183")]
        # L'impresa a destra e non al centro del riquadro: centrata a `x0 + 235`
        # il suo bordo sinistro cadeva a `x0 + 150`, cioe' DIETRO il bordo
        # destro dei titolari (`x0 + 168`), e l'arco doveva tornare indietro --
        # rientrando nel riquadro proprio dove sta scritto il nome.
        shop_y, mid = 196, x0 + 340
        out.append(_box(mid - 85, shop_y - 18, 170, 38, ENTITY,
                        fit(pair["business"], 158), ink="#FFFFFF"))
        for i, (who, side) in enumerate(zip(pair["owners"], divided or ("train", "train"))):
            y = 150 + i * 72
            fill = OBSERVED if side == "train" else ASKED
            out.append(f'<rect x="{x0 + 18}" y="{y - 16}" width="150" height="34" '
                       f'rx="4" fill="{fill}" stroke="{ENTITY}" stroke-width="1"/>')
            out.append(_t(x0 + 28, y - 2, fit(who["name"], 130), size=10,
                          weight=600))
            out.append(_t(x0 + 28, y + 12, f"{side} — label 1", size=9,
                          colour="#8A4B00" if side == "test" else "#37474F"))
            colour = MISSING if (divided and side == "test") else "#B0BEC5"
            out.append(f'<path d="M {x0 + 168} {y} C {x0 + 210} {y}, '
                       f'{x0 + 215} {shop_y}, {mid - 85} {shop_y}" fill="none" '
                       f'stroke="{colour}" stroke-width="{2 if colour == MISSING else 1.2}"/>')
        out.append(_t(x0 + 235, 292, cut, size=10.5, anchor="middle",
                      weight=600, colour="#8A4B00" if divided else "#37474F"))
        return "".join(out)

    body.append(panel(28, "random split", "the way everybody splits",
                      ("train", "test"),
                      f"{counts['random']:,} such pairs cut, per draw"))
    body.append(panel(542, "split by component",
                      "owners who share a business stay together", None,
                      f"{counts['component']:,} cut"))
    body.append(_t(28, height - 14,
                   "On the left the model is shown the answer under another "
                   "name. On the right it is not.", size=10.5,
                   colour="#8A4B00", weight=600))
    return _svg(width, height, body)


# Una rampa a una tinta per una grandezza, dal chiaro allo scuro. Non la rampa
# divergente di `heat`: queste colonne stanno tutte in [0, 1] e un segno non ce
# l'hanno, quindi due poli direbbero una cosa che il dato non dice.
def _mag(v):
    """A value in [0, 1] to a step of one hue, light to dark.

    Floors at a quarter of the way up: a column that is present but small --
    `recent = 1/10` -- has to read as present, and at the very bottom of the
    ramp it is indistinguishable from the empty cells next to it.
    """
    t = 0.25 + 0.75 * max(0.0, min(1.0, float(v)))
    return "#%02X%02X%02X" % tuple(
        round(lo + (hi - lo) * t)
        for lo, hi in ((0xEC, 0x2C), (0xF1, 0x5F), (0xF5, 0x7C)))


def _band(body, y, number, title):
    """A numbered band heading with a hairline over it."""
    body.append(f'<line x1="28" y1="{y - 18}" x2="1212" y2="{y - 18}" '
                f'stroke="#E0E6EA" stroke-width="1"/>')
    body.append(_t(28, y, f"{number}", size=13, weight=600, colour="#8FA6B4",
                   mono=True))
    body.append(_t(48, y, title.upper(), size=9.5, weight=600, colour="#8FA6B4"))


def _strip(body, x, y, values, *, cell=10.4, high=20):
    """One node's row of the feature matrix, one square per column."""
    for i, v in enumerate(values):
        body.append(f'<rect x="{x + i * cell:.1f}" y="{y}" '
                    f'width="{cell - 1:.1f}" height="{high}" rx="1" '
                    f'fill="{_mag(v) if abs(float(v)) > 1e-6 else "#F7F9FA"}" '
                    f'stroke="#FFFFFF" stroke-width="0.6"/>')


def neo4j_to_pyg(shape, sample):
    """From the graph in the database to the three tensors a network is handed.

    Rewritten on 26/11/2026. The first version drew the *shapes* of `x`,
    `edge_index` and `y` -- a box saying "2 x 575,034" -- and the shapes are the
    one part of this step nobody gets wrong. What goes wrong is the bookkeeping
    in the middle, so the figure now carries the actual integers: which row this
    owner became, which row her business became, what her fifty-two numbers
    look like, and the two columns of `edge_index` that are her one edge written
    both ways.

    `sample` is one real owner, pulled by cluster id, with her own row out of
    `features` -- so every number on the drawing is read from the arrays the
    next cell trains on, and none of it is typed in here.
    """
    width, height = 1240, 712
    body = [_t(28, 30, "From Neo4j to PyG", size=15, weight=600),
            _t(28, 50, "two queries, and then bookkeeping: a node stops being "
                       "an id and becomes a row", size=10.5, colour="#5A7183")]

    # ------------------------------------- 1: the graph, and the two queries
    _band(body, 92, "1", "the graph, and what the two queries return")
    body.append(_box(28, 110, 176, 42, ENTITY, fit(sample["owner"], 162),
                     f"Person · {sample['title']}", ink="#FFFFFF"))
    body.append(_box(28, 170, 176, 42, ENTITY, fit(sample["co_owner"], 162),
                     "Person · the other owner", ink="#FFFFFF"))
    body.append(_box(224, 140, 168, 42, ENTITY, fit(sample["business"], 154),
                     "Organization", ink="#FFFFFF"))
    body.append(_box(224, 222, 168, 38, STRUCTURED, "LicenseRecord",
                     sample["started"]))
    for y in (131, 191):
        body.append(f'<path d="M 204 {y} C 214 {y}, 214 161, 224 161" '
                    f'fill="none" stroke="#90A4AE" stroke-width="1.3"/>')
    body.append(_t(212, 122, "owns", size=8.5, colour="#5A7183", mono=True))
    body.append(f'<line x1="308" y1="182" x2="308" y2="222" stroke="#90A4AE" '
                f'stroke-width="1.3"/>')
    body.append(_t(314, 206, "HAS_LICENSE", size=8.5, colour="#5A7183",
                   mono=True))
    body.append(_t(28, 282, "its start date decides her label", size=9.5,
                   colour=TITLE))

    rows = [("owners", f"{shape['owner_rows']:,} rows", sample["owner_row"]),
            ("businesses", f"{shape['business_rows']:,} rows",
             sample["business_row"])]
    for i, (name, count, lines) in enumerate(rows):
        y = 110 + i * 86
        body.append(f'<rect x="436" y="{y}" width="776" height="70" rx="4" '
                    f'fill="#FBFCFD" stroke="{ENTITY}" stroke-width="1"/>')
        body.append(_t(450, y + 20, name, size=11.5, weight=600))
        body.append(_t(450, y + 36, count, size=9, colour="#5A7183", mono=True))
        body.append(_t(450, y + 56, "her row:" if i == 0 else "its row:",
                       size=9, colour="#5A7183"))
        for k, line in enumerate(lines):
            body.append(_t(560, y + 24 + k * 15, line, size=9.5, mono=True,
                           colour="#37474F"))
    body.append(_arrow(396, 145, 432, None))
    body.append(_arrow(396, 231, 432, None))

    # ------------------------------------- 2: the bookkeeping
    _band(body, 318, "2", "the bookkeeping — one id becomes one row")
    body.append(_t(28, 342, "at = {}  — one dictionary for both kinds of node, "
                            "owners numbered first", size=10, colour="#5A7183",
                   mono=True))
    maps = [(sample["cluster"], sample["owner_index"], "her", ENTITY),
            (sample["business_id"], sample["business_index"], "her business",
             "#90A4AE")]
    for i, (key, value, who, colour) in enumerate(maps):
        y = 364 + i * 26
        body.append(_t(44, y, f"'{key}'", size=10.5, mono=True, colour=colour,
                       weight=600))
        body.append(_t(210, y, "->", size=10.5, mono=True, colour="#90A4AE"))
        body.append(_t(240, y, f"row {value:,}", size=10.5, mono=True,
                       weight=600))
        body.append(_t(330, y, who, size=9.5, colour="#5A7183"))

    bar_y, bar_x, bar_w = 364, 440, 772
    cut = bar_w * shape["people"] / shape["nodes"]
    body.append(f'<rect x="{bar_x}" y="{bar_y - 12}" width="{cut:.1f}" '
                f'height="26" rx="3" fill="{OBSERVED}" stroke="{ENTITY}" '
                f'stroke-width="1"/>')
    body.append(f'<rect x="{bar_x + cut:.1f}" y="{bar_y - 12}" '
                f'width="{bar_w - cut:.1f}" height="26" rx="3" fill="#F0F4F6" '
                f'stroke="{ENTITY}" stroke-width="1"/>')
    body.append(_t(bar_x + cut / 2, bar_y + 5,
                   f"{shape['people']:,} owners", size=10, anchor="middle",
                   weight=600))
    body.append(_t(bar_x + cut + (bar_w - cut) / 2, bar_y + 5,
                   f"{shape['nodes'] - shape['people']:,} businesses", size=10,
                   anchor="middle", weight=600, colour="#37474F"))
    for at_x, text in ((bar_x, "row 0"),
                       (bar_x + cut, f"row {shape['people']:,}"),
                       (bar_x + bar_w, f"row {shape['nodes'] - 1:,}")):
        body.append(f'<line x1="{at_x:.1f}" y1="{bar_y + 14}" x2="{at_x:.1f}" '
                    f'y2="{bar_y + 20}" stroke="{ENTITY}" stroke-width="1"/>')
        body.append(_t(at_x, bar_y + 32, text, size=8.5, anchor="middle",
                       colour="#5A7183", mono=True))
    body.append(f'<line x1="{bar_x + cut * sample["owner_index"] / shape["people"]:.1f}" '
                f'y1="{bar_y - 22}" '
                f'x2="{bar_x + cut * sample["owner_index"] / shape["people"]:.1f}" '
                f'y2="{bar_y - 12}" stroke="{MISSING}" stroke-width="1.6"/>')

    # ------------------------------------- 3: the three tensors
    _band(body, 440, "3", "what the network is handed")

    body.append(_t(28, 468, "x", size=13, weight=600, mono=True))
    body.append(_t(44, 468, f"{shape['nodes']:,} x {shape['columns']}  float32"
                            "  — one row per node, and every row the same width",
                   size=10, colour="#5A7183", mono=True))
    sx = 300
    for i, (label, values) in enumerate((
            (f"row {sample['owner_index']:,}", sample["x_owner"]),
            (f"row {sample['business_index']:,}", sample["x_business"]))):
        y = 482 + i * 30
        body.append(_t(28, y + 14, label, size=9.5, mono=True, weight=600))
        body.append(_t(120, y + 14, sample["owner"] if i == 0
                       else sample["business"], size=9, colour="#5A7183"))
        _strip(body, sx, y, values)
    for first, last, name, note in sample["groups"]:
        _brace_light(body, sx + first * 10.4, sx + (last + 1) * 10.4 - 1, 544,
                     name, note)
    body.append(_t(28, 596, "An owner is zeros wherever a business's columns "
                            "are, and the other way round — the two kinds of "
                            "node share one matrix without sharing a meaning.",
                   size=9.5, colour="#5A7183"))

    body.append(_t(28, 630, "edge_index", size=13, weight=600, mono=True))
    body.append(_t(132, 630, f"2 x {2 * shape['edges']:,}  int64", size=10,
                   colour="#5A7183", mono=True))
    cols = sample["edge_columns"]
    for r in range(2):
        line = "[" + ", ".join(f"{v:>7,}" for v in cols[r]) + ", ... ]"
        body.append(_t(300, 624 + r * 16, line, size=10, mono=True,
                       colour="#37474F"))
    body.append(f'<rect x="296" y="{612}" width="112" height="36" rx="3" '
                f'fill="none" stroke="{MISSING}" stroke-width="1.4"/>')
    body.append(_t(420, 662, f"the first two columns are her one edge, written "
                             f"both ways: row {sample['owner_index']:,} to row "
                             f"{sample['business_index']:,}, and back",
                   size=9.5, colour="#8A4B00", weight=600))

    body.append(_t(28, 690, "y", size=13, weight=600, mono=True))
    body.append(_t(44, 690, f"{shape['labelled']:,} int64 — plus `index`, "
                            f"saying which node each answer belongs to. "
                            f"index[{sample['label_at']:,}] = "
                            f"{sample['owner_index']:,}, so y"
                            f"[{sample['label_at']:,}] = {sample['label']} "
                            f"is hers. A business has no answer at all.",
                   size=10, colour="#5A7183", mono=True))
    return _svg(width, height, body)


def _brace_light(body, x0, x1, y, label, note):
    """A hairline brace under a run of columns of `x`."""
    mid = (x0 + x1) / 2
    body.append(f'<path d="M {x0:.1f} {y - 6} L {x0:.1f} {y} L {x1:.1f} {y} '
                f'L {x1:.1f} {y - 6}" fill="none" stroke="#90A4AE" '
                f'stroke-width="1"/>')
    body.append(_t(mid, y + 14, label, size=9.5, anchor="middle", weight=600,
                   colour="#37474F"))
    body.append(_t(mid, y + 27, note, size=8.5, anchor="middle",
                   colour="#5A7183"))


def hops_picture(chain):
    """Three layers, three hops, and why both directions of each edge are added.

    The figure answers a question the numbers alone do not: with edges written
    only as owner -> business, a message leaves the owner and never comes back,
    so her row never changes. Every edge goes in both directions for that reason
    and not for symmetry's sake.

    `chain` is four real names out of the graph -- owner, her business, a
    co-owner, that co-owner's other business -- because "shop" and "other" drew
    a diagram of a graph instead of a fragment of this one. The cell that calls
    this runs the query, and the query asserts what the drawing claims: both
    businesses hold a licence from before 2015, and the fourth stop is **not**
    one of hers, so it really is three hops away and not one.
    """
    width, height = 1100, 310
    body = [_t(28, 30, "One layer is one hop", size=15, weight=600),
            _t(28, 50, "and every edge is written twice, because a message has "
                       "to come back", size=10.5, colour="#5A7183")]

    stops = [("her", ENTITY, "the owner we are asking about"),
             ("shop", "#90A4AE", "a business she holds"),
             ("other", ENTITY, "someone else on that business"),
             ("shop", "#90A4AE", "a business that person holds")]
    # Da 170 e non da 60: la prima nota e' larga 143 px e centrata a 60
    # cominciava a -12, cioe' fuori dal viewBox, che taglia in silenzio.
    x, y = 170, 130
    centres = []
    for i, ((label, fill, note), name) in enumerate(zip(stops, chain)):
        cx = x + i * 240
        centres.append(cx)
        r = 30 if i == 0 else 26
        body.append(f'<circle cx="{cx}" cy="{y}" r="{r}" fill="{fill}" '
                    f'stroke="{INK if i == 0 else "#FFFFFF"}" stroke-width="2"/>')
        body.append(_t(cx, y + 4, label, size=11, anchor="middle",
                       colour="#FFFFFF", weight=600))
        body.append(_t(cx, y + 52, fit(name, 220, 10.5), size=10.5,
                       anchor="middle", weight=600, colour=INK))
        body.append(_t(cx, y + 68, note, size=9.5, anchor="middle",
                       colour="#5A7183"))

    for i in range(3):
        a, b = centres[i] + 30, centres[i + 1] - 30
        mid = (a + b) / 2
        # Due frecce, una per direzione: e' cosi' che `edge_index` e' costruito.
        body.append(f'<path d="M {a} {y - 8} L {b - 7} {y - 8}" stroke="#90A4AE" '
                    f'stroke-width="1.4"/>'
                    f'<path d="M {b - 7} {y - 12} L {b} {y - 8} L {b - 7} {y - 4} z" '
                    f'fill="#90A4AE"/>')
        body.append(f'<path d="M {b} {y + 8} L {a + 7} {y + 8}" stroke="#90A4AE" '
                    f'stroke-width="1.4"/>'
                    f'<path d="M {a + 7} {y + 4} L {a} {y + 8} L {a + 7} {y + 12} z" '
                    f'fill="#90A4AE"/>')
        body.append(f'<rect x="{mid - 34}" y="{y - 46}" width="68" height="22" '
                    f'rx="11" fill="{OBSERVED}" stroke="{ENTITY}" '
                    f'stroke-width="1"/>')
        body.append(_t(mid, y - 31, f"layer {i + 1}", size=10,
                       anchor="middle", weight=600))

    body.append(_t(28, height - 44,
                   "Written only as owner -> business, a message leaves her and "
                   "nothing comes back: her row never changes, and the table "
                   "below measures what that costs.", size=10,
                   colour="#5A7183"))
    body.append(_t(28, height - 22,
                   "Three layers is what it takes to reach a co-owner's "
                   "business. Two reach the co-owner; one reaches only her own "
                   "shops.", size=10, colour="#5A7183"))
    return _svg(width, height, body)
