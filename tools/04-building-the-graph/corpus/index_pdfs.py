#!/usr/bin/env python3
"""Index the downloaded PDFs by contract, so the files become expendable.

Instructor-only. Writes one JSON per PDF directory:

    python tools/04-building-the-graph/corpus/index_pdfs.py data/chicago/2022-2026/pdfs \
        --manifest data/chicago/2022-2026/manifest.csv

The filename carries the identity -- <po_number>_r<revision>.pdf -- and that is
enough while the files are on disk. It stops being enough the moment a PDF is
deleted after extraction, which is the only way the full corpus fits: 128 GB of
PDFs against 137 GB free, and 25x less once reduced to text. This index is what
survives the deletion, so the text in the graph can still be traced back to the
file it came from and the URL it was fetched from.

A purchase order is not one document: 12,921 documents in the 2022-2026 window
belong to 8,283 orders, so a contract maps to a list of revisions, never to one
file.

Duplicates are reported, not removed. Measured 14/10/2026 over the 3,054 files
downloaded in August: 3,053 distinct contents, one duplicated pair, 0.3 MB
recoverable -- 0.0% of 13.5 GB. Deduplication is machinery for a saving that
does not exist here, so the detection stays and the deletion does not.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# The naming scheme download_pdfs.py writes. A purchase order number is not
# always numeric -- T25581, C029840 -- so the stem is split on the last _r.
STEM = re.compile(r"^(?P<po>.+)_r(?P<revision>\d+)$")


def hash_file(path: Path, chunk: int = 1 << 20) -> str:
    """sha256, read in chunks: a single 1,635-page PDF is 300 MB."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def manifest_urls(manifest: Path) -> dict[tuple[str, str], str]:
    if not manifest or not manifest.exists():
        return {}
    with manifest.open(encoding="utf-8") as f:
        return {(r["po_number"], r["revision"]): r["pdf_url"]
                for r in csv.DictReader(f)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdf_dir", type=Path)
    ap.add_argument("--manifest", type=Path, default=None,
                    help="to record the URL each file was fetched from")
    ap.add_argument("--out", type=Path, default=None,
                    help="default: <pdf_dir>/../pdf_index.json")
    args = ap.parse_args()

    # Resolved so the paths recorded in the JSON are repo-relative whichever
    # directory the script is called from.
    args.pdf_dir = args.pdf_dir.resolve()
    if args.manifest:
        args.manifest = args.manifest.resolve()

    if not args.pdf_dir.is_dir():
        print(f"not a directory: {args.pdf_dir}", file=sys.stderr)
        return 1

    urls = manifest_urls(args.manifest)
    contracts: dict[str, list[dict]] = defaultdict(list)
    by_hash: dict[str, list[str]] = defaultdict(list)
    unparsable, total_bytes = [], 0

    for path in sorted(args.pdf_dir.glob("*.pdf")):
        m = STEM.match(path.stem)
        if not m:
            unparsable.append(path.name)  # declared, not skipped in silence
            continue
        po, revision = m["po"], m["revision"]
        digest = hash_file(path)
        size = path.stat().st_size
        total_bytes += size
        by_hash[digest].append(path.name)
        contracts[po].append({
            "revision": int(revision),
            "file": path.name,
            "sha256": digest,
            "bytes": size,
            "url": urls.get((po, revision)),
        })

    for revisions in contracts.values():
        revisions.sort(key=lambda r: r["revision"])

    duplicates = {d: sorted(n) for d, n in by_hash.items() if len(n) > 1}
    out = args.out or args.pdf_dir.parent / "pdf_index.json"
    out.write_text(json.dumps({
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pdf_dir": str(args.pdf_dir.relative_to(ROOT)),
        "manifest": str(args.manifest.relative_to(ROOT)) if args.manifest else None,
        "files": sum(len(v) for v in contracts.values()),
        "contracts": len(contracts),
        "bytes": total_bytes,
        "distinct_contents": len(by_hash),
        "duplicates": duplicates,
        "unparsable": unparsable,
        "by_contract": dict(sorted(contracts.items())),
    }, indent=2))

    print(f"{sum(len(v) for v in contracts.values()):,} file, "
          f"{len(contracts):,} contratti, {total_bytes / 2**30:.2f} GB")
    print(f"contenuti distinti: {len(by_hash):,} | "
          f"gruppi duplicati: {len(duplicates):,} | "
          f"file in eccesso: {sum(len(v) - 1 for v in duplicates.values())}")
    if unparsable:
        print(f"nomi non interpretabili: {len(unparsable)} -> {unparsable[:3]}")
    print(f"scritto {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
