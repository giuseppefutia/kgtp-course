#!/usr/bin/env python3
"""Score the two readers against the hand labels, on the same 300 pages.

Instructor-only. This is the measurement decision 64 rests on: it compares the
regex detectors and the open-schema model (`extract_open.py`) with 300 pages
read by hand, and it is the reason production uses a parser on fixed forms and a
closed schema on free ones.

    python tools/04-building-the-graph/corpus/compare_labels.py data/chicago/2022-2026

Input, all under `<dir>/sample300/`:

    pages.jsonl        the 300 pages, drawn by `sample_pages.py` with seed 42
    regex_labels.csv   what the detectors said, written blind by the same script
    labels_claude.jsonl the hand labels -- one reader, so what follows is
                       agreement with one reader, not accuracy
    labels_qwen.jsonl  what `extract_open.py` said

It prints and writes nothing.

=============================================================================
WHAT IT FOUND -- 19/10/2026
=============================================================================
    page type, regex   25% agreement, on the `propria` layer only
    page type, model   55%
    grounding, model   2.3% of values not copied literally, of which 0.6% have
                       nothing on the page behind them
    empty pages        0 of 29 typed correctly by the model
    predicates         837 distinct, for 1,786 relations, 0 of the 8 needed

The sample is deliberately not representative: `sample_pages.py` forces at least
four pages per category, so rare categories are over-drawn. These are agreement
rates on a diagnostic sample, not estimates of corpus-wide accuracy.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

# The hand labels are free text -- one line per page, written while reading.
# These rules fold them into the eighteen families the model chooses from, first
# match wins. They are the join between the two vocabularies and nothing else:
# changing one changes what "agreement" means, so they travel with the numbers.
RULES = [
    ("bond e indenture",         r"ordinanza bond|indenture sui bond|puntatore a documenti"),
    ("vuoto o segnaposto",       r"vuoto|intestazione sola|intestazione di allegato|frammento|"
                                 r"redatta|segnaposto|dichiaratamente|indice del contratto|"
                                 r"indice del bando|indice di allegati|modulo \(quasi"),
    ("modifica del contratto",   r"modifica|proroga"),
    ("EDS e dichiarazioni",      r"EDS|affidavit|indebitamento"),
    ("regole MBE/WBE/DBE",       r"MBE/WBE|DBE|Target Market|deroga agli obiettivi|enti di supporto"),
    ("impegni sui subappalti",   r"Schedule C|piano di conformita|joint venture|commitment|"
                                 r"formula di aggiudicazione"),
    ("audit di conformita",      r"audit di conformita"),
    ("contributi politici",      r"contributi politici"),
    ("prezzi compilati",         r"prezzi unitari compilati|prezzi come sconto"),
    ("capitolato senza prezzi",  r"SENZA prezzi"),
    ("scheda di contratto o PO", r"scheda riassuntiva|blanket PO|tracciamento del Consiglio|"
                                 r"accettazione con importo|ordine d'acquisto"),
    ("assicurazioni",            r"assicurazion"),
    ("persone e societa",        r"personale chiave|delibera societaria|parere legale|notarile|"
                                 r"parti e firme|capacita' organizzative|referenza di cliente|"
                                 r"contatti e rimando"),
    ("processo di gara",         r"gara|bando|checklist|parametri chiave|esecuzione dell'offerta|"
                                 r"requisiti di sistema|lettera \(deroga|modello di lettera"),
    ("ambito, tecnica, tempi",   r"specifiche tecniche|deliverable|manuale tecnico|coordinate|"
                                 r"milestone|manodopera|laboratorio|procedura operativa|immobile|"
                                 r"accordo:|premesse|definizioni \(RDA\)|obblighi del developer|"
                                 r"obblighi ambientali|energia"),
    ("finanza del progetto",     r"termini definiti|compensi|concessione|TIF|tabella di programma|"
                                 r"bilancio|budget|preventivo"),
    ("clausole standard",        r"clausole|definizioni|licenze e classi|politica del lavoro|"
                                 r"lettera del fornitore|introduzione del contratto"),
]

# The model answers in English, the hand labels fold into Italian names.
MODEL_TO_FAMILY = {
    "bond ordinance or indenture": "bond e indenture",
    "boilerplate contract clauses": "clausole standard",
    "empty page or placeholder": "vuoto o segnaposto",
    "contract modification": "modifica del contratto",
    "EDS and sworn statements": "EDS e dichiarazioni",
    "MBE/WBE/DBE rules": "regole MBE/WBE/DBE",
    "subcontracting commitment": "impegni sui subappalti",
    "compliance audit result": "audit di conformita",
    "political contribution disclosure": "contributi politici",
    "filled unit prices": "prezzi compilati",
    "bid schedule without prices": "capitolato senza prezzi",
    "contract or purchase order summary": "scheda di contratto o PO",
    "insurance": "assicurazioni",
    "people and corporate structure": "persone e societa",
    "procurement process": "processo di gara",
    "scope, technical, schedule": "ambito, tecnica, tempi",
    "project finance": "finanza del progetto",
    "other": "altro",
}

# Which families a detector's category is allowed to mean. Two categories map to
# nothing on purpose: `durata e scadenze` and `anagrafica e rimandi` describe a
# field a page happens to carry, not a kind of page, so no reading of a page can
# agree with them. That is a finding about the detectors, not a gap here.
DETECTOR_TO_FAMILIES = {
    "modifiche e proroghe": {"modifica del contratto"},
    "EDS e dichiarazioni": {"EDS e dichiarazioni"},
    "MBE/WBE e subappalti": {"regole MBE/WBE/DBE", "impegni sui subappalti",
                             "audit di conformita"},
    "parti e firme": {"persone e societa"},
    "assicurazioni": {"assicurazioni"},
    "prezzi e importi": {"prezzi compilati"},
    "ambito e specifiche": {"ambito, tecnica, tempi"},
    "gara e aggiudicazione": {"processo di gara"},
    "durata e scadenze": set(),
    "anagrafica e rimandi": set(),
}

# The eight predicates the graph is built on. The open extraction found none of
# them, which is the whole argument of decision 64.
NEEDED = ["SUBCONTRACTS_FOR", "MODIFIES", "INCREASES_AMOUNT_BY", "FILED_EDS_FOR",
          "JOINT_VENTURE_OF", "PERFORMED_AT", "HOLDS_CERTIFICATION", "SAME_AS"]


def family(hand_label: str) -> str:
    for name, rx in RULES:
        if re.search(rx, hand_label, re.I):
            return name
    return "altro"


def sent_message(pg: dict) -> str:
    """The user message `extract_open.py` sends, rebuilt verbatim.

    The grounding test has to search exactly this and not the page text: the
    header is part of what the model was shown, and it quotes it back.
    """
    return (f"PO {pg.get('po_number','')} | spec {pg.get('spec_number','')} | "
            f"dept {pg.get('department','')} | vendor {pg.get('vendor_name','')}\n\n"
            f"{pg['text'][:6000]}")


def squash(s) -> str:
    """No spaces at all: a name broken over two lines is still the same name."""
    return re.sub(r"[^a-z0-9]", "", norm(s))


def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def jsonl(path: Path) -> dict:
    return {json.loads(l)["page_id"]: json.loads(l) for l in open(path) if l.strip()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus_dir", nargs="?", type=Path,
                    default=Path("data/chicago/2022-2026"))
    args = ap.parse_args()
    base = args.corpus_dir / "sample300"
    for f in ("pages.jsonl", "regex_labels.csv", "labels_claude.jsonl", "labels_qwen.jsonl"):
        if not (base / f).exists():
            sys.exit(f"{base / f} non esiste")

    pages = jsonl(base / "pages.jsonl")
    hand = jsonl(base / "labels_claude.jsonl")
    model = jsonl(base / "labels_qwen.jsonl")
    detector = {r["page_id"]: r for r in csv.DictReader(open(base / "regex_labels.csv"))}
    for r in hand.values():
        r["family"] = family(r["my_type"])

    # --- the detectors, on the layer they were built for -------------------
    own = [p for p in hand if detector[p]["page_class"] == "propria"]
    rows, ok = [], 0
    for cat, allowed in DETECTOR_TO_FAMILIES.items():
        sel = [p for p in own if detector[p]["regex_type"] == cat]
        good = [p for p in sel if hand[p]["family"] in allowed]
        ok += len(good)
        if sel:
            rows.append((cat, len(sel), len(good)))
    print(f"=== I RILEVATORI A REGEX, sulle {len(own)} pagine dello strato 'propria' ===")
    for cat, n, g in sorted(rows, key=lambda r: -r[1]):
        print(f"  {cat:24} {g:3}/{n:3}  {g/n:5.0%}")
    print(f"  {'ACCORDO COMPLESSIVO':24} {ok:3}/{len(own):3}  {ok/len(own):5.0%}")

    # --- the model, page type ---------------------------------------------
    valid = [p for p in hand if p in model and model[p]["type"] != "PARSE_ERROR"]
    agree = sum(1 for p in valid
                if MODEL_TO_FAMILY.get(model[p]["type"]) == hand[p]["family"])
    print(f"\n=== IL MODELLO A SCHEMA APERTO, sulle stesse 300 pagine ===")
    print(f"  JSON valido        {len(valid)}/{len(model)}")
    print(f"  tipo di pagina     {agree}/{len(valid)} = {agree/len(valid):.0%}"
          f"   (la regex: {ok/len(own):.0%})")

    # The judgement the model cannot make. An absence has no text to copy.
    empty = [p for p in valid if hand[p]["family"] == "vuoto o segnaposto"]
    hit = sum(1 for p in empty
              if MODEL_TO_FAMILY.get(model[p]["type"]) == "vuoto o segnaposto")
    print(f"  pagine vuote       {hit}/{len(empty)} riconosciute")
    if empty:
        said = collections.Counter(MODEL_TO_FAMILY.get(model[p]["type"], "?")
                                   for p in empty).most_common(3)
        print(f"     le chiama: {', '.join(f'{k} ({v})' for k, v in said)}")

    # --- grounding: is the value in what the model was shown? -------------
    # The haystack is the user message `extract_open.py` builds, verbatim, and
    # not the page text. Three measurements of the same thing, 19 and 21/10/2026:
    #
    #   29.3%  page text only, punctuation significant
    #   10.3%  page text plus the header fields, punctuation ignored
    #    2.3%  the message as sent -- the model quotes the prompt's own `PO
    #          232150` and `spec 1265390`, which no earlier haystack contained
    #
    # Each earlier figure was an artefact of the haystack, not a property of the
    # model. The split below is the one that says something: half a percent of
    # values have nothing on the page behind them, and four times as many are
    # the model reformatting something that is there -- against a prompt that
    # says to copy verbatim.
    tot = literal = supported = 0
    unsupported = []
    for p in valid:
        msg = sent_message(pages[p])
        hay, hay_sq = norm(msg), squash(msg)
        for e in model[p].get("entities", []):
            if not isinstance(e, dict) or not e.get("v"):
                continue
            if len(squash(e["v"])) <= 4:
                continue
            tot += 1
            if squash(e["v"]) in hay_sq:
                literal += 1
                continue
            toks = [t for t in norm(e["v"]).split() if len(t) >= 4]
            if toks and sum(1 for t in toks if t in hay) / len(toks) >= 0.5:
                supported += 1          # reformatted, but the words are there
            else:
                unsupported.append((e.get("t"), e["v"], p))
    off = tot - literal
    print(f"  valori copiati alla lettera         {literal:,}/{tot:,} = {literal/tot:.1%}")
    print(f"  riformulati, ma con appoggio        {supported:,}/{tot:,} = {supported/tot:.1%}")
    print(f"  senza appoggio sulla pagina         {len(unsupported):,}/{tot:,} = "
          f"{len(unsupported)/tot:.1%}   <- le invenzioni")
    print(f"     non alla lettera, in tutto: {off}/{tot} = {off/tot:.1%}")
    for t, v, p in unsupported[:6]:
        print(f"     {t:<13} {v[:52]!r}  ({p})")

    # --- the vocabulary it invents ---------------------------------------
    mp, qp = collections.Counter(), collections.Counter()
    for p in valid:
        for r in hand[p].get("relations", []):
            if len(r) == 3:
                mp[r[1]] += 1
        for r in model[p].get("relations", []):
            if isinstance(r, list) and len(r) == 3:
                qp[r[1]] += 1
    print(f"\n=== I PREDICATI ===")
    print(f"  a mano      {sum(mp.values()):,} relazioni, {len(mp)} predicati")
    print(f"  il modello  {sum(qp.values()):,} relazioni, {len(qp)} predicati"
          f"   -- uno nuovo ogni {sum(qp.values())/len(qp):.1f} relazioni")
    print(f"  in comune   {len(set(mp) & set(qp))}")
    print(f"  i piu' usati dal modello: {', '.join(f'{k}({v})' for k, v in qp.most_common(6))}")
    print(f"  sugli {len(NEEDED)} predicati che il grafo usa davvero:")
    for k in NEEDED:
        print(f"      {k:22} a mano {mp.get(k, 0):3}   il modello {qp.get(k, 0):3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
