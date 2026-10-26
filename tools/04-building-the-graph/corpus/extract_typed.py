#!/usr/bin/env python3
"""Fill one fixed form per page type, with the served model.

Instructor-only. Runs after `extract_contracts.py`, over the extracted text --
never over the PDFs.

    python tools/04-building-the-graph/corpus/extract_typed.py schedule_c data/chicago/2022-2026
    python tools/04-building-the-graph/corpus/extract_typed.py --list

    # one page, read in front of the class, written nowhere
    python tools/04-building-the-graph/corpus/extract_typed.py schedule_c --page 259270_r0#45

Output is one JSONL per type under `<dir>/typed/`, one line per page, appended
as it goes. Re-running skips pages already present, so a dropped Colab session
costs the pages in flight and nothing more.

=============================================================================
WHY FORM-FILLING AND NOT ENTITY EXTRACTION -- measured 2026-10-19
=============================================================================
The same 300 pages were labelled by hand and by the served model. The model is
well grounded: of 2,417 values, 97.7% are copied literally from what it was
shown, 1.7% are reformatted with the words still on the page, and 0.6% -- 15
values -- have nothing behind them. But asked for entities and relations in the
open it produced 1,786
relations over 837 distinct predicates -- a new predicate every two relations,
with `IS_VENDOR_FOR` and `IS_VENDOR_OF` side by side -- and none of the eight
predicates the graph actually needs. It also cannot recognise an empty page: of
29 pages that carry nothing but a running header, it typed 0 correctly, reading
the header and calling them contract summaries.

So the model is asked to copy into named slots that we choose, and to leave a
slot null when the page does not fill it. Its strength (copying exactly) is
what the task needs; its weakness (inventing structure) is removed because
there is no structure left to invent.

The `filled` slot carries the judgement the model is worst at, so it is checked
afterwards and never trusted: a form whose party slots are null is blank
whatever the model says.

Each type's `locator` is the string that selects its pages. Selection is not
the model's job either -- it is a grep, and it is why this runs over ~11,500
pages instead of 124,416.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
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

# A type is: the string that finds its pages, the slots to fill, and the slots
# that must be present for the page to count as filled rather than blank.
TYPES = {
    "schedule_c": {
        "locator": re.compile(r"Letter of Intent to Perform as a", re.I),
        "what": "a Schedule C/C-1/C-3/C-V letter of intent, in which a certified "
                "firm commits to work as a subcontractor to a prime contractor",
        "slots": {
            "certification": "MBE, WBE, VBE or DBE -- which programme the undersigned firm is certified under",
            "subcontractor": "name of the certified firm making the commitment (the 'From' party)",
            "prime": "name of the prime contractor (the 'To' party), excluding 'and the City of Chicago'",
            "work": "the work or service the certified firm will perform",
            "amount": "the subcontract dollar amount, verbatim, or null if blank or TBD",
            "percent": "the percentage of participation, or null",
            "signer": "name of the person who signed for the certified firm",
            "signer_title": "that person's title",
            "date": "the signature date, verbatim",
            "tier": "'first' for a subcontractor to the prime, 'second' for a 2nd tier subcontractor",
            "prime_has_ownership": "true/false/null -- whether the form states that owners or "
                                   "principals of the prime hold an ownership interest in the undersigned",
        },
        "required": ("subcontractor", "prime"),
    },
    "schedule_d": {
        "locator": re.compile(r"Schedule D[-\s]?(?:1|2|3|V)?\s*:?\s*(?:Affidavit|Compliance Plan|Task Order)"
                              r"|Affidavit of (?:the )?Prime Contractor|Goal Implementation Plan", re.I),
        "what": "a Schedule D compliance plan, in which the prime contractor lists the "
                "certified firms it commits to and the dollar value of each commitment",
        "slots": {
            "prime": "name of the prime contractor making the affidavit",
            "goal_percent": "the contract specific goal stated on the page, or null",
            "participants": "list of {firm, certification, work, amount, percent} for every "
                            "certified firm listed with a commitment; empty list if the form is blank",
            "total_amount": "the total direct participation amount, verbatim, or null",
            "total_percent": "the total direct participation percentage, verbatim, or null",
        },
        "required": ("participants",),
    },
    "city_contact": {
        "locator": re.compile(r"(Senior )?Procurement Specialist|designated representative", re.I),
        "what": "a page that names, in running prose, a City of Chicago employee who is "
                "the point of contact for this contract -- the procurement specialist to "
                "whom bid questions go, or the representative the parties designate for notices",
        "slots": {
            "people": "list of {name, title, role, email, phone, side} for each person named. "
                      "side is 'city' for a City of Chicago employee and 'contractor' for "
                      "anyone on the vendor's side. Include only people named on the page; "
                      "an empty list if the clause names a role with no person in it.",
        },
        "required": ("people",),
    },
    "compliance_audit": {
        "locator": re.compile(r"mwdbe\.com|Compliance Audit Summary|Not Meeting Goal", re.I),
        "what": "a B2Gnow compliance audit page, reporting what a contract committed "
                "to in MBE/WBE participation against what was actually paid",
        "slots": {
            "prime": "name of the prime contractor",
            "goal_percent": "the contract participation goal, verbatim",
            "credit_percent": "the participation actually credited, verbatim",
            "award": "current award amount, verbatim",
            "total_paid": "total paid to date, verbatim",
            "for_credit": "amount counted toward the goal, verbatim",
            "status": "any stated compliance status, e.g. 'Not Meeting Goal'",
            "progress": "contract progress percentage, or null",
            "period": "the contract period shown, verbatim",
        },
        "required": ("goal_percent",),
    },
    "key_personnel": {
        "locator": re.compile(r"Key Personnel|Areas? of Expertise|Summary of Key Personnel", re.I),
        "what": "a key-personnel page naming the people a bidder commits to the contract",
        "slots": {
            "people": "list of {name, title, role, location, employer} for each person named; "
                      "omit anyone who is only a signatory or a city employee",
            "firm": "the firm the page belongs to",
        },
        "required": ("people",),
    },
    "political_contributions": {
        "locator": re.compile(r"Individual Contribution|political fundraising committee of|Friends of ", re.I),
        "what": "a disclosure of political contributions made by the contractor or its principals",
        "slots": {
            "contributions": "list of {donor, recipient_committee, amount, date_made, date_reported}",
        },
        "required": ("contributions",),
    },
    "defined_terms": {
        "locator": re.compile(r"Funding Sources \(4\.01\)|Estimated Project Cost", re.I),
        "what": "the defined-terms table of a redevelopment agreement, which carries the "
                "project's funding stack",
        "slots": {
            "project_cost": "estimated project cost, verbatim",
            "funding": "list of {source, amount} exactly as the table gives them",
            "city_grant": "the city's own contribution, verbatim",
            "commencement": "commencement date",
            "completion": "completion date",
            "trade_names": "any trade name stated",
            "notice_party": "{name, title, address} of the developer's notice contact",
        },
        "required": ("project_cost",),
    },
}

SYSTEM = """You transcribe one page of a City of Chicago contract document into a fixed form.

The page is {what}.

Return ONLY a JSON object with exactly these keys and no others:
{slots}
plus "filled": true if the form on this page has been completed, false if it is a blank template.

Rules, in order of importance:
1. Copy values verbatim from the page. Never normalise, reformat or complete them.
2. Any slot the page does not fill in is null. A blank line, an underscore row, "TBD"
   or "N/A" is null. Returning null is always better than returning a guess.
3. Never carry a value over from the running header at the top of the page unless the
   slot asks for it.
4. Do not add keys. Do not explain."""


def client() -> OpenAI:
    return OpenAI(base_url=LLM_URL, api_key=LLM_KEY, timeout=180.0, max_retries=3)


def select(corpus: Path, locator: re.Pattern, limit: int | None) -> list[dict]:
    """The pages of one type. A grep, deliberately: see the module docstring."""
    out = []
    for f in sorted(corpus.glob("*.jsonl")):
        for line in open(f):
            r = json.loads(line)
            if locator.search(r["text"]):
                out.append(r)
                if limit and len(out) >= limit:
                    return out
    return out


def ask(api: OpenAI, spec: dict, rec: dict) -> dict:
    slots = "\n".join(f'  "{k}": {v}' for k, v in spec["slots"].items())
    sys_msg = SYSTEM.format(what=spec["what"], slots=slots)
    r = api.chat.completions.create(
        model=LLM_MODEL, temperature=0, max_tokens=1200,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": sys_msg},
                  {"role": "user", "content": rec["text"][:8000]}],
    )
    try:
        got = json.loads(r.choices[0].message.content)
    except json.JSONDecodeError:
        got = {"_error": "invalid json", "_raw": r.choices[0].message.content[:400]}
    # The model is worst at exactly this judgement, so it is recomputed here and
    # the model's own answer is kept only for comparison.
    got["_model_said_filled"] = got.pop("filled", None)
    got["filled"] = all(got.get(k) for k in spec["required"]) if "_error" not in got else None
    if isinstance(got.get("participants"), list) and not got["participants"]:
        got["filled"] = False
    got.update(page_id=f'{rec["doc_id"]}#{rec["page"]}', doc_id=rec["doc_id"],
               page=rec["page"], po_number=rec.get("po_number", ""),
               spec_number=rec.get("spec_number", ""),
               vendor_name=rec.get("vendor_name", ""),
               _tokens=[r.usage.prompt_tokens, r.usage.completion_tokens])
    return got


def find_page(corpus: Path, page_id: str) -> dict:
    """`<doc>#<page>` out of the extracted corpus, for the one-page demo."""
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
    p.add_argument("type", nargs="?", help=f"one of: {', '.join(TYPES)}")
    p.add_argument("corpus_dir", nargs="?", type=Path, default=Path("data/chicago/2022-2026"))
    p.add_argument("--limit", type=int, default=None, help="stop after this many pages")
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--list", action="store_true")
    p.add_argument("--page", help="one page, as 259270_r0#45 -- prints and writes nothing")
    p.add_argument("--show-text", action="store_true", help="print the page first")
    p.add_argument("--show-prompt", action="store_true", help="print the prompt and stop")
    args = p.parse_args()

    if args.list or not args.type:
        corpus = args.corpus_dir / "corpus"
        for name, spec in TYPES.items():
            n = len(select(corpus, spec["locator"], None)) if corpus.exists() else "?"
            print(f"{name:26} {n:>7} pagine   {len(spec['slots'])} campi")
        return 0
    if args.type not in TYPES:
        return print(f"tipo sconosciuto: {args.type}", file=sys.stderr) or 2

    spec = TYPES[args.type]

    if args.show_prompt:
        slots = "\n".join(f'  "{k}": {v}' for k, v in spec["slots"].items())
        print(SYSTEM.format(what=spec["what"], slots=slots))
        return 0

    if args.page:
        rec = find_page(args.corpus_dir / "corpus", args.page)
        if args.show_text:
            print("=" * 78, f"\nLA PAGINA: {args.page}\n", "=" * 78)
            print(rec["text"][:2000])
        t0 = time.time()
        got = ask(client(), spec, rec)
        print("=" * 78, f"\nIL MODULO COMPILATO ({time.time()-t0:.1f}s)\n", "=" * 78)
        print(json.dumps(got, indent=2, ensure_ascii=False))
        print(f"\n`filled` ricalcolato in codice: {got['filled']}   "
              f"il modello diceva: {got['_model_said_filled']}")
        return 0

    out_dir = args.corpus_dir / "typed"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.type}.jsonl"
    done = set()
    if out_path.exists():
        done = {json.loads(l)["page_id"] for l in open(out_path)}

    pages = [r for r in select(args.corpus_dir / "corpus", spec["locator"], args.limit)
             if f'{r["doc_id"]}#{r["page"]}' not in done]
    print(f"{args.type}: {len(pages)} pagine da fare, {len(done)} gia' fatte", file=sys.stderr)
    if not pages:
        return 0

    api = client()
    t0 = time.time()
    n = err = 0
    with open(out_path, "a") as f, ThreadPoolExecutor(max_workers=args.workers) as ex:
        for got in ex.map(lambda r: ask(api, spec, r), pages):
            f.write(json.dumps(got, ensure_ascii=False) + "\n")
            f.flush()
            n += 1
            err += "_error" in got
            if n % 100 == 0:
                print(f"  {n}/{len(pages)}  {n/(time.time()-t0)*60:.0f} pag/min  "
                      f"errori {err}", file=sys.stderr)

    filled = sum(1 for l in open(out_path) if json.loads(l).get("filled"))
    total = sum(1 for _ in open(out_path))
    print(f"\n{args.type}: {total} pagine, {filled} compilate ({filled/total:.0%}), "
          f"{err} risposte non valide, {(time.time()-t0)/60:.1f} min", file=sys.stderr)
    print(f"scritto {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
