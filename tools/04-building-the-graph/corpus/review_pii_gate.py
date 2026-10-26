#!/usr/bin/env python3
"""Make the PII-excluded pages readable, so a person can triage them.

Instructor-only. The gate between `extract` and `documents`:
the pages the filter held back are read by hand before anything is committed.

    python tools/04-building-the-graph/corpus/review_pii_gate.py data/chicago/2022-2026

Reads `corpus/_extraction_report.json`, re-extracts the text of each held page
from the PDF, and writes three files under `<dir>/pii_gate/`:

    held_pages.jsonl   one record per held page, text included
    review.html        the same pages, matches highlighted, in triage order
    decisions.csv      one row per page with an empty `decision` column

The text has to be re-extracted because the filter logs its reasons and never
the page (see `pii_score` in extract_contracts.py), so the only copy of a held
page is the PDF it came from. That makes this step depend on the PDFs still
being on disk: it runs before they are deleted, not after.

Triage order is the point of the HTML. Tier A is the pages carrying
`HINT_maybe_institutional` -- a roster of agencies counts like a roster of
people, and these are where over-dropping costs real contract text. Tier B is
the low scores without that hint, tier C the rest. The filter is deliberately
biased towards dropping, so this ordering puts the plausible mistakes first
instead of leaving them in page order among the obvious ones.

Nothing here decides anything: `decision` is left empty on purpose. Writing
the kept pages back into the corpus is a separate step, because reinstating a
page is the one action in this pipeline that undoes a drop.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from corpus.extract_contracts import (  # noqa: E402
    EMAIL_RE,
    ORG_MARKER_RE,
    PERSONAL_EMAIL_DOMAINS,
    PHONE_RE,
    RESIDENTIAL_RE,
    STREET_RE,
)

# Longest match wins where two patterns overlap, so a street address inside a
# residential marker is not cut in half by the highlighter.
HIGHLIGHTS = (
    ("phone", PHONE_RE),
    ("street", STREET_RE),
    ("residential", RESIDENTIAL_RE),
    ("org", ORG_MARKER_RE),
)


def page_text(pdf: Path, page: int) -> str:
    """One page of raw text, by the same extractor the corpus was built with."""
    out = subprocess.run(
        ["pdftotext", "-raw", "-enc", "UTF-8", "-f", str(page), "-l", str(page),
         str(pdf), "-"],
        capture_output=True, text=True, check=True,
    )
    return out.stdout


def tier(reasons: list[str], score: int) -> str:
    if any(r.startswith("HINT_maybe_institutional") for r in reasons):
        return "A"
    return "B" if score <= 2 else "C"


def spans(text: str) -> list[tuple[int, int, str]]:
    found: list[tuple[int, int, str]] = []
    for m in EMAIL_RE.finditer(text):
        personal = m.group(1).lower() in PERSONAL_EMAIL_DOMAINS
        found.append((m.start(), m.end(), "email" if personal else "email-org"))
    for label, pattern in HIGHLIGHTS:
        for m in pattern.finditer(text):
            found.append((m.start(), m.end(), label))

    found.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    merged: list[tuple[int, int, str]] = []
    for start, end, label in found:
        if merged and start < merged[-1][1]:
            continue
        merged.append((start, end, label))
    return merged


def marked_html(text: str) -> str:
    out, cursor = [], 0
    for start, end, label in spans(text):
        out.append(html.escape(text[cursor:start]))
        out.append(f'<mark class="{label}">{html.escape(text[start:end])}</mark>')
        cursor = end
    out.append(html.escape(text[cursor:]))
    return "".join(out)


CSS = """
:root { --bg:#fff; --fg:#1a1a1a; --muted:#666; --line:#e2e2e2; --card:#fafafa; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#1a1a1a; --fg:#e8e8e8; --muted:#999; --line:#333; --card:#222; }
}
body { background:var(--bg); color:var(--fg); font:15px/1.6 -apple-system,system-ui,sans-serif;
       margin:0 auto; padding:24px 16px; max-width:900px; }
h1 { font-size:21px; } h2 { font-size:16px; margin:0 0 4px; }
.meta { color:var(--muted); font-size:13px; }
.page { border:1px solid var(--line); border-radius:8px; padding:16px; margin:20px 0;
        background:var(--card); }
.tier { display:inline-block; font-weight:600; font-size:12px; padding:1px 7px;
        border-radius:10px; border:1px solid var(--line); margin-right:6px; }
pre { white-space:pre-wrap; word-break:break-word; font:12px/1.5 ui-monospace,monospace;
      max-height:360px; overflow:auto; border-top:1px solid var(--line); padding-top:10px;
      margin:10px 0 0; }
mark { background:none; border-radius:2px; padding:0 1px; }
mark.email { background:#ff4d4d; color:#fff; }
mark.phone { background:#ffd24d; color:#1a1a1a; }
mark.street { background:#9ad1ff; color:#1a1a1a; }
mark.residential { background:#ff8ad1; color:#1a1a1a; }
mark.email-org, mark.org { outline:1px dotted var(--muted); }
.legend span { margin-right:12px; font-size:12px; }
"""

LEGEND = (
    '<p class="legend">'
    '<span><mark class="email">personal mailbox</mark></span>'
    '<span><mark class="phone">phone</mark></span>'
    '<span><mark class="street">street address</mark></span>'
    '<span><mark class="residential">residential marker</mark></span>'
    '<span><mark class="org">organisation marker (hint only)</mark></span></p>'
)


def write_html(records: list[dict], out: Path, source: Path) -> None:
    counts = {t: sum(1 for r in records if r["tier"] == t) for t in "ABC"}
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<title>PII gate review</title>",
        f"<style>{CSS}</style></head><body>",
        "<h1>PII gate review</h1>",
        f'<p class="meta">{len(records)} held pages from {source}. '
        f'Tier A {counts["A"]} (possibly institutional, read these first) · '
        f'Tier B {counts["B"]} (low score) · Tier C {counts["C"]}. '
        "Record every verdict in decisions.csv; this page writes nothing.</p>",
        LEGEND,
    ]
    for n, r in enumerate(records, start=1):
        parts.append(
            f'<div class="page"><h2><span class="tier">{r["tier"]}</span>'
            f'{html.escape(r["doc_id"])} &middot; page {r["page"]}'
            f' <span class="meta">({n}/{len(records)})</span></h2>'
            f'<p class="meta">score {r["score"]} &middot; '
            f'{html.escape(", ".join(r["reasons"]))}<br>'
            f'{html.escape(r["producer"] or "(no producer)")}</p>'
            f'<pre>{marked_html(r["text"])}</pre></div>'
        )
    parts.append("</body></html>")
    out.write_text("".join(parts))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus_dir", type=Path,
                        help="e.g. data/chicago/2022-2026")
    parser.add_argument("--pdfs", type=Path, default=None,
                        help="defaults to <corpus_dir>/pdfs")
    parser.add_argument("--out", type=Path, default=None,
                        help="defaults to <corpus_dir>/pii_gate")
    args = parser.parse_args()

    report_path = args.corpus_dir / "corpus" / "_extraction_report.json"
    pdf_dir = args.pdfs or args.corpus_dir / "pdfs"
    out_dir = args.out or args.corpus_dir / "pii_gate"
    out_dir.mkdir(parents=True, exist_ok=True)

    report = json.loads(report_path.read_text())
    records = []
    missing = []
    for doc in report:
        for ex in doc.get("pii_exclusions", []):
            pdf = pdf_dir / doc["file"]
            if not pdf.exists():
                missing.append(doc["file"])
                continue
            records.append({
                "doc_id": doc["doc_id"],
                "file": doc["file"],
                "producer": doc.get("producer"),
                "page": ex["page"],
                "score": ex["score"],
                "reasons": ex["reasons"],
                "signals": ex["signals"],
                "tier": tier(ex["reasons"], ex["score"]),
                "text": page_text(pdf, ex["page"]),
            })

    records.sort(key=lambda r: (r["tier"], r["score"], r["doc_id"], r["page"]))

    with open(out_dir / "held_pages.jsonl", "w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with open(out_dir / "decisions.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tier", "doc_id", "page", "score", "reasons", "decision", "note"])
        for r in records:
            w.writerow([r["tier"], r["doc_id"], r["page"], r["score"],
                        "; ".join(r["reasons"]), "", ""])

    write_html(records, out_dir / "review.html", report_path.parent)

    by_tier = {t: sum(1 for r in records if r["tier"] == t) for t in "ABC"}
    print(f"{len(records)} held pages  (A {by_tier['A']}  B {by_tier['B']}  C {by_tier['C']})")
    if missing:
        # The PDFs are the only copy of a held page, so a gap here is a gap in
        # what can be reviewed at all -- it is reported, never passed over.
        print(f"PDF missing for {len(missing)} document(s): "
              f"{', '.join(sorted(set(missing))[:5])}", file=sys.stderr)
    print(f"wrote {out_dir}/review.html, held_pages.jsonl, decisions.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
