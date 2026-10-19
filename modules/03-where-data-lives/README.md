# Module 3 — Where Data Lives

Six engines, one graph, and the parts of the graph that do not survive the trip
between them.

- Live session: 1.5h · Lab: four exercises
- **This is the one week you load the graph yourself**, six times, one engine at
  a time. The loading is not setup you get through before the content: the time
  each engine takes to swallow the same data is the first measurement of the
  module, and you cannot be told it.
- Prerequisites: module 2, Cypher you can read, and Docker running. Keep module
  2's folder where it is: one section of this week's notebook reads the shapes
  you wrote there, out of that notebook itself, and validates the whole graph
  against them.

## Before the session

This is the heaviest week of the course to set up. Three numbers first, so that
none of them arrives as a surprise on the evening:

| | |
|---|---|
| download | 414 MB, once |
| free disk | about 25 GB: 23 GB for the six stores and 1.6 GB for the unpacked payload |
| wall clock | about 20 minutes to load all six, one after another |

If you have less disk than that, you can still do everything: load one engine,
work with it, tear its store down, load the next. The section on running them one
at a time says how, and which one is expensive to rebuild.

Two folders are involved. This one holds what you open in a notebook: the
lesson, the lab, the definition of the stack, and the data once you have
downloaded it. `tools/03-where-data-lives/` holds what you run once from a
shell — the loaders, one per engine, and the two scripts that reshape the
export for them. **Every command on this page runs from the root of the
repository**, so both paths are written out in full.

### 1. The payload

Two files, `module-03-payload.zip` and `SHA256SUMS.txt`, from the module's folder
on Drive — the same folder that holds the slides and the recording of the
session:

**[Module 03 — Where Data Lives](https://drive.google.com/drive/folders/1Nx9b6NyRoT25gmxT37PP2zh9UITI_7x4)**

Put both in the root of the repository, unpack the archive where the loaders
look, then build the rest:

```bash
# optional, and see below
shasum -a 256 -c SHA256SUMS.txt

unzip module-03-payload.zip -d modules/03-where-data-lives/import/

# the two other shapes, written out of the one you just unpacked
python3 tools/03-where-data-lives/admin_headers.py
python3 tools/03-where-data-lives/falkor_bulk_headers.py
```

The checksum is worth the ten seconds. A download that arrives truncated does
not announce itself: it turns up later as a loader failing on a row, or worse as
an engine holding fewer edges than the others and still answering every
question.

Those last two lines are the part worth understanding before you run it. The
graph is loaded into six engines from **four different shapes of the same
rows**, because each engine's own bulk loader insists on its own: one CSV layout,
which Kuzu reads, a second for Neo4j's importer, a third for FalkorDB's, and
N-Quads for the three triple stores. The second and third are not separate
downloads — they are generated here out of the first, which is also the cheapest
way to see how little of the difference is data. Neo4j's importer wants a
different header line and nothing else: the rows are copied byte for byte.
FalkorDB's wants the header *and* every list column re-rendered, because its
loader runs `ast.literal_eval` on each cell and cannot read the export's own
list syntax. Five of twenty-eight files change. Run both scripts and then diff
them against `modules/03-where-data-lives/import/csv/` if you want to see it
rather than take it from me.

One thing FalkorDB's shape cannot carry at all is a date: its loader has no date
type, so every date column goes in as a string. The lesson never asks FalkorDB
about a date; if you do, read *If something fails* first.

`import/` is not in this repository and never will be: it is larger than git
should carry, and the loaders rebuild it rather than edit it. Two small JSON
files arrive inside the archive, and they are the module's own distinction
between a measurement and a record. `load-times.json` is a measurement: every
loader overwrites its own entry as it finishes, so it reaches you with the
numbers from the machine this module was built on and holds yours afterwards.
`batching.json` is a record — the cost of writing one row at a time against a
batch, on each engine — and it cannot be retaken from here, so the lesson reads
it as given and says so.

### 2. Load the six

```bash
tools/03-where-data-lives/load_all.sh      # all six, in order, one at a time
```

**On Windows, do this module inside WSL 2.** `load_all.sh` is a bash script and
runs `.venv/bin/python`, which a Windows virtual environment does not have.
Clone the repository inside WSL, follow the setup in the root README from there,
and turn on Docker Desktop's WSL integration so the containers are reachable.

It starts and stops the containers itself, one profile at a time, so you do not
bring the stack up first. Every service in `docker-compose.yml` sits behind a
profile, which is why none of them ever starts by accident.

The order is not arbitrary. The two embedded engines go first, because they need
no container and fail immediately if the payload is wrong — a bad download
should cost you seconds, not twenty minutes. Then the two property graphs, each
written by its own importer into a wiped volume. Then the two triple stores,
whose bulk loaders want the server down.

Afterwards, to bring one engine up and put it away again:

```bash
cd modules/03-where-data-lives
docker compose --profile neo4j up -d
docker compose --profile neo4j down -v      # -v also removes its store
```

Those two are the exception to running everything from the root: `docker
compose` reads the file in the folder you are standing in, and the stack is
defined next to this README.

Each loader can also be run on its own, if one of the six fails or you want to
redo it. They are the `load_*.py` files in `tools/03-where-data-lives/`, and
each one carries in its header what it found out about its engine — including
the three things Neo4j's importer refused, and the type FalkorDB's cannot write.
Read them; they are course material, not plumbing.

### 3. One at a time is the method, not a precaution

Four of the six are containers, and each one reserves more memory than Docker's
VM can give to all four together. The stores have the same problem on disk. Two
engines competing for the same RAM, the same cores and the same disk while one
of them is being timed produce numbers about the competition — so the module
never runs two at once, and the measurements in the lesson were taken that way.

If disk is tight, keep one store at a time and `down -v` between engines. One
warning before you do: Fuseki is the only one whose reload costs minutes rather
than seconds. Tear it down last and reluctantly.

### 4. What you see when an engine is down

Nothing breaks. Every cell that reads a live engine reports `n/a` for the ones
that are not there, and the lab's first cell prints a line per engine saying how
many nodes it holds or why it could not be reached. So a session with one engine
up is a shorter table, not an error — which is also how you should work through
the lab if you are short of disk.

## The session

Five sections. The dataset is the same throughout; what changes is which part of
the engine you are looking at.

| | |
|---|---|
| **The trip is not free** | "the same data in two models" is a claim, and we check it. The place where the two families refuse to translate is the place where an edge has to carry something of its own. |
| **The six engines** | What you stood up, and what it cost, measured in front of you rather than quoted. Three property graphs and three triple stores, one of each embedded. |
| **The same question, six times** | Ten questions, six engines, and a winner that changes per row. There is no fastest engine in this table, and that is the result. |
| **Where the computation lives** | What happens when the algorithm you need is not in the database. The round trip out and back has a price, and we pay it live. |
| **Does the engine change the knowledge graph?** | Entity resolution run on each engine, and the answer compared. "Largely the same" is not a verdict, it is a number. |

One cell in the first section is worth arriving for: it is the only place in the
module where an engine answers something **false** with no error, no warning and
no flag on the reply. A set and a list are not the same thing, and one of the six
will not tell you which one it gave you.

## The lab

`lab.ipynb`. Four exercises; the questions and the vocabulary are given, the
queries are yours.

| | | |
|---|---|---|
| 1 | a question of your own, asked of all six | you write the runner, and find out which engine needed something different |
| 2 | one Cypher text, three engines that all speak Cypher | where "speaks Cypher" stops being a portability claim |
| 3 | an algorithm none of the six has | what leaving the database costs, measured |
| 4 | a write loop against a write batch | the round trip, priced |

## What you will be able to say afterwards

- where two data models stop translating into each other, and what that forces
  an edge to carry
- why an engine that answers wrongly without an error is more dangerous than one
  that fails — a set that quietly ate a list, a correct query that answered
  empty because the graph was not named, a centrality that answered zero
- why "which graph database is fastest" has no answer, and what question to ask
  instead
- whether changing engine changes the knowledge graph — with the measurement
  that settles it, rather than an opinion

## If something fails

**`No module named 'falkordb'`, with the package installed.** On Apple Silicon,
check the architecture of the interpreter and not the package. A Python launched
from a shell running under Rosetta installs x86_64 wheels into a virtual
environment that Jupyter then starts as arm64, and the import error that follows
looks exactly like a missing package. Start the kernel arm64 and the wheels
match.

**A SPARQL query that answers zero rows, with no error at all.** The graph is
loaded into a named graph, so a query has to say which graph it reads:
`GRAPH <...> { ... }`. Without it, one of the three stores answers nothing and
reports no problem. The lab's first cell gives you the name.

**A FalkorDB answer that looks right and is not.** It caps result sets by
default and enforces the cap by truncating in silence. `docker-compose.yml`
removes the cap for this stack; if you point your own client at it, that is the
first thing to check.

**A date comparison that answers 0 on FalkorDB alone.** Its bulk loader has no
date type, so on this stack every FalkorDB date is a string, and comparing it with
`date('2020-01-01')` is null rather than false: the query answers 0 rows and
reports nothing. Neo4j and Kuzu answer thousands with the same text. Compare with
a string, `'2020-01-01'`, on FalkorDB — an ISO date sorts correctly as text — and
check `typeOf(n.startDate)` before you trust a date there.

**A healthcheck that says green while every query comes back empty.** Loading
two engines at once can leave a bulk loader half finished behind a container that
reports itself healthy. Load them one at a time, and if one is already in that
state, `down -v` and load it again.
