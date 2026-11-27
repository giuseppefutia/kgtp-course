# Module 7 — Graph Representation Learning

Modules 3 to 5 built a graph and asked it questions. Today a model learns from
it — and the first thing to settle is whether it should.

- Live session: 1.5h
- Prerequisites: the graph of module 4; module 5's agent for the last section.

## The problem

A graph is not a table, so something has to turn a node's neighbours into a row.
A query can do that with `avg()`. A graph neural network does it with weights it
learns. Most of this session is about telling those two apart — and about the
three decisions that move the answer more than the choice of architecture does.

The task is real and it is not a toy: of the 193,848 business owners the City of
Chicago register resolves, which ones file another licence between 2018 and
2021? Everything the model reads is cut at 2015. One column may look past that
cut — the answer.

## What the module builds, in order

1. **Zachary's karate club, and four models on it.** Eight members whose side we
   know, twenty-six to guess. Three models that ignore the edges get 12, 13 and
   13 of the 26; a two-layer GCN on the same four columns gets 19. That is the
   whole case for the rest of the module, in a graph that fits in one figure.
2. **One forward pass, by hand.** `GCNConv` rebuilt with a matrix multiply and a
   division by `sqrt(degree)`, to seven decimal places of agreement. The mixing
   is an average; what a network adds is the weights on it, not the averaging.
3. **The same shape on Chicago.** Two Cypher queries, then bookkeeping: 390,464
   nodes, 52 columns, 287,517 edges, 69,822 of them carrying an answer. The
   figure that matters here is the one showing what `x`, `edge_index` and `y`
   actually hold, with one real owner's row in them.
4. **Five models on the same columns.** Logistic regression, random forest,
   gradient boosting, an MLP of *equal capacity*, and the network. The MLP is
   the control the section turns on: same layers, same parameters, empty
   `edge_index`.
5. **Which direction the edges go.** Written both ways the network scores 0.729.
   Written `owner -> business` only it scores 0.696 — which is, to four decimal
   places, exactly what the same network scores with no edges at all.
6. **The same question, split another way.** Co-owners kept together instead of
   shuffled, and nothing else changed.
7. **The engine as a tool of the agent.** The trained network, loaded from disk,
   scoring one owner from her own three-hop neighbourhood, handed to module 5's
   agent as a ninth tool.

## What you will see fail

**The headline number loses most of itself to one line of code.** Over four
seeds and four hundred epochs, the network's lead over the best model that
ignores the graph is 5.6 points on a random split and 0.2 on a split that keeps
co-owners together — and 0.2 is smaller than the 0.008 spread between those four
seeds would need it to be to mean anything. Nothing breaks and nothing
warns you: a business with two owners that filed once labels *both* of them 1,
so a random order hands the model one of the pair with the answer attached and
asks it to guess the other. A draw cuts 6,724 such pairs.

**Half of an edge list is worth nothing at all.** A message that leaves an owner
and never comes back cannot change her row, so the model is an MLP with extra
steps — and it scores like one, to four decimals.

**The column labelled `degree` does not hold degrees.** All four columns of the
karate figure are standardised centralities, so member 13's +0.11 is five
friends against a club average of 4.6 — not the number five. The section that
rebuilds a forward pass by hand only works once that is said out loud, and it
went two drafts without being.

**The subgraph check that found a bug in the subgraph query.** Three layers reach
three hops and no further, so an owner's score from her own neighbourhood must
be the number the whole-graph pass gave her — not close to it, the same. It was
0.007 off for two owners out of four, which is how the third hop was found to be
collecting the wrong businesses. The notebook now asserts the equality rather
than printing it.

## What you need

**The graph of module 4**, read-only. `NEO4J_URI`, `NEO4J_USER`,
`NEO4J_PASSWORD` and `NEO4J_DATABASE` are read from the environment as in
modules 4, 5 and 6. Nothing in this module writes to the graph.

**One package group more than module 6**, and it is the big one:

```
pip install -e ".[notebooks,graphrag,gnn]"
```

About 560 MB on top of what module 6 needed, 328 of them torch. `graphrag` is in
that line because the last section imports module 5's agent.

**The trained engine, which ships with the module** in
[`serving/gnn/`](../../serving/gnn): the weights, and a card saying what they
scored. The lesson loads them rather than training — four hundred epochs is five
minutes, and it checks the card rather than trusting it. To rebuild them, and
for the experiments a notebook cannot hold, see
[`tools/07-graph-representation-learning`](../../tools/07-graph-representation-learning).

**One model being served**, for the last cell only — the agent's. If the endpoint
is down that cell says so and prints the tool's own answer, which needs no model:
it is a Cypher query and a forward pass. Nothing else in the notebook calls a
model.

The module is one notebook, `lesson.ipynb`. `pictures.py` draws every figure
from the results of the cell above it, so no figure can say something the data
did not.

## One sentence of caution, and it is in the notebook too

This module puts a probability on a **person**. It is a ranking over owners in
aggregate, measured at an AUC of 0.71 — right about seven times in ten on a
random pair of owners, one of whom filed. It is not a verdict about anybody, it
does not say a business will fail, and it is not a reason to deny anyone
anything. The tool the agent calls returns that sentence with every number, and
the system prompt orders the model to repeat it.
