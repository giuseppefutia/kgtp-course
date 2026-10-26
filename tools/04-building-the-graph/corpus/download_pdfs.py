#!/usr/bin/env python3
"""Download the contract PDFs listed in the corpus manifest.

Instructor-only. Output goes to data/chicago/raw/pdfs/, which is gitignored:
these are the unfiltered originals, and only the PII-filtered text extracted
from them is ever committed.

Run from the repo root:
    python tools/04-building-the-graph/download_pdfs.py                       # the whole manifest
    python tools/04-building-the-graph/download_pdfs.py --limit 3             # try a few first
    python tools/04-building-the-graph/download_pdfs.py --self-test URL       # check the plumbing

Files are named <po_number>_r<revision>.pdf. A purchase order is not a unique
document: each revision has its own file and its own GUID in the source system
(PO 27019 carries seven), and extract_contracts.py keys on the same identity.

Re-running skips whatever is already on disk, so an interrupted run resumes.

=============================================================================
HOW THE VIEWER WORKS — worked out 2026-08-07, do not simplify away
=============================================================================
The manifest's `contract_pdf` column points at a ZK (Java) viewer page, not at
a file. Fetching it takes two hops and a browser-shaped request.

1. GET the viewer URL. WITH BROWSER HEADERS: a bare requests User-Agent gets
   500 Internal Server Error, which reads like a broken endpoint but is the
   server declining to serve a non-browser. With the full header set below it
   returns 200 and a small ZK bootstrap page.

2. That page carries an <iframe> whose src is the actual document, same
   endpoint but different parameters:

       .../DPSWebDocumentViewer?id={GUID}&osName=eContentContracts&el=0&image=image

   GET that in the same session and it answers application/pdf.

Both `sid` forms in the manifest work (112 rows ESMART, 8 EDGE). For EDGE the
short id is resolved server-side into a document GUID, so the iframe src cannot
be predicted from the manifest and must be read from the bootstrap page — which
is why this is two requests and not one.
=============================================================================
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import time
from pathlib import Path

import requests

from corpus.extract_contracts import doc_key

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = ROOT / "data" / "chicago" / "corpus_manifest.csv"
# Spelled out rather than imported from download.py: that module is the
# portal downloader and the two have no reason to share a constant, which
# is what made this file fail to import when only one was carried over.
DEFAULT_PDF_DIR = ROOT / "data" / "chicago" / "raw" / "pdfs"
PDF_MAGIC = b"%PDF"
IFRAME_SRC = re.compile(r"<iframe[^>]+src=\"([^\"]+)\"", re.IGNORECASE)

# The viewer answers 500 to anything that does not look like a browser. This is
# the minimum set that gets a 200 -- trimming it is how the endpoint starts
# looking broken again.
BROWSER_HEADERS = {
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/151.0.0.0 Safari/537.36",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
              "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "en-US,en;q=0.9",
    "sec-ch-ua": '"Not=A?Brand";v="99", "Google Chrome";v="151", "Chromium";v="151"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "cross-site",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "referer": "https://data.cityofchicago.org/",
}


class NotAPdf(Exception):
    """The endpoint answered, but not with a PDF."""


def fetch_pdf(session: requests.Session, viewer_url: str) -> bytes:
    """Return the PDF bytes for one viewer URL. Two hops, see module docstring."""
    page = session.get(viewer_url, timeout=120, allow_redirects=True)
    page.raise_for_status()

    if page.content.startswith(PDF_MAGIC):
        return page.content  # some documents may answer directly

    match = IFRAME_SRC.search(page.text)
    if not match:
        raise NotAPdf(
            f"no iframe in the viewer page ({page.status_code}, "
            f"{len(page.content)} bytes, {page.headers.get('Content-Type', '?')})"
        )

    doc = session.get(
        html.unescape(match.group(1)),
        timeout=300,
        headers={"referer": page.url, "sec-fetch-dest": "iframe",
                 "sec-fetch-site": "same-origin"},
    )
    doc.raise_for_status()
    if not doc.content.startswith(PDF_MAGIC):
        raise NotAPdf(f"iframe served {doc.headers.get('Content-Type', '?')}, "
                      f"{len(doc.content)} bytes")
    return doc.content


def load_manifest(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for col in ("po_number", "revision", "pdf_url"):
        if rows and col not in rows[0]:
            raise SystemExit(f"{path}: missing column '{col}'")
    return [r for r in rows if (r.get("pdf_url") or "").strip()]


def download_one(session: requests.Session, row: dict, dest_dir: Path) -> dict:
    key = doc_key(row["po_number"], row.get("revision", ""))
    dest = dest_dir / f"{key}.pdf"
    if dest.exists() and dest.stat().st_size > 0:
        return {"doc": key, "status": "cached", "bytes": dest.stat().st_size}

    try:
        data = fetch_pdf(session, row["pdf_url"].strip())
    except NotAPdf as exc:
        return {"doc": key, "status": "not_a_pdf", "detail": str(exc)}
    except requests.RequestException as exc:
        return {"doc": key, "status": "http_error", "detail": str(exc)[:200]}

    tmp = dest.with_suffix(".pdf.part")
    tmp.write_bytes(data)
    tmp.replace(dest)  # only appears under its real name once complete
    return {"doc": key, "status": "ok", "bytes": len(data)}


def self_test(url: str) -> int:
    """Exercise the plumbing against a URL known to serve a PDF."""
    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)
    try:
        data = fetch_pdf(session, url)
    except (NotAPdf, requests.RequestException) as exc:
        print(f"FAIL {type(exc).__name__}: {exc}")
        return 1
    print(f"OK   {len(data):,} bytes, starts with {data[:8]!r}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--limit", type=int, help="stop after N documents")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="seconds between requests (default 1.0)")
    parser.add_argument("--self-test", metavar="URL",
                        help="fetch one known-good PDF URL and exit")
    args = parser.parse_args()

    if args.self_test:
        return self_test(args.self_test)

    if not args.manifest.exists():
        raise SystemExit(
            f"no manifest at {args.manifest}. Run build_manifest.py first."
        )
    rows = load_manifest(args.manifest)
    if args.limit:
        rows = rows[: args.limit]
    args.out.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)

    results = []
    for i, row in enumerate(rows, start=1):
        res = download_one(session, row, args.out)
        results.append(res)
        detail = res.get("detail", "")
        # flush: a long run is usually watched through a redirected log, and
        # block buffering would leave that log empty until the very end.
        print(f"  [{i:>3}/{len(rows)}] {res['status']:<10} {res['doc']}"
              f"{'  ' + detail[:80] if detail else ''}", flush=True)
        if res["status"] not in ("cached",):
            time.sleep(args.delay)  # the source is a public sector system

    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("\n" + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    log = args.out / "_download_report.json"
    log.write_text(json.dumps(results, indent=2))
    print(f"report: {log.relative_to(ROOT)}")

    if counts.get("ok", 0) == 0 and counts.get("cached", 0) == 0:
        print("\nNothing downloaded. Every row failed the same way "
              f"({', '.join(sorted(counts))}), which is what an unresolved "
              "viewer endpoint looks like: fetch_pdf still needs the manual "
              "Network-tab step. See the docstring at the top of this file.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
