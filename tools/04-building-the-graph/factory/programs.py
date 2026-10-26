"""The programme a grant agreement funds, named by the document and not by the CSV.

A contract in the structured data is an island: it carries a vendor, a department
and an amount, and nothing says that three contracts with three different vendors
are the same city programme. The grant agreements say so in prose. Measured
18/9/2026 over 112 of them: 58% name a programme, 56 distinct names, and seven of
those appear on more than one contract with more than one vendor --
`Employment Preparation and Placement Program` on three, `Homeless Services
Program` on three.

    python -m factory.programs --extract     # ask the model, write the JSON
    python -m factory.programs --load        # read the JSON, write the graph
    python -m factory.programs --load --dry-run

Two commands on purpose. the corpus rule forbids live inference in the demos, so
the extraction runs once, by the instructor, and what students get is the file.
Decision 43: this is a worked example over the prose branch of decision 25, not a
pipeline over the corpus -- the yield does not justify one, and saying so is part
of the lesson.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")

LLM_URL = os.environ.get("KGTP_LLM_BASE_URL", "https://kgtp-llm.ngrok-free.app/v1")
LLM_KEY = os.environ.get("KGTP_LLM_API_KEY", "teacher-key")
LLM_MODEL = os.environ.get("KGTP_LLM_MODEL", "Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8")

OUT = Path("../../data/chicago/descriptions/programs.json")

# Narrow on purpose. Asked for eight fields at once on 18/9/2026 the model
# answered well, but a programme name is the only one of them with a yield worth
# building on, and a narrow question is where the model is most reliable -- the
# same reason the relevance judge of decision 40 asks one thing.
PROMPT = """This is an excerpt from a City of Chicago grant agreement.

Name the programme this agreement funds, exactly as the text names it. A programme
is a named initiative that can outlive this one contract -- "Preschool for All",
"Employment Preparation and Placement Program". The contractor's own name, the
department, or a description of the work is not a programme name. If the text
names none, answer null.

Answer with JSON and nothing else: {"program": "..."}

Excerpt:
"""

READ = """
MATCH (doc:Document)-[:HAS_PAGE]->(p:Page)
WITH doc, p ORDER BY p.page
WITH doc, collect(p.text)[..30] AS pages
MATCH (doc)<-[:HAS_DOCUMENT]-(:ContractRecord)-[:INCLUDED_IN_CONTRACT]->(c:Contract)
OPTIONAL MATCH (c)-[:HAS_VENDOR]->(o:Organization)
RETURN DISTINCT c.id AS contract, doc.id AS doc, collect(DISTINCT o.name)[0] AS vendor,
       head(pages) AS first, reduce(a = '', t IN pages[1..] | a + '\n' + t) AS body
"""

WRITE = """
UNWIND $rows AS row
MERGE (p:Program {id: row.id})
  SET p.name = row.name, p.names = row.names, p.source = 'DOCUMENTS'
WITH p, row
UNWIND row.contracts AS po
MATCH (c:Contract {id: po})
MERGE (c)-[r:PART_OF_PROGRAM]->(p)
  SET r.fromDocument = row.documents[0]
"""


def key(name: str) -> str:
    """One programme, however the document spelled it.

    `FY '17 CHILD CARE` and `Child Care` are the same programme with a budget year
    in front, so the year is dropped before comparing. Nothing else is inferred:
    two names that differ by more than punctuation stay two programmes.
    """
    name = re.sub(r"^(fy\s*'?\d{2,4}|20\d\d)\s*[-–:]?\s*", "", name.strip(), flags=re.I)
    name = re.sub(r"\bprogram(me)?\b|\binitiative\b", "", name, flags=re.I)
    return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()


def windows(session):
    from factory.descriptions import classify, scope_candidates

    seen = set()
    for row in session.run(READ):
        if row["contract"] in seen or classify(row["first"] or "")[0] != "grant_agreement":
            continue
        found = scope_candidates(row["body"] or "", window=6000)
        if found:
            seen.add(row["contract"])
            yield dict(row), found[0]


def extract() -> int:
    from database.lpg.graph_db import Neo4jDB
    from openai import OpenAI

    api = OpenAI(base_url=LLM_URL, api_key=LLM_KEY, timeout=90.0, max_retries=4)
    db = Neo4jDB()
    try:
        with db._driver.session(database=db._database) as session:
            work = list(windows(session))
    finally:
        db.close()
    print(f"grant agreements with a readable scope: {len(work)}")

    def ask(item):
        row, window = item
        try:
            reply = api.chat.completions.create(
                model=LLM_MODEL, temperature=0, max_tokens=80,
                messages=[{"role": "user", "content": PROMPT + window[:6000]}])
            match = re.search(r"\{.*\}", reply.choices[0].message.content or "", re.S)
            name = json.loads(match.group(0)).get("program") if match else None
        except Exception as error:      # noqa: BLE001 - counted, not raised
            return {**row, "program": None, "error": type(error).__name__}
        if isinstance(name, str) and name.strip().lower() in ("null", "none", ""):
            name = None
        return {**row, "program": name}

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = [{k: v for k, v in r.items() if k not in ("first", "body")}
                   for r in pool.map(ask, work)]

    named = [r for r in results if r.get("program")]
    errors = sum(1 for r in results if r.get("error"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"model": LLM_MODEL, "endpoint": LLM_URL, "prompt": PROMPT,
         "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "extractions": results}, indent=2))
    print(f"named a programme: {len(named)}/{len(results)}   errors: {errors}")
    print(f"written to {OUT}")
    return len(named)


def group(extractions: list[dict]) -> list[dict]:
    by_key = defaultdict(lambda: {"names": Counter(), "contracts": [], "documents": [],
                                  "vendors": set()})
    for item in extractions:
        name = item.get("program")
        if not name or not key(name):
            continue
        entry = by_key[key(name)]
        entry["names"][name.strip()] += 1
        entry["contracts"].append(item["contract"])
        entry["documents"].append(item["doc"])
        entry["vendors"].add(item.get("vendor"))
    rows = []
    for k, entry in by_key.items():
        # Decision 14: the identifier carries its namespace. Singular, like the
        # `vendor:` and `department:` identifiers the agent's tools already take,
        # so one prefix rule covers all three.
        rows.append({"id": "program:" + k.replace(" ", "-")[:60],
                     # The display name is the spelling the documents used most:
                     # the model repeats the document, and the documents disagree
                     # about capitalisation more than about words.
                     "name": entry["names"].most_common(1)[0][0],
                     "names": sorted(entry["names"]),
                     "contracts": sorted(set(entry["contracts"])),
                     "documents": sorted(set(entry["documents"])),
                     "vendors": sorted(v for v in entry["vendors"] if v)})
    return sorted(rows, key=lambda r: (-len(r["contracts"]), r["name"]))


def load(dry_run: bool) -> int:
    from database.lpg.graph_db import Neo4jDB

    if not OUT.exists():
        print(f"no extraction at {OUT}: run --extract first")
        return 0
    rows = group(json.loads(OUT.read_text())["extractions"])
    shared = [r for r in rows if len(r["contracts"]) > 1]
    print(f"programmes: {len(rows)}   on more than one contract: {len(shared)}")
    for row in shared[:6]:
        print(f"   {row['name'][:52]:54} {len(row['contracts'])} contracts, "
              f"{len(row['vendors'])} vendors")
    if dry_run:
        print("\ndry run, nothing written")
        return 0
    db = Neo4jDB()
    try:
        with db._driver.session(database=db._database) as session:
            session.run("CREATE CONSTRAINT program_id IF NOT EXISTS "
                        "FOR (p:Program) REQUIRE p.id IS UNIQUE")
            session.run(WRITE, rows=rows)
    finally:
        db.close()
    print(f"\nwritten: {len(rows)} Program nodes")
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--extract", action="store_true", help="ask the model, write the JSON")
    ap.add_argument("--load", action="store_true", help="read the JSON, write the graph")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.extract:
        extract()
    if args.load or not args.extract:
        load(args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
