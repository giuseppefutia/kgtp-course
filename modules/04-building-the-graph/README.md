# Module 4 — Building the Graph

Finding what is wrong with a graph nobody told you is wrong.

- Live session: 1.5h
- You are given the graph, already loaded. You do not build it.
- Prerequisites: Cypher you can read and write; module 3.

## The problem

Four public datasets about the City of Chicago went in, and so did the scanned
contracts behind them. One graph came out. Nothing in the sources said that a
row in the contracts file and a row in the business licence file are the same
company — somebody decided, and that decision is now a fact the rest of the
course reasons over.

Some of those decisions are wrong. Your job this week is not to fix them. It is
to **find them, and say how you know**.

That distinction is the module. A graph you cannot audit is not a knowledge
base, it is a rumour with an index.

## What you are given

Measured on the published graph, 23/10/2026:

| | |
|---|---:|
| nodes | 3,026,400 |
| relationships | 5,800,402 |
| contracts | 88,916 |
| organisations | 212,009 |
| people | 215,393 |
| licence records | 1,203,437 |
| documents, with pages | 14,499 / 279,017 |

Plus an entity layer — `OrganizationGroup` and `Person` — asserting which rows
describe the same business and the same human being. That layer is where the
errors live, and it is the only part of the graph nobody wrote down: it was
computed.

## Before the session

**This module runs on Neo4j Desktop, and the graph arrives as a dump.** One
download, one load, no Docker.

| | |
|---|---|
| download | 1.4 GB, once |
| free disk | about 6 GB: 1.4 GB for the dump, 4.3 GB for the store and transaction logs it becomes |
| wall clock | seconds. Measured 23/10/2026: 4.33 GiB restored in 6.5 s |

### 1. The database

Install **[Neo4j Desktop](https://neo4j.com/download/)** and create a DBMS of
version **2025.11.2**. The version is not a preference. The dump is written in
the `block` store format, which is readable by Neo4j Enterprise and not by
Community, and Desktop is what gives you Enterprise under a development
licence. A Community server of the same version will refuse this file.

Set the password to `password`, or export `NEO4J_PASSWORD` before starting
Jupyter. The notebooks read `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` and
`NEO4J_DATABASE` from the environment and fall back to
`bolt://localhost:7687`, `neo4j`, `password` and `kgtp`.

Then install two plugins from the DBMS's plugin pane:

| | | |
|---|---|---|
| **APOC** | required | the lesson calls `apoc.text.sorensenDiceSimilarity` and four more. Without it, the sections on similarity do not run |
| **GDS** | only to rebuild | Louvain and WCC are how the entity layer was computed. Nothing in the lesson calls them |

Desktop installs the build that matches your server; the graph was built with
APOC 2025.11 and GDS 2.24.0.

### 2. The dump

Two files, `kgtp.dump` and `SHA256SUMS.txt`, from the module's folder on Drive —
the same folder that holds the slides and the recording of the session:

**[Module 04 — Building the Graph](https://drive.google.com/drive/folders/1RUiyHFqm6NV72aBGkYIzeFj1aC76YRgE)**

The checksum is worth the ten seconds. A 1.4 GB download that arrives truncated
does not announce itself: it turns up as a load that fails halfway, or as a
graph holding fewer rows than everyone else's and still answering every
question.

```bash
shasum -a 256 -c --ignore-missing SHA256SUMS.txt
```

`--ignore-missing` because that file also lists `module-04-inputs.zip`, which
belongs to the rebuild path below and which you have no reason to have
downloaded. Without the flag it reports a failure for the file you correctly do
not have. You want one line, `kgtp.dump: OK`.

From the DBMS's own folder — Desktop will open it for you, and on macOS it is
under `~/Library/Application Support/neo4j-desktop/Application/Data/dbmss/`:

```bash
bin/neo4j-admin database load kgtp --from-path=/path/to/the/download
```

The DBMS can stay running while you do this, because `kgtp` does not exist in
it yet. Then register the database, once, from the Neo4j Browser against the
`system` database:

```cypher
CREATE DATABASE kgtp
```

**The file name is the database name.** `kgtp.dump` loads as `kgtp`, which is
what the notebooks ask for. Renaming the file renames the database, and then
every notebook needs `NEO4J_DATABASE` set to match.

If `neo4j-admin` or `cypher-shell` answers *Unsupported Java 17 detected*, it
found the system Java rather than the one Desktop ships. Point `JAVA_HOME` at
Desktop's own runtime — on macOS, inside
`~/Library/Application Support/neo4j-desktop/Application/Cache/runtime/`, at the
`Contents/Home` under it — and run the command again.

### 3. Check it before the session, not during

```python
import os
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))
with driver.session(database="kgtp") as s:
    print(s.run("MATCH (n) RETURN count(n) AS nodes").single()["nodes"])
```

It must say **3,026,400**. The notebooks name the database explicitly rather
than taking the server default, for the reason that cell's comment gives: a
default database that holds some other graph does not raise, it answers — with
numbers from whatever is in there.

## Rebuilding it from nothing

Optional, and it is not the way into the session. The whole pipeline is
published in [`tools/04-building-the-graph`](../../tools/04-building-the-graph),
which holds the eight phases that build the graph from the four CSVs, the five
that load the documents, and a README saying what each one reads and writes and
why it sits where it does.

Two things to know before you start, both of them in that README in full:

- a rebuild gives you **the same graph, not the same rows**. Record identity is
  positional and the cluster identifiers are recomputed, so the cells that name
  one person or one group come back with different ones. That is not a fault in
  the pipeline, it is the subject of the module;
- one phase cannot be reproduced from the payload at all: `embed` needs the
  served embedding endpoint. Module 4 never queries a vector index, so nothing
  here needs it — module 5 will.

## Live session (1.5h)

Four sections. Each one takes a decision the pipeline made, and asks what it
bought and what it cost.

### 0. The four files, and where they touch

Three node types come from two files each: `Organization`, `PersonRecord`,
`Department`. Those three junctions are the whole reason the graph exists, and
nothing in any file declares them.

The employee file writes a name as `LAST, GIVEN MIDDLE`; the owner file has
three columns. Both must produce the same string or nothing joins.

### 1. Sixty-five billion pairs, and the two steps that cut them to four

Two files describe people and share no identifier, so the only field left to
match on is the name — and comparing every pair of 361,694 records means
65,411,093,971 of them. That is the constraint the whole pipeline answers to.

The session separates the two jobs one query does — a fuzzy index decides which
records get compared, a similarity score decides which pairs pass — and then
spends its time on one name, where four candidates come back and the score lets
two different men through as one.

There is no ground truth for these names, so the threshold cannot be optimised,
only defended: **it can be shown wrong, never shown right.**

### 2. From edges to entities

Similarity edges are a graph, not an answer. Connected components weld 37,824
records into one blob by transitive closure; Louvain's finest level is kept
instead.

That choice cuts both ways, and the session shows both: it separates two men a
permissive edge had joined, and it splits one woman whose records were joined at
a perfect 1.000, because a doubtful neighbour deformed the neighbourhood.

### 3. Organisations: more signals, and a different way to be wrong

Four rules, each pairing a second signal with a requirement on the name —
address, address minus the unit, postcode, shared owners. The weaker the second
signal, the stronger the name must be.

One group is taken apart edge by edge: a correct core of one construction firm,
plus two joint ventures attached by the address alone, holding money that is not
the parent's.

The same rules fail in the opposite direction too — a real relation that no rule
can reach — and that one the session names without showing: it is the one to go
looking for afterwards.

There is a fifth class of error — the world knows something the data cannot say
— and it is module 6's, because it needs a source outside the graph.

## What you will be able to say afterwards

- why a threshold can be shown wrong but never shown right
- why the granularity of a clustering is a decision with a price on both sides
- why merging on one signal is always wrong, and what to do instead
- why an entity layer goes wrong in two opposite directions at once, and why
  tightening a rule fixes neither

## What this module does not do

It does not fix anything. Every anomaly you find is still in the graph at the
end of the week, on purpose: modules 5 and 6 are built on the difference between
what the graph says and what is true.

## If something fails

**A query that answers with numbers nobody else has.** You are on the wrong
database. The server default is not `kgtp`, and asking the wrong database does
not raise. Run the check in step 3; if it does not say 3,026,400, fix the
connection before anything else.

**`Unknown function 'apoc.text.sorensenDiceSimilarity'`.** APOC is not
installed in this DBMS. The plugin is per DBMS, not per installation of
Desktop, so a plugin you installed for another one is not here.

**`neo4j-admin database load` says the store format is not supported.** The
server is Community, not Enterprise. The dump is in `block` format; see step 1.

**`CREATE DATABASE kgtp` says it already exists, and it is empty.** Loading a
dump over a registered database needs `--overwrite-destination=true` on the
`load` command. Stop the DBMS, re-run the load with that flag, start it again.

**A cell that calls a model and answers anyway.** The endpoint the session uses
is off most of the time on purpose, and that cell prints the recorded answer
instead. It says which of the two you are looking at.
