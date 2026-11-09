# Module 5 — GraphRAG

Four ways to answer a question about the graph, and the question of which one
to reach for.

- Live session: 1.5h
- Prerequisites: the graph of module 4; Cypher you can read.

## The problem

You have the graph. Somebody now asks it a question in English.

There are four shapes of answer, and the course has built up to all of them:
read the pages and answer from them; read the pages and add what the graph knows
about the contracts behind them; let the model write the Cypher; or give the
model a set of tools and let it decide its own next step.

Three of the four decide their route before the question arrives. One decides
while it runs. **None of them is the best one**, and the module ends on a
measurement of which works when — the question of *Is GraphRAG Needed?*
(AWS/Cisco, GEM 2026), asked of these four on these contracts.

## What you will see fail

Each of the four also appears a second time, failing — same pipeline, same shape
of call, a different question. The failures are the point: none of them raises
an error.

- a question whose words are not the document's words, and retrieval finds a
  booklet about prescription drugs
- a question whose answer is spread over two contracts, where one hop reaches
  one of them
- a query that is correct in every way the schema can describe, and returns `0`
  instead of `1,470`, because the values in this graph are upper case
- an agent that calls the same tool twenty times, guessing names, and answers
  with a number that disagrees with its own list

## What you need

**The graph of module 4, in the same Neo4j Desktop DBMS you loaded it into.**
Nothing is built here and nothing is written: every cell in this module reads.

Two more Python packages than the other modules — LangGraph and the LangChain
client — so the install line gains one extra:

```
pip install -e ".[notebooks,graphrag]"
```

And **two models being served**: one that answers, one that embeds. Both are
named in `config.ini`, with the database beside them — point it at your own or
at the ones being served for the class, and nothing else in the notebook
changes. `serving/` holds the notebooks that serve them, one per model.

If the answering model is down the cells that need it fail and say so; the
figures that do not need it still draw.

The module is one notebook, `lesson.ipynb`. `pipelines/` holds the four systems
as code you can call and read; `pictures.py` draws every figure in the lesson
from the results of the cell above it, so no diagram can describe something the
run did not do.
