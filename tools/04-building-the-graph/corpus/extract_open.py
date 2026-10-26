#!/usr/bin/env python3
"""Open-schema extraction: the model names the types, entities and predicates.

Instructor-only. This is the approach that **lost**, and it is kept because the
losing is the lesson. `extract_typed.py` is what runs in production; decision 64
records why, and the numbers below are the evidence it rests on.

    # the live demo: one page, read in front of the class
    python tools/04-building-the-graph/corpus/extract_open.py --page 84664_r31#1

    # the batch that produced the comparison (300 pages, ~4 min at 16 workers)
    python tools/04-building-the-graph/corpus/extract_open.py --run data/chicago/2022-2026

=============================================================================
WHAT IT COSTS TO LET THE MODEL CHOOSE -- measured 19/10/2026 on 300 pages
=============================================================================
The same 300 stratified pages were labelled by hand and by this prompt. Scored
by `compare_labels.py`:

  grounding          of 2,417 values, 97.7% are copied literally out of what the
                     model was shown; 1.7% are reformatted but their words are
                     on the page; 0.6% -- 15 values -- have nothing behind them.
                     The model copies well. That is not the problem.
  page type          55% agreement with the hand labels, against 25% for the
                     regex detectors on the same pages. The model wins here.
  empty pages        of 29 pages carrying nothing but a running header, it typed
                     0 correctly: it read the header and called them contract
                     summaries. It cannot recognise an absence.
  predicates         1,786 relations over 837 distinct predicates -- a new
                     predicate every two relations, with `IS_VENDOR_FOR` and
                     `IS_VENDOR_OF` side by side -- and **none** of the eight
                     predicates the graph actually needs.

So the model is well grounded and badly structured. On 124,416 pages an open
schema would give a graph with tens of thousands of edge types, which is not a
graph. `extract_typed.py` keeps the grounding and removes the invention by
naming the slots itself.

Nothing in this file writes to the graph. Its output is a reference set.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    sys.exit("pip install openai (see pyproject.toml for the pinned version)")

LLM_URL = os.environ.get("KGTP_LLM_BASE_URL", "https://kgtp-llm.ngrok-free.app/v1")
LLM_KEY = os.environ.get("KGTP_LLM_API_KEY", "teacher-key")
LLM_MODEL = os.environ.get("KGTP_LLM_MODEL", "Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8")

# The eighteen families are closed on purpose: the type is the one thing a
# closed list costs nothing to fix, and leaving it open made the answers
# unscoreable against the hand labels. Everything else in the prompt is open,
# which is the point of the comparison.
FAMILIES = [
    "bond ordinance or indenture", "boilerplate contract clauses",
    "empty page or placeholder", "contract modification",
    "EDS and sworn statements", "MBE/WBE/DBE rules",
    "subcontracting commitment", "compliance audit result",
    "political contribution disclosure", "filled unit prices",
    "bid schedule without prices", "contract or purchase order summary",
    "insurance", "people and corporate structure", "procurement process",
    "scope, technical, schedule", "project finance", "other",
]

# Verbatim, as it ran on 19/10/2026. Decision 25 requires the prompt to travel
# with the output it produced, so this string is not to be "improved" without
# re-running the 300 pages: the measurements above would stop applying.
SYSTEM = (
    "You extract structured facts from pages of City of Chicago contract documents.\n"
    "Return ONLY a JSON object, no prose, with exactly these keys:\n"
    '{"type": one of ' + json.dumps(FAMILIES) + ",\n"
    ' "specific": true if the page carries facts about ITS OWN contract, false if it is generic text reusable on any contract,\n'
    ' "entities": [{"t": type, "v": value, "r": role or ""}],  // t in: Person, Organization, Amount, Term, Identifier, Facility, Commodity, Program, LegalRef, Address, FundCode, Attribute, Obligation, Role, Document, System, Brand, Standard\n'
    ' "relations": [[subject, predicate, object]]  // UPPER_SNAKE predicates, only relations the page actually states\n'
    "}\n"
    "Rules: never invent a value that is not on the page. Organizations merely cited as examples in a clause are NOT parties. "
    "A price table whose prices read 'Not Specified' has no amounts."
)


def client() -> OpenAI:
    return OpenAI(base_url=LLM_URL, api_key=LLM_KEY, timeout=180.0, max_retries=2)


def ask(api: OpenAI, rec: dict) -> tuple[str, str, int, int]:
    """One page. The header is passed in and is also what makes the model guess.

    The four record fields are prepended because a page alone often does not say
    which contract it belongs to. They are also why a grounding test that looks
    only at `text` reports inventions that are not there: the model quotes this
    header back, `PO 232150` and all. Measured three ways on the same answers --
    29.3% against the page text alone, 10.3% adding the field values, 2.3%
    against this message as sent. `compare_labels.py` searches the last one.
    """
    r = api.chat.completions.create(
        model=LLM_MODEL, temperature=0, max_tokens=1400,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content":
                f"PO {rec.get('po_number','')} | spec {rec.get('spec_number','')} | "
                f"dept {rec.get('department','')} | vendor {rec.get('vendor_name','')}\n\n"
                f"{rec['text'][:6000]}"},
        ],
    )
    return (rec["page_id"], r.choices[0].message.content,
            r.usage.prompt_tokens, r.usage.completion_tokens)


def find_page(corpus: Path, page_id: str) -> dict:
    """`<doc>#<page>` out of the extracted corpus, without touching a PDF."""
    doc, _, page = page_id.partition("#")
    f = corpus / f"{doc}.jsonl"
    if not f.exists():
        sys.exit(f"{f} non esiste: il documento non ha testo estratto")
    for line in open(f):
        r = json.loads(line)
        if str(r["page"]) == page:
            return r
    sys.exit(f"pagina {page} non trovata in {doc}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--page", help="one page, as 84664_r31#1 -- prints the answer")
    p.add_argument("--run", type=Path, help="the 300-page reference batch")
    p.add_argument("--corpus-dir", type=Path, default=Path("data/chicago/2022-2026"))
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--show-text", action="store_true", help="print the page first")
    p.add_argument("--show-prompt", action="store_true", help="print the prompt and stop")
    args = p.parse_args()

    if args.show_prompt:
        print(SYSTEM)
        return 0
    if not args.page and not args.run:
        p.error("serve --page, --run o --show-prompt")

    api = client()

    if args.page:
        rec = find_page(args.corpus_dir / "corpus", args.page)
        if args.show_text:
            print("=" * 78, f"\nLA PAGINA: {args.page}\n", "=" * 78)
            print(rec["text"][:2000])
        t0 = time.time()
        _, txt, tin, tout = ask(api, rec)
        print("=" * 78, f"\nQUELLO CHE IL MODELLO LEGGE ({time.time()-t0:.1f}s, "
              f"{tin} token in, {tout} out)\n", "=" * 78)
        try:
            print(json.dumps(json.loads(txt), indent=2, ensure_ascii=False))
        except json.JSONDecodeError:
            print("JSON non valido:\n", txt)
        return 0

    out = args.run / "sample300" / "labels_qwen.jsonl"
    src = args.run / "sample300" / "pages.jsonl"
    if not src.exists():
        sys.exit(f"{src} non esiste: esegui prima sample_pages.py")
    done = {json.loads(l)["page_id"] for l in open(out)} if out.exists() else set()
    recs = [r for r in (json.loads(l) for l in open(src)) if r["page_id"] not in done]
    print(f"da fare: {len(recs)} (gia' fatte: {len(done)})", file=sys.stderr)
    if not recs:
        return 0

    t0 = time.time()
    n = 0
    with open(out, "a") as f, ThreadPoolExecutor(max_workers=args.workers) as ex:
        for pid, txt, tin, tout in ex.map(lambda r: ask(api, r), recs):
            try:
                parsed = json.loads(txt)
            except json.JSONDecodeError:
                parsed = {"type": "PARSE_ERROR", "specific": None, "entities": [],
                          "relations": [], "raw": txt[:400]}
            parsed.update(page_id=pid, _tok=[tin, tout])
            f.write(json.dumps(parsed, ensure_ascii=False) + "\n")
            f.flush()
            n += 1
            if n % 50 == 0:
                print(f"  {n}/{len(recs)}  {n/(time.time()-t0)*60:.0f} pag/min",
                      file=sys.stderr)
    print(f"\nfatte {n} pagine in {(time.time()-t0)/60:.1f} min -> {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
