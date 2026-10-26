# tools/04-building-the-graph

Everything that turns four public City of Chicago datasets, plus the scanned
contracts behind them, into the graph module 4 reasons over. Run from this
directory: the modules import each other by package name, so
`cd tools/04-building-the-graph` first and the commands below work as written.

**You do not need any of this to do module 4.** The module ships the finished
graph as a dump, and [its README](../../modules/04-building-the-graph) says how
to load it. This folder is for reading, and for rebuilding if you want to see
the decisions happen rather than take them from me.

```text
download.py     fetch the raw CSVs from the data portal
build.py        the orchestrator: phases, their order, and why
reset_graph.py  empty the graph, so a build starts from nothing

factory/        one module per step that writes to the graph
corpus/         the PDF pipeline: choose, fetch, extract, classify, read
checks/         read-only tools you run by hand
database/       driver connection
importer/       batch import machinery the factory modules build on
util/           backend abstraction, CLI entry point, logging
```

## What a rebuild gives you, and what it does not

Three things, before you spend an hour on it.

**The same graph, not the same rows.** Record identity is positional — the
*n*-th row of a CSV becomes `contracts:<n>` — and the entity layer is
recomputed, so cluster identifiers are assigned afresh. Every count below comes
out the same; the particular person the lesson calls by name is a different
node. The module is about auditing an entity layer, so this is the subject
rather than an inconvenience, but it means a rebuilt graph and the dump answer
the lesson's narrative cells differently.

**No vectors.** `embed` is the one phase that needs a service rather than a
file, and the endpoint is the instructor's. `build.py corpus --without-embed`
skips it and says so. Module 4 never queries a vector index; module 5 does.

If you have a GPU to spend, that phase is not closed to you: the notebook that
serves the model is published in [`serving/`](../../serving), and
`KGTP_EMBEDDINGS_BASE_URL` plus `KGTP_EMBEDDINGS_API_KEY` point this half at
whatever you stand up — the preflight included, so it probes the address it
will actually call.

**Two of the dump's derived layers are older than the corpus under them**, and
a rebuild does not reproduce them — it improves on them. Both were computed
when the corpus was smaller and neither was recomputed when it grew. Measured
23/10/2026, dump against a rebuild from this payload:

| | in the dump | rebuilt |
|---|---:|---:|
| `Page` with an `embedding` | 92,439 of 279,017 | needs the endpoint |
| `ContractDescription` | 917 | **2,366** |

Everything the four CSVs and the extraction produce comes out the same, down to
14,499 `Document`, 279,017 `Page`, 1,185 `Claim`/`Evidence` pairs, 13,213
`EXTRACTED_FROM` and 714,058 person similarity edges. It is the two phases that
derive something *from* the loaded corpus that lag.

Neither matters to module 4: nothing in the lesson reads an embedding or a
`ContractDescription`. Both matter to module 5, which retrieves against
exactly those two. `embed` is resumable — it selects pages with text and no
vector, so a second run continues rather than repeats, 185,121 pages with the
endpoint up for all of them.

**The portal is not a source you can pin.** `download.py` names the file it
writes after today's date, and the City of Chicago updates these datasets
continuously. The four filenames in `build.py` are the snapshot this graph was
built from, and they are in the payload for exactly that reason. Downloading
them again gives you a different dataset with a different name, and `build.py`
will tell you so instead of loading it.

## Before the first run

A Neo4j Desktop DBMS at **2025.11.2** with **APOC** and **GDS** installed —
GDS is what `people_cluster`, `orgs_cluster` and `dept_cluster` call, so unlike
the lesson a build genuinely needs it. The graph was built with APOC 2025.11
and GDS 2.24.0.

Create the database first, from the Neo4j Browser against `system`:

```cypher
CREATE DATABASE kgtprebuild
```

**Neo4j database names take no underscore.** `kgtp_m4_test` is rejected by both
`CREATE DATABASE` and `neo4j-admin`, with a message about illegal characters; a
dash is legal but then every statement naming the database needs backticks
around it. Plain lowercase letters and digits cost nothing and avoid both.

Then point the pipeline at it. Everything here reads the connection from the
environment, in this order: explicit argument, environment, `database/lpg/config.ini`.

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=password
export NEO4J_DATABASE=kgtprebuild
```

The notebooks read the same four names, so the same export points them at what
you built. Use a database name of your own rather than `kgtp`: a build begins by
emptying what it finds, and `kgtp` is where the dump went.

### The inputs

`module-04-inputs.zip` from [the module's folder on Drive](https://drive.google.com/drive/folders/1RUiyHFqm6NV72aBGkYIzeFj1aC76YRgE), 420 MB, 1.6 GB
unpacked, 9,347 files. It unpacks at the **root of the repository** and every
path inside it is already where the loaders look:

```bash
unzip module-04-inputs.zip          # from the repository root
```

```text
data/chicago/raw/*.csv                 the four portal datasets, 490 MB
data/chicago/corpus_manifest.csv       the earlier corpus: 3,176 rows
data/chicago/corpus/                   its page text, 1,751 files
data/chicago/2022-2026/manifest.csv    the later corpus: 13,258 rows
data/chicago/2022-2026/corpus/         its page text, 7,576 files
data/chicago/2022-2026/forms/          what the regex parsers read off those pages
data/chicago/2022-2026/typed/          what the model read off the pages routed to it
data/chicago/2022-2026/page_classes.csv   which pages the router kept, and why
data/chicago/descriptions/*.json       what a model produced once, by hand
```

**Two corpora, loaded one after the other.** They overlap and `documents`
MERGEs on document id, so loading both is not loading twice: `2022-2026` alone
gives 12,921 `Document` and 230,328 `Page`, and the earlier one after it reaches
14,499 and 279,017 — the figures the lesson quotes. Only the later corpus has
`forms/` and `typed/` beside it, which is why `doc-facts` reads only that one.

`build.py` names every file it expects and fails before running anything if one
is missing, so a half-unpacked archive shows up immediately rather than halfway
through a load. What is **not** in there is the 43 GB of PDFs those pages were
extracted from; the section on the corpus says what that costs and why.

## What it costs

Measured 23/10/2026, rebuilding into an empty database on an M-series laptop,
with the DBMS also keeping two other databases of this size online — which is
most of why the clustering phases are as slow as they are, since the three were
sharing a 2 GB page cache.

| phase | |
|---|---:|
| `reset` + `employees` + `contracts` + `owners` | 1 min 50 s |
| `people-cluster` | 14 min 44 s |
| `licenses` | 19 min 33 s |
| `orgs-cluster` | **over 72 min, and not finished** |
| `dept-cluster` | 2 s |
| `documents` | 7 min 36 s |
| `documents-earlier` | under 1 min |
| `doc-facts` | 1 min 26 s |
| `descriptions` | 6 s |
| `programs` | 1 s |

So the corpus column is about ten minutes and the graph column is hours, which
is the opposite of what the file sizes suggest. `orgs-cluster` is the one to
plan around: its similarity pass took 13 min 30 s, and the loop that writes
`BELONGS_TO_ORG_GROUP` after it was at batch 87 of 199 after 58 minutes, at 40 s
a batch — so budget around two and a half hours for that phase alone. The run
was stopped there, which is why there is no total on this page: every other row
is measured and that one is not. Start a rebuild when you do not need the
laptop.

## How the phases fit together

```text
data portal
    |  download.py          (ran once; the CSVs are in the payload)
    v
data/chicago/raw/*.csv
    |
    +-- build.py graph
    |     reset
    |     employees --> contracts --> owners --> people-cluster
    |       --> licenses --> orgs-cluster --> dept-cluster
    |
    +-- build.py corpus
          documents --> documents-earlier --> doc-facts
            --> descriptions --> programs --> embed
                        (reads the extracted text, never a PDF)
```

Left to right is execution order and dependency order at once: every step reads
what the steps before it wrote. `build.py all` runs the graph column and then
the corpus one.

## Running a build

```bash
python3 build.py graph                    # rebuild the graph from empty
python3 build.py corpus --without-embed   # load the documents, skip the vectors
python3 build.py all
python3 build.py graph --dry-run          # print the commands, run nothing
python3 build.py --only dept-cluster
python3 build.py graph --from licenses    # this phase and everything after it
```

`build.py` holds the phases and the dependency that forces each position —
employees before contracts because both MERGE `Department` and the first to run
sets `source`; people-cluster before licenses because licences draw
`WORKS_FOR_ORG` from resolved entities. That order lives there and is not
repeated anywhere else, so there is nothing to keep in sync.

`--from` deliberately skips the `reset`, so resuming a build does not empty what
the earlier phases already loaded.

Rebuilds always start from empty, and `reset_graph.py` drops the constraints and
indexes too: leaving them behind makes the next build look like it created
nothing. The two token lookup indexes are the exception and it is explained
where the exception is made.

## factory/ — what each module puts in the graph

Every module exposes a `*_factory(base_importer_cls, backend)` returning an
importer class, and is run the same way:

```bash
python3 -m factory.<module> --backend neo4j [--file <csv> --base_path <dir>]
```

For example, a module that reads a CSV, and one that reads the graph:

```bash
# reads a file: the payroll CSV, from data/chicago/raw/
python3 -m factory.employees --backend neo4j \
    --file xzkq-xp2w_2026-08-11.csv --base_path ../../data/chicago/raw

# reads the graph: no file, it resolves the PersonRecord nodes already loaded
python3 -m factory.people_cluster --backend neo4j
```

**Running them by hand means keeping the order yourself.** `people_cluster` has
nothing to resolve until `employees` and `owners` have run, `licenses` draws its
edges from the entities `people_cluster` built, and `dept_cluster` needs the
`Department` nodes both `employees` and `contracts` create. Prefer letting
`build.py` order them.

`--backend` is required and never defaulted. `--file` and `--base_path` are
passed only by the modules that read a file; the ones that read the graph take
neither.

| module | reads | writes |
|---|---|---|
| `employees` | payroll CSV | `PersonRecord`, `Department`, `WORKS_FOR_DEPARTMENT` |
| `contracts` | contracts CSV | `Contract`, `ContractRecord`, `Organization`, `Address`, `ContractType`, `ProcurementType`, `Specification`, `Department` |
| `owners` | business owners CSV | `PersonRecord` |
| `people_cluster` | the graph | `Person`, `IS_SIMILAR_TO`, `RECORD_RESOLVED_TO` |
| `licenses` | licences CSV | `LicenseRecord`, `LicenseType`, `Organization`, `Address`, `WORKS_FOR_ORG` |
| `orgs_cluster` | the graph | `OrganizationGroup`, `IS_SIMILAR_TO`, `BELONGS_TO_ORG_GROUP` |
| `dept_cluster` | the graph | `DepartmentGroup`, `BELONGS_TO_ORG_GROUP` |
| `documents` | manifest + extracted text | `Document`, `Page`, `HAS_DOCUMENT`, `HAS_PAGE` |
| `doc_facts` | `forms/` + `typed/` | `Claim`, `Evidence`, `Modification`, `ComplianceAudit`, `Certification`, `ReasonCode`, `PersonRecord`, and the edges between them |
| `descriptions` | the graph | `ContractDescription`, `HAS_DESCRIPTION` |
| `programs` | `programs.json` | `Program`, `PART_OF_PROGRAM` |
| `embeddings` | the graph + model endpoint | `Page.embedding`, vector index `page_embedding` |

The rows are in build order, which is also dependency order. The three
`_cluster` steps write no records of their own — they add an entity layer on
top of what the importers created, and that layer is where the resolution
decisions become visible.

`factory/naming.py` is not an importer. It generates the Cypher expression that
turns first, middle and last name into `PersonRecord.fullName`, and every source
creating a `PersonRecord` interpolates that one expression instead of writing
its own — two sources normalising differently never match, and nothing says so.

`factory/batch_owners.py` is not a phase either. It is a rehearsal of
incremental resolution — a batch of new owner rows, the clusters they touch,
rebuilt — and its last step restores the graph to what it found, which is what
makes it safe to run twice.

## corpus/ — the document pipeline

Half of this ran once and its output is what you unpacked. The other half is
`build.py corpus`, above. The split is not tidiness: the first half is 43 GB
fetched from a server nobody here controls, 51 minutes of `pdftotext`, a human
reading withheld pages, and a model served by hand — none of which should be on
twenty laptops, and one of which gives different answers each time it runs.

The chain, as it ran, with what each step measured. Paths are relative to
`data/chicago/2022-2026/`.

| | script | from | to | measured |
|---|---|---|---|---|
| 0 | `build_manifest.py`, `download_pdfs.py` | the contracts CSV | `pdfs/` | 12,896 PDFs, 42.86 GB. Re-running skips what is on disk, so the same command retries failures |
| 1 | `extract_contracts.py` | `pdfs/` | `corpus/*.jsonl` | 444,980 pages → 229,518 extracted (51.6%); 7,575 files, 868 MB; 51 minutes, zero errors |
| 2 | `classify_pages.py` | `corpus/` | `page_classes.csv` | 124,416 distinct pages of 229,518; 411 distinct pages are 45.5% of all the text |
| 3 | `review_pii_gate.py` | the report + the PDFs | `pii_gate/` | 810 pages withheld, 139 flagged to re-read, 36 s |
| 4 | `parse_forms.py` | `corpus/` | `forms/*.jsonl` | **30,927 rows**, 9.6 seconds, no GPU |
| 5 | `extract_typed.py` | `corpus/` | `typed/*.jsonl` | 5,664 pages sent to the model, **880 filled forms** |
| 6 | consolidation | `typed/schedule_{c,d}.jsonl` | `typed/subcontract_edges.json` | 119 raw edges → **98** |

Between step 1 and the load there is a **human gate**: the withheld pages are
read before the extracted text is published. It is not automated on purpose.

Steps 4 and 5 are two readers of the same pages, and which one reads which page
was decided by measuring rather than by preference. `sample_pages.py`,
`extract_open.py` and `compare_labels.py` are that measurement — 300 sampled
pages, labelled by hand and by a model, compared: the regex reader reached 25%
of what was there, the model 55%. They are published because the rule they
produced is only defensible with them.

```bash
python3 -m corpus.test_pii_filter                        # calibration, no PDFs needed
python3 corpus/extract_typed.py --list                   # the seven page types
python3 corpus/extract_typed.py schedule_c --show-prompt  # what was actually asked
```

**A known defect, left in.** `extract_contracts.py` splits on `\f`, which
yields one empty page per document, so its own report declares 227,548 pages
discarded instead of 214,652. The extracted text is unaffected; the number in
the report is wrong by the document count.

## If a rebuild fails

**`ImportError: ... incompatible architecture (have 'arm64', need 'x86_64')`,
with the package installed.** On Apple Silicon, check the architecture of the
interpreter and not the package. `arch` printing `i386` means the shell is
running under Rosetta, and a universal Python launched from it runs as x86_64
against the arm64 wheels pip put there natively — or the reverse, if pip was the
one under Rosetta. The import error that follows looks exactly like a broken
install. `arch -arm64` on both the install and the run, and the wheels match.
Module 3's README hits the same trap from the other end.

**`*** 23 batch(es) FAILED out of ~211. The load is INCOMPLETE. ***`** This is
the importer telling you the truth, and it does not stop the build. One failing
batch of 1,000 rows used to abandon every batch after it — the comment above the
loop in `importer/lpg/graph_importer.py` carries the date that was measured —
so now a batch that throws is counted and skipped and the pass goes on.

The cause, when it is Lucene's `ParseException`, is a company name. The
candidate query strips punctuation from the name and joins the surviving words
with ` AND `, and one name in the licences file survives that as a boolean
operator: **`A.N.D. RELIABLE AUTO REPAIR INC`** becomes the term `AND`, and the
query parser refuses `AND~0.3 AND RELIABLE~0.3 …` at column 0. Reproduce it in
the Browser:

```cypher
CALL db.index.fulltext.queryNodes('organization_name', 'AND~0.3 AND RELIABLE~0.3')
```

That is one organisation in 212,009, and it carries no `IS_SIMILAR_TO` edge in
the published graph. Whether the other 22 failed batches had the same cause the
report does not say: it keeps five failures and all five were this one. What is
measured is narrower and worth knowing anyway — a rebuild and the dump agree on
every `IS_SIMILAR_TO` count, method by method, down to 714,058 person edges and
9,725 `SAME_ZIP` ones. Identical input in identical order gives identical
batches, so whatever those batches lost, both graphs lost equally.

It is left in rather than patched. The module is about finding what is missing
from an entity layer, and the dump is what the lesson's numbers were taken
from, so a fix here would make the published figures unreproducible by the
published code. What was fixed is the diagnosis: the report used to cut the
message one token before Lucene says which term it choked on.

**The build stops at a phase with no output of its own.** Every phase is a
subprocess and its output goes straight through, so a phase that fails silently
failed before it could log. Run that one command on its own — `build.py` prints
each one above the phase it belongs to — and the traceback is there.

**`employees` or `contracts` loads and `people-cluster` finds nothing.** The
cluster phases call GDS. A DBMS without the plugin answers *Unknown procedure
gds.graph.project*, which is the one import error that is not an import error.

## checks/ — run by hand, write nothing

```bash
# what is in the graph, by label
python3 -m checks.graph_report

# one business name across contracts and licences
python3 -m checks.whois "PRAXAIR"

# the pages of a purchase order
python3 -m checks.read_pages --contract 93627 --cover

# what the PII filter held back, and why
python3 -m checks.review_withheld --po 135798 --text

# which facts the extracted pages actually carry, field by field
python3 -m checks.corpus_fields
python3 -m checks.corpus_fields --stratum random
```

None of these writes to the graph. `corpus_fields` is the odd one out twice
over: it reads the extracted JSONL rather than the graph, so it answers before a
load as well as after one — and it reads only `data/chicago/corpus/`, the
earlier corpus. Its header says **92,439 pages**, which is that corpus and not
the 279,017 in the graph. Do not read that number as the size of the corpus; it
is the size of the half this check looks at.

## Conventions worth knowing before reading a module

- **Identifiers carry their namespace.** `licenses:1234` and `contracts:1234`
  are different firms; three account numbers collide with vendor numbers, so the
  prefix is part of the identifier rather than decoration.
- **Absent values do not become nodes.** A missing department is no edge, not an
  edge to a node named `UNKNOWN`.
- **Everything `doc_facts` writes says where it came from**, in three ways that
  answer three different questions: `source` names the extraction, `doc` and
  `page` name the exact line, `date` says when the document was filed. Nothing
  there came from a published CSV, which is why.
- **A comment that belongs to a Cypher query goes inside the query**, with `//`,
  rather than above it in Python — so the explanation survives being pasted into
  the Neo4j Browser, which is where these are actually read and tried.
- **`TODO` is the only marker**, and a bracketed number — `TODO(A10)` — points
  at an open question recorded under that number rather than a vague intention
  to improve something.
