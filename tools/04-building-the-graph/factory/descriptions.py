"""One description per contract, built from the documents the router keeps.

The artefact scenarios 1, 2 and 5 of module 5 all retrieve against, and the
reason none of them could be measured before it existed. Decisions 25, 26 and 27
say what it is; this file builds it.

    python3 -m factory.descriptions --dry-run       # report, write nothing
    python3 -m factory.descriptions                 # write ContractDescription

Two stages run here, both deterministic: `classify` decides what each document
is, `extract` pulls the description out of it. The third stage, summarising the
grant agreements, needs a model and is not in this file.

Everything is read from the first page. Measured 15/9/2026 over 1,750 documents:
of the fields this file extracts, 1,119 titles are on page one and 1 is not;
454 brief descriptions on page one and 3 are not; every Mod Reason that exists
is on page one. Reading further costs time and finds nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, ".")

# Decision 14: an identifier carries the namespace it belongs to.
DESC_PREFIX = "contracts:desc:"

# The same firm's PDF can carry a font whose cmap is shifted, so the text layer
# extracts as mojibake that no quality check flags -- `garbage_token_ratio` has
# median 0 and only 6 pages of 92,439 above 0.3, because the shifted bytes still
# look like words. Measured 15/9/2026: 11 documents, all recoverable.
MOJIBAKE_SHIFT = 29
MOJIBAKE_MARKS = ("&RQWUDFW", "6XPPDU\\", "7LWOH")

# Field labels sit next to each other on the page, so a value runs until the
# next label starts. Without this the capture swallows the rest of the form.
# Labels are matched through the OCR, not around it: `Mod Req Number` comes back
# as `Mod Reo Number` often enough to leak into a title, and `Procurement
# Services` as `Procurement Ser.vices`. Every label here tolerates the letters
# its own OCR confuses and stray punctuation between words.
LABELS = (r"Term of Contract|Dollar Amount|Brief Descripti[o0]n"
          r"|Pr[o0]curement\s*Ser[.\s]*vices|M[o0]d\s*Re[qo]|M[o0]d\s*Reas[o0]n"
          r"|Vend[o0]r\s*Number|Specificati[o0]n\s*Number|City\s*Department"
          r"|Submissi[o0]n\s*Date|Name\s*[o0]f\s*C[o0]ntract[o0]r"
          r"|C[o0]ntract\s*Area|Please\s*refer\s*t[o0]\s*the\s*DPS"
          r"|C[o0]ntract\s*\(P[O0]\)\s*Number|M[o0]dificati[o0]n\s*Revisi[o0]n"
          r"|Start\s*Date|End\s*Date|Departmental\s*C[o0]ntact"
          r"|It has been determined")
NEXT_FIELD = r"(?=" + LABELS + r"|\n\s*\n)"
TRAILING_LABEL = re.compile(r"\s*(?:" + LABELS + r").*$", re.I | re.S)

ROUTES = {
    "contract_summary": "extract",
    "modification": "extract",
    "grant_agreement": "summarise",
    "task_order": "summarise",
    "ordinance": "extract",
}


def unshift(text: str) -> str:
    """Undo the shifted cmap, including the characters that fell below 32.

    The shift moves every glyph down by 29, so the space (32) arrives as 0x03
    and the digits as 0x0f-0x1e. Shifting only the printable range left those
    behind: the heading came back as `Modification\x03Summary\x03Report`, no
    test in `classify` matched it, and all 11 documents landed in `excluded`.
    Measured 20/9/2026, corrected the same day.

    Whitespace is the exception, and for the same reason: `pdftotext` writes the
    line breaks itself and leaves some real spaces between the glyph runs, so
    they are structure and not shifted content. Shifting them turned every real
    space into `=` -- `Contract =PO= Number` -- and 0x0a + 29 is an apostrophe,
    which would glue every line to the next. The cost is a real `=` in the
    document arriving as a space, which on these forms is nothing.
    """
    keep = " \n\r\f\t"
    return "".join(c if c in keep
                   else chr(ord(c) + MOJIBAKE_SHIFT) if 3 <= ord(c) < 127
                   else c
                   for c in text)


def classify(first_page: str) -> tuple[str, str, bool]:
    """Decision 25: what a document is, from its first page alone.

    Returns (class, how it was recognised, whether the text had to be unshifted).
    The cascade is ordered by confidence: the printed heading first, then the
    field labels for documents whose heading did not survive extraction, then
    the classes that have no heading of their own.

    A document that loses both its heading and its field labels lands in
    `excluded` and becomes invisible downstream with nothing to mark it. That is
    why `--dry-run` prints the excluded count instead of only the kept ones.
    """
    decoded = any(mark in first_page for mark in MOJIBAKE_MARKS)
    text = unshift(first_page) if decoded else first_page
    low = text.lower()

    if "modification summary" in low:
        return "modification", "heading", decoded
    if "contract summary" in low:
        return "contract_summary", "heading", decoded
    if re.search(r"Mod Req Number|Modification Revision Number", text, re.I):
        return "modification", "fields", decoded
    if re.search(r"Contract \(PO\) Number|Title of Contract|Brief Description of Work",
                 text, re.I):
        return "contract_summary", "fields", decoded
    if "document tracking sheet" in low:
        return "ordinance", "heading", decoded
    if re.search(r"grant agreement|delegate agency", low):
        return "grant_agreement", "heading", decoded
    if "task order" in low:
        return "task_order", "heading", decoded
    if "amlegal" in low:
        return "excluded:municipal_code", "heading", decoded
    return "excluded:other", "none", decoded


def field(text: str, label: str, cap: int = 400) -> str:
    match = re.search(label + r":?\s*(.*?)" + NEXT_FIELD, text, re.S | re.I)
    if not match:
        return ""
    # The lookahead stops at the next label it recognises; this cuts the one it
    # did not, so a mangled label does not travel into the indexed text.
    value = TRAILING_LABEL.sub("", " ".join(match.group(1).split()))
    return value.strip(" :-.,")[:cap]


def clean_title(title: str) -> str:
    """Decision 26: strip the opaque identifiers 37% of titles carry.

    `994831: SAFETY AND TECHNICAL RESCUE EQUIPMENT` and `DLT Quote# 5366584 for
    enterprise technical support fees` put tokens in the embedding that carry no
    meaning and no similarity. Measured 15/9/2026: the rule empties no title and
    shortens three below ten characters, two of which were already noise.
    """
    title = re.sub(r"^\s*\w*\d{4,}\s*[:\-]\s*", "", title)
    title = re.sub(r"Quote\s*#?\s*\d+", "", title, flags=re.I)
    title = re.sub(r"\b\d{4,}\b", "", title)
    return " ".join(title.split()).strip(" :-.,")


def extract(cls: str, text: str) -> dict:
    if cls == "contract_summary":
        return {"title": clean_title(field(text, "Title of Contract")),
                "brief": field(text, "Brief Description of Work"),
                "area": field(text, "Procurement Services Contract Area", 60)}
    if cls == "modification":
        return {"title": clean_title(field(text, "Title of Contract")),
                **mod_table(text)}
    if cls == "ordinance":
        line = re.search(r"((?:Mod to PO|New P\.?O).{0,200})", text, re.S | re.I)
        return {"authorisation": " ".join(line.group(1).split()) if line else ""}
    return {}


# The modification table is a grid, and the text layer interleaves its columns:
# after the header row comes "<request number> <REASON>", then the description
# wraps over the following lines until a date ends the row. Matching the column
# labels individually captures the request number as if it were the reason.
MOD_TABLE = re.compile(
    r"Mod\s*Req\s*Number\s*Mod\s*Reason\s*Description\s*"
    r"\d+\s+(?P<reason>[A-Z][A-Z0-9 &/,\.\-]{2,60}?)\s*\n"
    r"(?P<description>.*?)"
    r"(?=\n\s*\d{1,2}/\d{1,2}/\d{2,4}|\n\s*Term of Contract|\Z)",
    re.S)


def mod_table(text: str) -> dict:
    match = MOD_TABLE.search(text)
    if not match:
        return {"mod_reason": "", "mod_description": ""}
    return {"mod_reason": " ".join(match.group("reason").split()),
            "mod_description": " ".join(match.group("description").split())[:400]}


def is_near_duplicate(value: str, lines: list[str], threshold: float = 0.85) -> bool:
    """Decision 26 asks for similarity, not equality, and the OCR is why.

    The same title read twice comes back as `SLE VECTOR MOSQUITO ABATEMENT` and
    `SLE VECTOR MOSeUITO ABATEMENT`: two strings, one fact, and an exact test
    keeps both.
    """
    candidate = re.sub(r"[^A-Z0-9]", "", value.upper())
    if not candidate:
        return True
    for line in lines:
        existing = re.sub(r"[^A-Z0-9]", "", line.upper())
        if not existing:
            continue
        if SequenceMatcher(None, candidate, existing).ratio() >= threshold:
            return True
    return False


def assemble(parts: list[dict]) -> str:
    """Decision 26: one atemporal text per contract.

    No dates, no amounts, no ordering: the chronology lives on ContractRecord,
    where it is complete, rather than here, where it exists for 69 contracts.
    Lines are deduplicated because a contract with ten modifications repeats the
    same title ten times.
    """
    lines: list[str] = []
    for part in parts:
        for key in ("title", "brief", "mod_description", "mod_reason", "authorisation"):
            value = (part.get(key) or "").strip()
            if value and not is_near_duplicate(value, lines):
                lines.append(value)
    return "\n".join(lines)


# Finding the scope in the body is not a regex problem. The phrase "scope of
# work" appears in clauses that merely refer to it -- joint venture insurance,
# invoicing terms -- as often as it heads the content: measured 15/9/2026, of
# 395 documents carrying the phrase the rule below keeps 355, and of three
# sampled passages one was the scope and two were clauses about it. So this
# stage only *nominates*; deciding is the summariser's job, decision 25.
SCOPE = re.compile(r"scope of (the )?(work|services)", re.I)
EXTERNAL = re.compile(r"incorporated (herein )?by (this )?reference|see attached"
                      r"|attached (hereto )?as exhibit", re.I)
TABLE_OF_CONTENTS = re.compile(r"\.{4,}")
SCOPE_VERBS = re.compile(r"\b(shall|will|provides?|includes?|perform|furnish|means)\b", re.I)

# The scope sits in the opening pages; a document runs to 1,635 pages and
# reading them all to the end costs far more than it returns. Counted by
# position in the document, not by printed page number.
BODY_PAGES = 30


def looks_like_prose(chunk: str) -> bool:
    words = chunk.split()
    if TABLE_OF_CONTENTS.search(chunk[:200]) or len(words) < 40:
        return False
    if sum(1 for w in words[:60] if w.isupper()) > 40:
        return False
    return bool(SCOPE_VERBS.search(chunk))


def scope_candidates(body: str, window: int = 1200) -> list[str]:
    """Passages a summariser should look at, best guess first."""
    found = []
    for match in SCOPE.finditer(body):
        chunk = " ".join(body[match.start():match.start() + window].split())
        if EXTERNAL.search(chunk[:250]) or not looks_like_prose(chunk):
            continue
        found.append(chunk)
        if len(found) == 2:
            break
    return found


REFERENCE = re.compile(r"INCORPORATED HEREIN BY REFERENCE|SEE ATTACHED", re.I)

READ = """
MATCH (doc:Document)-[:HAS_PAGE]->(p:Page)
WITH doc, p ORDER BY p.page
// Cut by position, not by p.page: the PII filter withholds pages, so 18
// documents start at page 31 or later and a numeric cap drops them whole.
WITH doc, collect(p.text)[..$body_pages] AS pages
MATCH (doc)<-[:HAS_DOCUMENT]-(:ContractRecord)-[:INCLUDED_IN_CONTRACT]->(c:Contract)
RETURN c.id AS contract, doc.id AS doc, head(pages) AS first,
       reduce(a = '', t IN pages[1..] | a + '\n' + t) AS body
"""

WRITE = """
UNWIND $rows AS row
MATCH (c:Contract {id: row.contract})
MERGE (c)-[:HAS_DESCRIPTION]->(d:ContractDescription {id: row.id})
SET d.text = row.text, d.tier = row.tier, d.builtFrom = row.builtFrom,
    d.sourceDocuments = row.sourceDocuments,
    d.incorporatesByReference = row.incorporatesByReference
"""


def load_summaries(path: Path) -> dict[str, list[str]]:
    """What the summariser produced last time it ran, by contract.

    Read rather than recomputed: the corpus rule forbids live inference in the
    demos, so the committed file is the artefact and this file only consumes it.
    An absent file is normal before the first run and is reported, not raised.
    """
    if not path.exists():
        return {}
    by_contract: dict[str, list[str]] = defaultdict(list)
    for item in json.loads(path.read_text())["summaries"]:
        summary = item["summary"].strip()
        # Two passages of the same contract often paraphrase each other, so the
        # same similarity test that de-duplicates extracted fields applies here.
        if summary and not is_near_duplicate(summary, by_contract[item["contract"]]):
            by_contract[item["contract"]].append(summary)
    return by_contract


def build(limit: int | None, summaries: dict[str, list[str]] | None = None) -> dict:
    """Run the deterministic stages and report what the summariser still owes.

    Two things come out: descriptions assembled from labelled fields, which are
    finished, and the passages nominated for summarising, which are not. They
    are kept apart because the second half needs a model and the corpus rule
    forbids live inference in the demos -- it runs once and its output is
    committed.
    """
    from database.lpg.graph_db import Neo4jDB

    db = Neo4jDB()
    by_contract: dict[str, list[dict]] = defaultdict(list)
    pending: list[dict] = []
    classes, how = Counter(), Counter()
    seen = 0
    try:
        with db._driver.session(database=db._database) as session:
            for row in session.run(READ, body_pages=BODY_PAGES):
                if limit and seen >= limit:
                    break
                seen += 1
                first, body = row["first"] or "", row["body"] or ""
                cls, recognised, decoded = classify(first)
                classes[cls] += 1
                how[recognised + (" +decoded" if decoded else "")] += 1
                route = ROUTES.get(cls)
                if route is None:
                    continue

                candidates = scope_candidates(body)
                if candidates:
                    pending.append({"contract": row["contract"], "doc": row["doc"],
                                    "cls": cls, "candidates": candidates})
                if route != "extract":
                    continue

                text = unshift(first) if decoded else first
                by_contract[row["contract"]].append(
                    {"doc": row["doc"], "cls": cls,
                     "reference": bool(REFERENCE.search(first) or REFERENCE.search(body)),
                     **extract(cls, text)})
    finally:
        db.close()

    summaries = summaries or {}
    for contract in summaries:
        by_contract.setdefault(contract, [])

    rows, empty = [], 0
    for contract, parts in by_contract.items():
        text = assemble(parts)
        for summary in summaries.get(contract, []):
            text = f"{text}\n{summary}" if text else summary
        if not text:
            # Decision 25: a routed document that yields nothing disappears with
            # nothing to mark it, so the count is printed rather than dropped.
            empty += 1
            continue
        # Only prose earns the dense index. The deterministic branch produces
        # labels -- a title, a modification reason -- and 133-character labels
        # cluster: measured 15/9/2026, `Demolition Services` reached the top 5
        # for 3 of 12 unrelated questions. It is the reason decision 27 sent T2
        # to full text, at 30 characters instead of 133.
        tier = "T1" if summaries.get(contract) else "T2"
        rows.append({"contract": contract, "id": DESC_PREFIX + contract, "text": text,
                     "tier": tier,
                     "builtFrom": sorted({p["cls"] for p in parts}
                                         | ({"summary"} if summaries.get(contract) else set())),
                     "sourceDocuments": sorted(p["doc"] for p in parts),
                     "incorporatesByReference": any(p["reference"] for p in parts)})
    return {"rows": rows, "classes": classes, "how": how, "empty": empty,
            "pending": pending, "documents": seen,
            "summarised": len(set(summaries) & {r["contract"] for r in rows})}


# ---------------------------------------------------------------- summarising

# Read from the environment with the names `pipelines/config.py` already uses,
# so one export points both at the same endpoint. The domain is reserved per
# service and survives a runtime restart, which is why it can be a default.
LLM_URL = os.environ.get("KGTP_LLM_BASE_URL", "https://kgtp-llm.ngrok-free.app/v1")
LLM_KEY = os.environ.get("KGTP_LLM_API_KEY", "teacher-key")
LLM_MODEL = os.environ.get("KGTP_LLM_MODEL", "Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8")

SUMMARY_PROMPT = """You are reading one passage from a City of Chicago contract.

Decide whether it describes WHAT THE CITY IS BUYING -- the goods, services or
work the contractor must deliver.

It does NOT count if the passage is about insurance, invoicing, payment terms,
indemnity, joint venture governance, or if it only refers to a scope defined
somewhere else.

Write the summary as a direct description of the goods, services or work --
"Snow removal and de-icing for arterial streets", not "The passage describes
the scope of services for...". The summary is indexed for search, so words
about the document itself are noise.

Answer with JSON and nothing else:
{"is_scope": true, "summary": "<at most 2 sentences, plain description>"}
{"is_scope": false, "summary": ""}

Passage:
"""


def client():
    from openai import OpenAI

    # The proxy answers 429 above its per-key rate and 503 when its concurrency
    # semaphore is full for 30s. Both are transient and both are retried here.
    return OpenAI(base_url=LLM_URL, api_key=LLM_KEY, timeout=120.0, max_retries=5)


def summarise_one(api, passage: str) -> dict:
    """One judgement and one summary, or a reason it produced neither.

    The model decides as well as summarises, because the regex that nominated
    this passage cannot tell the scope from a clause that merely mentions it --
    of three sampled passages on 15/9/2026, one was the scope and two were not.
    """
    try:
        reply = api.chat.completions.create(
            model=LLM_MODEL, temperature=0, max_tokens=200,
            messages=[{"role": "user", "content": SUMMARY_PROMPT + passage[:4000]}])
        content = reply.choices[0].message.content or ""
    except Exception as error:                      # noqa: BLE001 - counted, not raised
        return {"error": type(error).__name__, "is_scope": False, "summary": ""}

    # A served model can wrap JSON in prose or a fence whatever the prompt asks.
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        return {"error": "no JSON in reply", "is_scope": False, "summary": ""}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"error": "bad JSON in reply", "is_scope": False, "summary": ""}
    return {"is_scope": bool(parsed.get("is_scope")),
            "summary": " ".join(str(parsed.get("summary", "")).split())}


def summarise(pending: list[dict], workers: int, out_path: Path) -> dict:
    """Decision 25: this runs once, by the instructor, and its output is committed.

    the corpus rule forbids live inference in the demos, so what a student sees
    is this file, not this endpoint. The model and the prompt are written beside
    the results for the same reason decision 19 commits the embedding recipe:
    a summary whose prompt is unknown cannot be reproduced or argued with.
    """
    results, errors = [], Counter()
    work = [(item, passage) for item in pending for passage in item["candidates"]]
    print(f"passages to judge: {len(work)} from {len(pending)} documents")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        api = client()
        futures = {pool.submit(summarise_one, api, passage): (item, passage)
                   for item, passage in work}
        for done, future in enumerate(as_completed(futures), 1):
            item, passage = futures[future]
            verdict = future.result()
            if verdict.get("error"):
                errors[verdict["error"]] += 1
            elif verdict["is_scope"] and verdict["summary"]:
                results.append({"contract": item["contract"], "doc": item["doc"],
                                "cls": item["cls"], "summary": verdict["summary"],
                                "passage": passage[:400]})
            if done % 50 == 0:
                print(f"  {done}/{len(work)}  kept {len(results)}  errors {sum(errors.values())}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(
        {"model": LLM_MODEL, "endpoint": LLM_URL, "prompt": SUMMARY_PROMPT,
         "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "summaries": results}, indent=2))
    print(f"\nkept {len(results)} summaries of {len(work)} passages "
          f"({len({r['contract'] for r in results})} contracts)")
    for name, n in errors.most_common():
        print(f"  error {name}: {n}")
    print(f"written to {out_path}")
    return {"results": results, "errors": errors}




# ------------------------------------------------------------------ embedding

EMBED_URL = os.environ.get("KGTP_EMBEDDINGS_BASE_URL",
                           "https://kgtp-embed.ngrok-free.app/v1")
EMBED_KEY = os.environ.get("KGTP_EMBEDDINGS_API_KEY", "teacher-key")
EMBED_MODEL = os.environ.get("KGTP_EMBEDDINGS_MODEL", "Qwen/Qwen3-Embedding-0.6B")

STORE_VECTORS = """
UNWIND $rows AS row
MATCH (d:ContractDescription {id: row.id})
CALL db.create.setNodeVectorProperty(d, 'embedding', row.embedding)
"""


def embed(batch_size: int = 64) -> int:
    """Decision 19: one index per unit, and the dimension is checked, not assumed.

    A second vector index beside `page_embedding`, not a replacement for it:
    decision 27 keeps both alive so the same question can be asked of the pages
    and of the descriptions, and the two answers compared. The vectors are
    derived and never committed -- what is committed is this file, the text in
    the graph, and the pinned model above.
    """
    from database.lpg.graph_db import Neo4jDB
    from openai import OpenAI

    api = OpenAI(base_url=EMBED_URL, api_key=EMBED_KEY, timeout=120.0, max_retries=5)
    db = Neo4jDB()
    done = 0
    try:
        with db._driver.session(database=db._database) as session:
            rows = [(r["id"], r["text"]) for r in session.run(
                "MATCH (d:ContractDescription) "
                "WHERE d.text IS NOT NULL AND d.tier = 'T1' "
                "RETURN d.id AS id, d.text AS text")]
            print(f"descriptions to embed: {len(rows)}")

            dimension = None
            for start in range(0, len(rows), batch_size):
                chunk = rows[start:start + batch_size]
                reply = api.embeddings.create(
                    model=EMBED_MODEL, input=[text for _, text in chunk])
                vectors = [item.embedding for item in reply.data]

                if dimension is None:
                    dimension = len(vectors[0])
                    print(f"dimension reported by the endpoint: {dimension}")
                    session.run(
                        "CREATE VECTOR INDEX description_embedding IF NOT EXISTS "
                        "FOR (d:ContractDescription) ON (d.embedding) OPTIONS "
                        "{indexConfig: {`vector.dimensions`: $dimension, "
                        "`vector.similarity_function`: 'cosine'}}", dimension=dimension)
                elif len(vectors[0]) != dimension:
                    # The endpoint can be restarted onto another revision between
                    # batches, and a mixed-dimension index is silently useless.
                    raise RuntimeError(
                        f"dimension changed mid-run: {dimension} -> {len(vectors[0])}")

                session.run(STORE_VECTORS, rows=[
                    {"id": node_id, "embedding": vector}
                    for (node_id, _), vector in zip(chunk, vectors)])
                done += len(chunk)
                print(f"  {done}/{len(rows)}")

            session.run("CALL db.awaitIndexes(300)")
    finally:
        db.close()
    return done




# ----------------------------------------------------------------- neighbours

# Decision 33: the name written here is the one of the group member that holds
# the most contracts, not `OrganizationGroup.name`. The group's own canonical
# name is one of its members' names but is not chosen for prominence -- L28 is
# called `WALSH CONSTRUCTIONQ`, a node with one contract, over `WALSH
# CONSTRUCTION COMPANY OF ILL` which has 48.
NEIGHBOURS = """
MATCH (c:Contract)-[:HAS_DESCRIPTION]->(d:ContractDescription)
WHERE d.tier = 'T1'
OPTIONAL MATCH (c)-[:HAS_VENDOR]->(:Organization)-[:BELONGS_TO_ORG_GROUP]->(g)
OPTIONAL MATCH (m:Organization)-[:BELONGS_TO_ORG_GROUP]->(g)
OPTIONAL MATCH (m)<-[:HAS_VENDOR]-(mc:Contract)
WITH c, d, g, m, count(DISTINCT mc) AS weight
ORDER BY weight DESC
WITH c, d, g, collect(m.name)[0] AS vendor
OPTIONAL MATCH (dep:Department)-[:ASSIGNS_CONTRACT]->(c)
RETURN d.id AS id, d.text AS text,
       collect(DISTINCT vendor) AS vendors,
       collect(DISTINCT dep.id) AS departments
"""

STORE_NEIGHBOURS = """
UNWIND $rows AS row
MATCH (d:ContractDescription {id: row.id})
SET d.neighbourText = row.text
"""


def neighbour_text(text: str, vendors: list, departments: list) -> str:
    """Scenario 2 of the paper, §3.2: one-hop neighbours grouped by relation type.

    Grouped rather than listed as triples, which is the paper's own saving, and
    written once at build time rather than read at query time -- that is what
    separates scenario 2 from scenario 5, and the difference is easy to lose.
    """
    lines = [text]
    for label, values in (("HAS_VENDOR", vendors), ("ASSIGNS_CONTRACT", departments)):
        named = sorted({v for v in values if v})
        if named:
            lines.append(f"{label}: {', '.join(named)}")
    return "\n".join(lines)


def attach_neighbours() -> int:
    from database.lpg.graph_db import Neo4jDB

    db = Neo4jDB()
    try:
        with db._driver.session(database=db._database) as session:
            rows = [{"id": r["id"],
                     "text": neighbour_text(r["text"], r["vendors"], r["departments"])}
                    for r in session.run(NEIGHBOURS)]
            for start in range(0, len(rows), 500):
                session.run(STORE_NEIGHBOURS, rows=rows[start:start + 500])
    finally:
        db.close()
    return len(rows)


def embed_neighbours(batch_size: int = 64) -> int:
    """A second vector beside the first, on the same node.

    Decision 27 wants the configurations measured side by side, so the text with
    neighbours does not overwrite the text without them: both vectors live, and
    the same question can be asked of each.
    """
    from database.lpg.graph_db import Neo4jDB
    from openai import OpenAI

    api = OpenAI(base_url=EMBED_URL, api_key=EMBED_KEY, timeout=120.0, max_retries=5)
    db = Neo4jDB()
    done = 0
    try:
        with db._driver.session(database=db._database) as session:
            rows = [(r["id"], r["t"]) for r in session.run(
                "MATCH (d:ContractDescription) WHERE d.neighbourText IS NOT NULL "
                "RETURN d.id AS id, d.neighbourText AS t")]
            session.run(
                "CREATE VECTOR INDEX neighbour_embedding IF NOT EXISTS "
                "FOR (d:ContractDescription) ON (d.neighbourEmbedding) OPTIONS "
                "{indexConfig: {`vector.dimensions`: 1024, "
                "`vector.similarity_function`: 'cosine'}}")
            for start in range(0, len(rows), batch_size):
                chunk = rows[start:start + batch_size]
                reply = api.embeddings.create(
                    model=EMBED_MODEL, input=[text for _, text in chunk])
                session.run(
                    "UNWIND $rows AS row MATCH (d:ContractDescription {id: row.id}) "
                    "CALL db.create.setNodeVectorProperty(d, 'neighbourEmbedding', row.v)",
                    rows=[{"id": i, "v": item.embedding}
                          for (i, _), item in zip(chunk, reply.data)])
                done += len(chunk)
            session.run("CALL db.awaitIndexes(300)")
    finally:
        db.close()
    return done


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    ap.add_argument("--limit", type=int, help="stop after this many documents")
    ap.add_argument("--neighbours", action="store_true",
                    help="attach one-hop neighbours to the T1 descriptions and embed them")
    ap.add_argument("--embed", action="store_true",
                    help="vectorise the descriptions already in the graph")
    ap.add_argument("--summarise", action="store_true",
                    help="call the model on the nominated passages and write them out")
    ap.add_argument("--workers", type=int, default=16,
                    help="requests in flight; the proxy caps this too")
    ap.add_argument("--out", default="../../data/chicago/descriptions/summaries.json")
    args = ap.parse_args()

    if args.neighbours:
        print(f"neighbours attached: {attach_neighbours()}")
        print(f"embedded with neighbours: {embed_neighbours()}")
        return 0

    if args.embed:
        print(f"embedded: {embed()} descriptions")
        return 0

    summaries = {} if args.summarise else load_summaries(Path(args.out))
    out = build(args.limit, summaries)
    rows, classes, how, empty = out['rows'], out['classes'], out['how'], out['empty']
    total = sum(classes.values())

    print(f"documents read: {out['documents']}")
    for name, n in classes.most_common():
        print(f"  {name:28} {n:>5}  -> {ROUTES.get(name, 'excluded')}")
    print("\nrecognised by")
    for name, n in how.most_common():
        print(f"  {name:28} {n:>5}")

    routable = sum(n for c, n in classes.items() if ROUTES.get(c) == "extract")
    lengths = sorted(len(r["text"]) for r in rows)
    print(f"\ncontracts with a description: {len(rows)}")
    print(f"  routed but extracted nothing:  {empty}")
    print(f"  from {routable} documents on the extract branch")
    print(f"  text length: median {lengths[len(lengths) // 2] if lengths else 0}, "
          f"max {lengths[-1] if lengths else 0}")
    print(f"  of which carry a summary:      {out['summarised']}")
    print(f"  marked incorporatesByReference: "
          f"{sum(1 for r in rows if r['incorporatesByReference'])}")

    pending = out["pending"]
    docs_by_route = Counter(ROUTES[p["cls"]] for p in pending)
    print(f"\nawaiting the summariser: {len(pending)} documents, "
          f"{len({p['contract'] for p in pending})} contracts")
    for route, n in docs_by_route.most_common():
        print(f"  nominated on the {route} branch: {n}")

    if args.summarise:
        summarise(out["pending"], args.workers, Path(args.out))
        return 0

    if args.dry_run:
        print("\ndry run, nothing written")
        for row in rows[:3]:
            print(f"\n--- {row['contract']} ({', '.join(row['builtFrom'])})")
            print("   " + row["text"][:220].replace("\n", "\n   "))
        return 0

    from database.lpg.graph_db import Neo4jDB
    db = Neo4jDB()
    try:
        with db._driver.session(database=db._database) as session:
            session.run(
                "CREATE CONSTRAINT contract_description_id IF NOT EXISTS "
                "FOR (d:ContractDescription) REQUIRE d.id IS UNIQUE")
            for i in range(0, len(rows), 1000):
                session.run(WRITE, rows=rows[i:i + 1000])
    finally:
        db.close()
    print(f"\nwritten: {len(rows)} ContractDescription nodes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
