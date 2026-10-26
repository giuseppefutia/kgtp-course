"""Build the graph and load the document corpus, in the order they depend on.

Before this file the order lived in one sentence inside licenses.py and nowhere
else, so rebuilding meant asking whoever had done it last.

    python build.py graph                  rebuild the graph from empty
    python build.py corpus                 load the documents and what was read
    python build.py corpus --without-embed the same, without the vectors
    python build.py all
    python build.py graph --dry-run        print the commands, run nothing
    python build.py graph --from licenses
    python build.py --only dept-cluster

Every phase is a subprocess, so a failure stops the chain with the exit code and
the output of the step that failed. Timings are printed per phase: a number
nobody measures is not a budget.

Rebuilds are always from empty. Record identity is positional, so loading twice
into the same database does not give the same graph as loading once; starting
from nothing is what makes that irrelevant.

WHAT THIS FILE DOES NOT DO
--------------------------
It does not fetch the PDFs and it does not extract text from them. That half of
the corpus pipeline is 43 GB over a server nobody here controls, plus a model
served by hand, and it ran once: what is published is its output -- the
extracted text, the parsed forms, the typed fields -- and the `corpus` phases
below read that. The README names the scripts and the order, for the record.

One phase cannot be reproduced from the payload at all: `embed` needs the served
embedding endpoint. Without it the graph is complete except for `Page.embedding`
and the vector index, which is everything module 4 asks of it and not everything
module 5 will. The dump is the only path that arrives with the vectors.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

# The endpoint and its TLS context come from the importer that uses them, so the
# preflight probes the same address the phase will call.
from factory.embeddings import DEFAULT_URL as EMBED_URL, ssl_context

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DATA = ROOT / "data" / "chicago"
RAW = DATA / "raw"

# Two extracted corpora, loaded one after the other. The second is named after
# the window of contracts it covers; the first predates that naming and sits
# directly under data/chicago/ with its manifest beside it.
#
# They overlap, and `documents` MERGEs on document id, so loading both is not
# loading twice. Verified 23/10/2026: `2022-2026` alone gives 12,921 Document
# and 230,328 Page; the earlier corpus loaded after it reaches 14,499 and
# 279,017, which is what the graph holds and what the lesson quotes. Shipping
# only the newer one, which is the obvious thing to do, quietly costs 1,578
# documents and 48,689 pages.
EARLIER = DATA
CORPUS = DATA / "2022-2026"

# The CSVs carry the date they were downloaded, and the filename is the only
# record of which snapshot of the portal this graph was built from. The portal
# updates continuously, so a fresh download is a different dataset with a
# different name -- which is why these are pinned here and shipped in the
# payload rather than fetched at build time.
SOURCES = {
    "contracts": "rsxa-ify5_2026-08-11.csv",
    "owners": "ezma-pppn_2026-08-11.csv",
    "employees": "xzkq-xp2w_2026-08-11.csv",
    "licenses": "r5kz-chrr_2026-08-12.csv",
}


@dataclass
class Phase:
    name: str
    argv: list[str]
    why: str = ""
    needs_files: list[Path] = field(default_factory=list)
    needs_tools: list[str] = field(default_factory=list)
    needs_urls: list[str] = field(default_factory=list)


def importer(module: str, csv_name: str | None = None, base: Path = RAW,
             *extra: str) -> list[str]:
    argv = [sys.executable, "-m", f"factory.{module}", "--backend", "neo4j"]
    if csv_name:
        argv += ["--file", csv_name, "--base_path", str(base)]
    return argv + list(extra)


def graph_phases() -> list[Phase]:
    """The build order, with the dependency that forces each position.

    employees runs before contracts on purpose: both MERGE Department nodes and
    whichever runs first sets `source`, so swapping them relabels 39 departments
    without changing anything else. Nothing reads that property today, which is
    exactly why the order has to be written down rather than remembered.
    """
    return [
        Phase("reset", [sys.executable, "reset_graph.py", "--yes"],
              "every rebuild starts from nothing"),
        Phase("employees", importer("employees", SOURCES["employees"]),
              "creates PersonRecord and the payroll spelling of each Department",
              [RAW / SOURCES["employees"]]),
        Phase("contracts", importer("contracts", SOURCES["contracts"]),
              "creates Contract, ContractRecord, Organization, Address",
              [RAW / SOURCES["contracts"]]),
        Phase("owners", importer("owners", SOURCES["owners"]),
              "creates the PersonRecord rows for business owners",
              [RAW / SOURCES["owners"]]),
        Phase("people-cluster", importer("people_cluster"),
              "reads the PersonRecord nodes owners and employees created"),
        Phase("licenses", importer("licenses", SOURCES["licenses"]),
              "draws WORKS_FOR_ORG from the Person entities people-cluster built",
              [RAW / SOURCES["licenses"]]),
        Phase("orgs-cluster", importer("orgs_cluster"),
              "reads the Organization nodes contracts and licenses created"),
        Phase("dept-cluster", importer("dept_cluster"),
              "reads the Department nodes contracts and employees created"),
    ]


def corpus_phases() -> list[Phase]:
    """The load half of the corpus pipeline: text already extracted, now graph.

    Every phase here reads a file that was produced once and published. The
    order is the dependency order: `documents` puts the pages in the graph, and
    the three phases after it attach to pages that have to be there already.
    """
    return [
        Phase("documents", importer("documents", "manifest.csv", CORPUS),
              "loads the extracted text as Document and Page",
              [CORPUS / "manifest.csv", CORPUS / "corpus"]),
        Phase("documents-earlier", importer("documents", "corpus_manifest.csv", EARLIER),
              "the same importer over the earlier corpus, which the later one "
              "does not contain. This is the order that was verified",
              [EARLIER / "corpus_manifest.csv", EARLIER / "corpus"]),
        Phase("doc-facts", importer("doc_facts", "manifest.csv", CORPUS),
              "loads what was read out of the pages -- people, modifications, "
              "subcontracts, compliance outcomes, and the Claim/Evidence pairs "
              "where a document contradicts the record",
              [CORPUS / "manifest.csv", CORPUS / "forms", CORPUS / "typed"]),
        Phase("descriptions", [sys.executable, "-m", "factory.descriptions"],
              "one ContractDescription per contract, read off the first page of "
              "the documents the router keeps; deterministic, reads the graph"),
        Phase("programs", [sys.executable, "-m", "factory.programs", "--load"],
              "the programme a grant agreement funds, named in prose. The "
              "extraction asked a model and ran once; this reads its output",
              [DATA / "descriptions" / "programs.json"]),
        Phase("embed", importer("embeddings"),
              "vectors for the pages documents loaded; resumable, so a second "
              "run continues rather than repeats. Needs the served endpoint",
              needs_urls=[EMBED_URL]),
    ]


def preflight(phases: list[Phase]) -> list[str]:
    """Check what every phase needs before running any of them.

    Checking up front rather than per phase is the whole point: discovering
    after twenty minutes of loading that a file is missing costs the twenty
    minutes.
    """
    problems = []
    for phase in phases:
        for path in phase.needs_files:
            if not path.exists():
                problems.append(f"{phase.name}: missing {path}")
        for tool in phase.needs_tools:
            if shutil.which(tool) is None:
                problems.append(f"{phase.name}: {tool} is not on PATH "
                                f"(brew install poppler, or apt install poppler-utils)")
        for url in phase.needs_urls:
            if (reason := unreachable(url)) is not None:
                problems.append(f"{phase.name}: {url} {reason}")
    return problems


def unreachable(url: str) -> str | None:
    """Say why a served endpoint cannot be used, or None if a model is served there.

    A transport failure is fatal and the message repeats it verbatim rather than
    summarising -- a tunnel that moved and a laptop with no network fail here
    identically otherwise.

    An HTTP status is not enough on its own. 401 and 403 mean a server is there
    and did not like this key, which is fine: the phase carries its own. But a
    reserved ngrok domain with nothing behind it answers **404**, and an earlier
    version of this probe accepted any status as proof of life -- so a build
    started, ran for an hour and died at the last phase, which is the one thing
    the preflight exists to prevent. Measured 23/10/2026: both course tunnels
    answered 404 with no GPU session running.

    Every OpenAI-compatible server answers /models, so a 404 there means nothing
    is serving, whatever is answering the port.
    """
    request = urllib.request.Request(url.rstrip("/") + "/models",
                                     headers={"Authorization": "Bearer preflight"})
    try:
        urllib.request.urlopen(request, timeout=10, context=ssl_context())
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return None
        return (f"answered {exc.code}: something is listening but no model is "
                f"served there (is the Colab session up?)")
    except Exception as exc:
        return f"is not answering ({exc})"
    return None


def run(phases: list[Phase], dry_run: bool) -> int:
    width = max(len(p.name) for p in phases)
    started = time.time()
    done = []
    for phase in phases:
        printable = " ".join(
            arg.replace(str(ROOT) + "/", "") for arg in phase.argv[1:])
        # Flushed, all three. A build is normally redirected to a log, where
        # block buffering holds every header until the process ends while the
        # importers' own logging goes to stderr unbuffered -- so the log reads
        # as though the phases never started.
        print(f"\n=== {phase.name} " + "=" * (58 - len(phase.name)), flush=True)
        if phase.why:
            print(f"    {phase.why}", flush=True)
        print(f"    python {printable}", flush=True)
        if dry_run:
            continue
        t0 = time.time()
        result = subprocess.run(phase.argv, cwd=HERE)
        elapsed = time.time() - t0
        if result.returncode != 0:
            print(f"\n*** {phase.name} failed with exit code {result.returncode} "
                  f"after {elapsed:.0f}s. The build is INCOMPLETE. ***")
            if done:
                print("    completed before it: " + ", ".join(n for n, _ in done))
            return result.returncode
        done.append((phase.name, elapsed))
        print(f"    {phase.name} done in {elapsed:.0f}s", flush=True)

    if dry_run:
        print("\ndry run, nothing was executed")
        return 0

    total = time.time() - started
    print("\n" + "=" * 62)
    for name, elapsed in done:
        print(f"  {name:<{width}}  {elapsed:6.0f}s")
    print(f"  {'total':<{width}}  {total:6.0f}s")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", nargs="?", default="all",
                    choices=["graph", "corpus", "all"])
    ap.add_argument("--from", dest="start", metavar="PHASE",
                    help="skip everything before this phase")
    ap.add_argument("--only", metavar="PHASE", help="run this phase alone")
    ap.add_argument("--without-embed", action="store_true",
                    help="drop the embed phase: it needs the served endpoint")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    phases = []
    if args.target in ("graph", "all"):
        phases += graph_phases()
    if args.target in ("corpus", "all"):
        phases += corpus_phases()

    # Dropped before the preflight, and announced. The preflight refuses to start
    # a build whose last phase cannot run, which is right when the endpoint is
    # merely down and wrong for everyone who does not have one: without this flag
    # a missing service would block the four phases that need no service at all.
    # Saying what was dropped is the price of dropping it.
    if args.without_embed:
        dropped = [p.name for p in phases if p.name == "embed"]
        phases = [p for p in phases if p.name != "embed"]
        if dropped:
            print("--without-embed: skipping `embed`. The graph will have no "
                  "Page.embedding and no vector index.", flush=True)

    names = [p.name for p in phases]
    if args.only:
        phases = [p for p in phases if p.name == args.only]
        if not phases:
            print(f"unknown phase: {args.only}\navailable: {', '.join(names)}",
                  file=sys.stderr)
            return 2
    elif args.start:
        if args.start not in names:
            print(f"unknown phase: {args.start}\navailable: {', '.join(names)}",
                  file=sys.stderr)
            return 2
        # --from skips the reset, which is the point of asking for it: resuming
        # a build must not empty what the earlier phases already loaded.
        phases = phases[names.index(args.start):]

    problems = preflight(phases)
    if problems:
        print("cannot start:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    return run(phases, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
