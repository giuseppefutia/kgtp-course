#!/usr/bin/env python3
"""Extract clean per-page text from Chicago contract PDFs into JSONL.

Handles the two document classes observed in the wild:
  A) scanned pages + municipal OCR layer (Power PDF Create) -- prone to
     word-duplication artifacts under layout-mode extraction
  B) born-digital (Word -> Distiller) with embedded scanned exhibits

Strategy: pdftotext in raw mode (no layout reconstruction), one call per
document, split on form feeds. Pages below --min-chars are dropped but
logged. A duplicate-bigram ratio flags any residual OCR-overlay
duplication for manual review instead of silently poisoning the corpus.

Run from the repo root:
    python tools/04-building-the-graph/extract_contracts.py raw_pdfs/ \
        --out data/chicago/corpus/ \
        --manifest data/chicago/corpus_manifest.csv

If a manifest is given, files named <po_number>.pdf (or matching the
pdf_url basename) inherit the join metadata; otherwise provenance is
just the filename.

Requires poppler-utils (pdftotext, pdfinfo) on PATH.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

WORD_RE = re.compile(r"[A-Za-z][A-Za-z'&.-]+")

# --- PII filter ------------------------------------------------------------
# Policy: inclusion is decided by ROLE, not by public availability. Officials
# signing in their official capacity stay; directories of personal contact
# details go.
#
# The discriminator is multiplicity, not presence. A legitimate contract page
# is full of addresses and phone numbers -- the vendor's registered office, the
# notices clause, ACORD certificates. What a contract page does NOT have is a
# dozen individuals each paired with a home address and a personal phone. So
# single business contacts score nothing and density is what accumulates.
#
# This filter runs before anything is committed and its decisions are
# irreversible in practice, so it is deliberately biased towards dropping.

EMAIL_RE = re.compile(r"\b[\w.+-]+@([\w-]+(?:\.[\w-]+)+)\b")
PHONE_RE = re.compile(r"\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")
STREET_RE = re.compile(
    r"\b\d{1,6}\s+(?:[NSEW]\.?\s+)?[A-Za-z][\w.'-]*(?:\s+[A-Za-z][\w.'-]*){0,3}\s+"
    r"(?:ST|STREET|AVE|AVENUE|BLVD|BOULEVARD|RD|ROAD|DR|DRIVE|LN|LANE|CT|COURT|"
    r"PL|PLACE|WAY|TER|TERRACE|PKWY|PARKWAY|HWY|CIR|CIRCLE)\b\.?",
    re.IGNORECASE,
)
RESIDENTIAL_RE = re.compile(
    r"\b(?:APT\.?|APARTMENT|UNIT\s*#?\d|#\s*\d+[A-Z]?\b|HOME\s+(?:PHONE|ADDRESS)|"
    r"RESIDENCE|CELL(?:\s+PHONE)?)\b",
    re.IGNORECASE,
)

# Mailbox domains that indicate a private individual rather than an
# organisation. An institutional address (a .gov, or the vendor's own domain)
# is a person acting in a role and is not by itself a reason to drop a page.
# Contact density means nothing on its own: a page listing thirty agencies is as
# dense as a page listing thirty people. These markers say the entries are
# organisations, which under the role-not-findability rule belong in the corpus.
ORG_MARKER_RE = re.compile(
    r"\b(?:INC|LLC|L\.L\.C|CORP|CORPORATION|CO|LTD|LLP|PLC|COMPANY|CENTER|CENTRE|"
    r"ASSOCIATION|ASSN|LEAGUE|FOUNDATION|SOCIETY|INSTITUTE|COUNCIL|AGENCY|BUREAU|"
    r"DEPARTMENT|DEPT|DIVISION|AUTHORITY|COMMISSION|UNIVERSITY|COLLEGE|SCHOOL|"
    r"HOSPITAL|CLINIC|CHURCH|MINISTRIES|SERVICES|PROGRAM|PARTNERS|GROUP|"
    r"ENTERPRISES|HOLDINGS|CONSTRUCTION|CONSULTING)\b\.?",
    re.IGNORECASE,
)

PERSONAL_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "hotmail.com",
    "outlook.com", "live.com", "msn.com", "aol.com", "icloud.com", "me.com",
    "mac.com", "comcast.net", "sbcglobal.net", "att.net", "verizon.net",
    "earthlink.net", "juno.com", "prodigy.net", "ameritech.net", "mail.com",
}


def pii_signals(text: str) -> dict[str, int]:
    """Count the distinct personal-contact markers on a page."""
    personal = {
        m.group(0).lower()
        for m in EMAIL_RE.finditer(text)
        if m.group(1).lower() in PERSONAL_EMAIL_DOMAINS
    }
    return {
        "personal_emails": len(personal),
        "phones": len({m.group(0) for m in PHONE_RE.finditer(text)}),
        "street_addresses": len({m.group(0).lower() for m in STREET_RE.finditer(text)}),
        "residential_markers": len(RESIDENTIAL_RE.findall(text)),
        "org_markers": len(ORG_MARKER_RE.findall(text)),
    }


def pii_score(signals: dict[str, int]) -> tuple[int, list[str]]:
    """Score a page and say why. Reasons are logged; the text never is."""
    score, reasons = 0, []

    if signals["personal_emails"]:
        score += 1
        reasons.append(f"personal_email x{signals['personal_emails']}")
    if signals["personal_emails"] >= 3:
        score += 1
        reasons.append("personal_email_cluster")

    for key, label in (("phones", "phone"), ("street_addresses", "street_address")):
        n = signals[key]
        if n >= 6:
            score += 2
            reasons.append(f"{label}_dense x{n}")
        elif n >= 3:
            score += 1
            reasons.append(f"{label}_multiple x{n}")

    # A residential marker only matters next to a way of reaching the person.
    if signals["residential_markers"] and (signals["phones"] or signals["personal_emails"]):
        score += 1
        reasons.append(f"residential_marker x{signals['residential_markers']}")

    # A page may be dense with contacts because it lists organisations rather
    # than people -- a roster of public workforce centres reads exactly like a
    # board directory to the counters above.
    #
    # This is only ever a HINT for the reviewer, never a reason to keep the
    # page. Trying it as an override was measured against the real documents on
    # 2026-08-07 and let page 55 of PO C029840 -- an actual board directory with
    # home addresses -- back into the corpus, because degraded OCR scatters
    # enough tokens like CO, CENTER and DR to read as institutional. On the one
    # irreversible step of the pipeline, over-dropping costs a page of contract
    # text; under-dropping publishes someone's home address. So the score is
    # left untouched and the exclusion list, which is short enough to read, is
    # triaged by hand.
    if signals["org_markers"] >= 3 and not signals["personal_emails"]:
        reasons.append(f"HINT_maybe_institutional x{signals['org_markers']}")

    return score, reasons

# Fax-era OCR artifacts: underscores glued to letters, letter-digit fusions,
# symbols embedded mid-word ('servtc_$_vhichare', 'a_ri_ modification').
GARBAGE_RE = re.compile(r"[A-Za-z]_|_[A-Za-z]|[A-Za-z][$#@\\|{}<>][A-Za-z]|[A-Za-z]\d[A-Za-z]")


def garbage_token_ratio(text: str) -> float:
    """Fraction of tokens containing mid-word OCR garbage.

    Clean born-digital and good municipal OCR sit at ~0.00; degraded
    fax-era scans observed at 0.07-0.12. Threshold: 0.03.
    """
    tokens = text.split()
    if len(tokens) < 20:
        return 0.0
    bad = sum(1 for t in tokens if GARBAGE_RE.search(t))
    return bad / len(tokens)


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def pdf_metadata(path: Path) -> dict:
    meta = {}
    for line in run(["pdfinfo", str(path)]).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip()
    return {
        "producer": meta.get("producer", ""),
        "pages": int(meta.get("pages", 0) or 0),
        "title": meta.get("title", ""),
    }


def dup_bigram_ratio(text: str) -> float:
    """Fraction of consecutive word pairs that are identical (case-folded).

    Clean prose sits near 0. The OCR-overlay duplication artifact
    ('proceeds proceeds of each each series') pushes this above ~0.15.
    """
    words = [w.lower() for w in WORD_RE.findall(text)]
    if len(words) < 20:
        return 0.0
    dups = sum(1 for a, b in zip(words, words[1:]) if a == b)
    return dups / (len(words) - 1)


def extract_pages(path: Path) -> list[str]:
    text = run(["pdftotext", "-raw", "-enc", "UTF-8", str(path), "-"])
    return text.split("\f")


def doc_key(po: str, revision: str) -> str:
    """Identity of a document: a purchase order alone is not unique.

    One purchase order carries one document per revision, each with its own
    GUID in the source system (PO 27019 has seven). Keying on the PO alone
    would make six of those seven overwrite each other on the way out.
    """
    return f"{po.strip()}_r{(revision or '').strip() or '0'}"


def load_manifest(path: Path | None) -> dict[str, dict]:
    if not path:
        return {}
    index = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            po = (row.get("po_number") or "").strip()
            if po:
                index[doc_key(po, row.get("revision", ""))] = row
    return index


def match_manifest(pdf: Path, index: dict[str, dict]) -> tuple[str, dict]:
    """Resolve a file to its manifest row. Exact stem match wins."""
    stem = pdf.stem
    if stem in index:
        return stem, index[stem]
    for key, row in index.items():
        if key in stem:
            return key, row
    return stem, {}


def process(pdf: Path, out_dir: Path, index: dict, min_chars: int,
            dup_threshold: float, pii_threshold: int = 3) -> dict:
    meta = pdf_metadata(pdf)
    doc_id, join = match_manifest(pdf, index)
    pages = extract_pages(pdf)

    out_path = out_dir / f"{doc_id}.jsonl"
    kept = dropped = flagged = 0
    pii_excluded: list[dict] = []

    with open(out_path, "w") as f:
        for n, raw in enumerate(pages, start=1):
            text = raw.strip()
            if len(text) < min_chars:
                dropped += 1
                continue

            # PII gate, before the page can reach the corpus. The exclusion is
            # logged with its reasons and its signal counts -- never with the
            # text, which would put the very content back into a committed file.
            signals = pii_signals(text)
            score, reasons = pii_score(signals)
            if score >= pii_threshold:
                pii_excluded.append({
                    "page": n, "score": score,
                    "reasons": reasons, "signals": signals,
                })
                continue

            ratio = dup_bigram_ratio(text)
            g_ratio = garbage_token_ratio(text)
            flags = []
            if ratio > dup_threshold:
                flags.append("dup_overlay_suspect")
            if g_ratio > 0.03:
                flags.append("ocr_degraded")
            if flags:
                flagged += 1
            record = {
                "doc_id": doc_id,
                "source_file": pdf.name,
                "page": n,
                "n_chars": len(text),
                "dup_bigram_ratio": round(ratio, 4),
                "garbage_token_ratio": round(g_ratio, 4),
                "flags": flags,
                "po_number": join.get("po_number", ""),
                "revision": join.get("revision", ""),
                "spec_number": join.get("spec_number", ""),
                "department": join.get("department", ""),
                "vendor_name": join.get("vendor_name", ""),
                "sha256": hashlib.sha256(text.encode()).hexdigest()[:16],
                "text": text,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            kept += 1

    # A document with no text layer -- a scan that was never OCR'd -- would
    # otherwise leave a zero-byte JSONL behind, which reads as "extraction
    # failed" or "not processed yet" rather than "there was nothing to
    # extract". The report is where that fact belongs.
    if kept == 0:
        out_path.unlink(missing_ok=True)

    return {
        "doc_id": doc_id,
        "file": pdf.name,
        "producer": meta["producer"],
        "pages_total": meta["pages"],
        "pages_kept": kept,
        "pages_dropped": dropped,
        "pages_flagged": flagged,
        "pages_pii_excluded": len(pii_excluded),
        "pii_exclusions": pii_excluded,
        "output": str(out_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--out", type=Path, default=Path("corpus"))
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--min-chars", type=int, default=200)
    parser.add_argument("--dup-threshold", type=float, default=0.15)
    parser.add_argument("--pii-threshold", type=int, default=3,
                        help="drop a page at or above this personal-contact "
                             "score (lower = stricter; default 3)")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    index = load_manifest(args.manifest)
    pdfs = sorted(args.input_dir.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {args.input_dir}", file=sys.stderr)
        return 1

    summary = []
    for pdf in pdfs:
        try:
            report = process(pdf, args.out, index, args.min_chars,
                             args.dup_threshold, args.pii_threshold)
        except subprocess.CalledProcessError as exc:
            report = {"doc_id": pdf.stem, "file": pdf.name,
                      "error": exc.stderr[:200] if exc.stderr else str(exc)}
        summary.append(report)
        print(json.dumps(report, ensure_ascii=False))

    with open(args.out / "_extraction_report.json", "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    counts = Counter("error" in r for r in summary)
    excluded = sum(r.get("pages_pii_excluded", 0) for r in summary)
    print(f"\nDone: {counts[False]} ok, {counts[True]} failed. "
          f"Report: {args.out}/_extraction_report.json")
    print(f"PII filter dropped {excluded} page(s) across "
          f"{sum(1 for r in summary if r.get('pages_pii_excluded'))} document(s).")
    if excluded:
        print("Review the exclusions in the report before committing the corpus.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
