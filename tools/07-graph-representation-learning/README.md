# tools/07-graph-representation-learning

Everything that turns the graph of module 4 into a trained graph network: the
arrays, and the training that produces the engine the lesson loads. Run from
this directory.

**You do not need any of this to do module 7.** The module ships the trained
engine in [`serving/gnn/`](../../serving/gnn) and the lesson loads it — four
hundred epochs is five minutes, and a session that trains the same thing twice
spends a twentieth of itself recomputing a number already on the screen. This
folder is for rebuilding it, and for the part of the module that a notebook
cannot hold: changing one thing and running it again.

```text
build_dataset.py  the two queries, and the bookkeeping that numbers the nodes
train.py          the network, the split, and the card that records what it scored
```

## The two commands

```bash
cd tools/07-graph-representation-learning
python build_dataset.py       # ~15 s, writes data/chicago/gnn/owners.npz (4 MB)
python train.py               # ~5 min, writes serving/gnn/owner_filing.pt + .json
```

`build_dataset.py` reads `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` and
`NEO4J_DATABASE` from the environment, as modules 4, 5 and 6 do, and takes the
same four as flags. The database is **named**, never left to the server default:
these queries do not raise on the wrong graph, they return, with numbers from
whatever is in there.

Measured 27/11/2026 on Apple silicon, against the graph module 4 builds:

```text
329,719 (owner, business) rows, 147,796 businesses by 2015
nodes 390,464  = 193,848 owners + 196,616 businesses
columns 52     = 27 owner + 24 business + 1 type flag
edges 287,517  = one per (owner, business); no owner-to-owner edge exists
labelled 69,822 of 390,464 nodes (18%) — 62.4% of them filed again

seed    valid     test  at epoch  test rows
   0   0.7161   0.7080        70     20,946
```

Those are the numbers in the shipped card. If yours differ in the third decimal
that is the accelerator, not a mistake; if they differ in the first, the graph
underneath is not the one module 4 builds.

## Why the card exists

`train.py` writes the weights **and** a JSON file saying what they are and what
they measured, and the lesson asserts one against the other: it loads the engine,
scores the held-out third with the features the notebook built, and stops if the
answer is not the card's within 0.002.

That assertion is the only thing standing between the module and its worst
failure mode, which is silent. Change a column in the lesson, or a cap, or the
order the nodes are numbered in, and the engine still loads — `load_state_dict`
checks shapes, and 52 columns are 52 columns whatever they mean. It then answers
confidently about owners, from the wrong features, and nothing anywhere says so.

The same reasoning is why this folder exists at all. Before it, the numbers came
from a research script that trained, measured, printed and dropped the model: the
register held numbers whose models no longer existed, which is a memory and not a
result.

## The split is the decision

```bash
python train.py --split random        # the way everybody splits
python train.py --seeds 4             # four seeds, and the spread between them
python train.py --epochs 60           # what fits in a live session
```

Two owners who hold a business together are labelled by the same licence. A
random split puts one of them in the training half with the answer attached and
asks for the other; nothing fails, and the test score goes up by about five
points. `--split random` is here so that gap can be run rather than believed —
and `--seeds 4` because a margin smaller than the seed-to-seed spread is not a
margin. On the honest split that spread was 0.008.

## What is not here

**No fetching, no graph building.** This folder starts from the graph module 4
loads; [`tools/04-building-the-graph`](../04-building-the-graph) is what builds
it.

**No feature engineering beyond the two queries.** That is the module's point
rather than an omission: an owner in this register has almost no attributes of
her own, so everything the model knows about her except her title is what she
owns — and that is what the graph is for.

**No `NeighborLoader`, no sampling.** 390,464 nodes by 52 columns is 81 MB; the
whole graph goes through every forward pass. The lesson says where that stops
being true.
