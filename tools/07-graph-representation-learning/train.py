"""Train the engine the lesson loads, and write it next to what it scored.

    python train.py                       the shipped configuration
    python train.py --epochs 60           what fits in a live session
    python train.py --split random        the leaky split, to see the difference
    python train.py --seeds 4             four seeds, and the spread between them

Reads what `build_dataset.py` wrote and produces two files: the weights, and a
card saying what they are and what they measured. The card is the point. A
number in a notebook whose model no longer exists is a memory, not a result, and
that is exactly what this folder had before this file: the research script
trained, measured, printed and dropped the model.

THE SPLIT IS THE DECISION, NOT A DETAIL
---------------------------------------
Two owners who hold a business together are labelled by the same licence, so a
random split puts one of them in the training half with the answer attached and
asks for the other. Nothing fails; the number goes up by five points. The
default here keeps whole connected components of co-ownership on one side, which
is the honest number and the one the shipped card carries. `--split random`
exists so the gap can be seen rather than taken on trust.

WHAT TO EXPECT
--------------
About five minutes on an Apple-silicon laptop for the 400 epochs of the shipped
configuration, and the whole graph is in memory at once -- 390,464 nodes by 52
columns is small. The epoch is chosen on the validation slice: choosing it by
looking at the test set is model selection on the thing being reported, and it
flatters only the models that have epochs.
"""

from __future__ import annotations

import argparse
import datetime
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from scipy import sparse
from scipy.sparse.csgraph import connected_components
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from torch_geometric.nn import SAGEConv


class Net(nn.Module):
    """Three layers of message passing, then one number per node.

    The same class as the lesson's, down to the attribute names, because the
    lesson loads this file's output with `load_state_dict`: rename `layers` or
    `head` here and the load fails. That is the intended coupling -- the
    alternative is a rename that loads fine into the wrong shape.

    A layer is a hop. On this graph the first reaches an owner's businesses, the
    second the people on them, the third those people's businesses.
    """

    def __init__(self, columns, hidden=256, layers=3, dropout=0.2):
        super().__init__()
        self.layers = nn.ModuleList(
            [SAGEConv(columns if i == 0 else hidden, hidden) for i in range(layers)])
        self.head = nn.Linear(hidden, 1)
        self.dropout = dropout

    def forward(self, x, edge_index):
        for conv in self.layers:
            x = F.dropout(F.relu(conv(x, edge_index)), self.dropout, self.training)
        return self.head(x).squeeze(-1)


def co_ownership(owns, knowable, people, shops):
    """Who shares a business with whom, as a graph the data does not contain.

    There is no owner-to-owner edge in the register, so this is `P @ P.T`: the
    two-hop projection of the graph the network trains on. The business column
    comes back to its position inside the business block, because in `owns` it
    is offset by the number of people.
    """
    incidence = sparse.csr_matrix(
        (np.ones(len(owns), dtype=np.float32), (owns[:, 0], owns[:, 1] - people)),
        shape=(people, shops))
    together = (incidence[knowable] @ incidence[knowable].T).tocsr()
    together.setdiag(0)
    together.eliminate_zeros()
    return together


def by_component(seed, group, components, n, test_share=0.3, valid_share=0.2):
    """Whole groups to one slice. Co-owners are never split.

    Groups go in whole, so the slices come out a little uneven: components do
    not divide into exact thirds, and the largest of them holds 13,290 owners.
    They are left uneven rather than forced -- trimming a group to hit a round
    third puts part of it on the other side, which is the thing this function
    exists to prevent.
    """
    rng = np.random.default_rng(seed)
    order = rng.permutation(components)
    size = np.bincount(group, minlength=components)
    where = np.zeros(components, dtype=np.int8)      # 0 train, 1 valid, 2 test
    taken, target = 0, int(n * test_share)
    for g in order:
        if taken >= target:
            break
        where[g] = 2
        taken += size[g]
    rest = [g for g in order if where[g] == 0]
    taken, target = 0, int(sum(size[g] for g in rest) * valid_share)
    for g in rest:
        if taken >= target:
            break
        where[g] = 1
        taken += size[g]
    per_owner = where[group]
    return (np.flatnonzero(per_owner == 0), np.flatnonzero(per_owner == 1),
            np.flatnonzero(per_owner == 2))


def at_random(seed, label):
    """Test, and a validation slice carved out of the training half.

    The way everybody splits, and the reason this module has a section about it.
    """
    train, test = train_test_split(np.arange(len(label)), test_size=0.3,
                                   random_state=seed, stratify=label)
    train, valid = train_test_split(train, test_size=0.2, random_state=seed,
                                    stratify=label[train])
    return train, valid, test


def run(seed, data, slices, device, *, epochs, hidden, layers, dropout, lr,
        keep=False):
    """One training run. Returns the test AUC at the best validation epoch."""
    features, owns = data["features"], data["owns"]
    knowable, label = data["knowable"], data["label"]
    x = torch.tensor(features).to(device)
    # Both directions. Written one way only, a message leaves an owner and
    # never comes back: her row never changes, and the network scores exactly
    # what the same network scores with no edges at all.
    edge_index = torch.tensor(
        np.concatenate([owns, owns[:, ::-1]]).T.copy()).to(device)

    torch.manual_seed(seed)
    train, valid, test = slices
    model = Net(features.shape[1], hidden, layers, dropout).to(device)
    optimiser = torch.optim.Adam(model.parameters(), lr=lr)
    rows = torch.tensor(knowable[train]).to(device)
    answers = torch.tensor(label[train], dtype=torch.float32).to(device)

    best_valid, test_there, best_state, best_epoch = 0.0, 0.0, None, -1
    for epoch in range(epochs):
        model.train()
        optimiser.zero_grad()
        F.binary_cross_entropy_with_logits(
            model(x, edge_index)[rows], answers).backward()
        optimiser.step()
        if epoch % 10 == 0 or epoch == epochs - 1:
            model.eval()
            with torch.no_grad():
                scores = model(x, edge_index).cpu().numpy()
            here = roc_auc_score(label[valid], scores[knowable[valid]])
            if here > best_valid:
                best_valid, best_epoch = here, epoch
                test_there = roc_auc_score(label[test], scores[knowable[test]])
                if keep:
                    # On the CPU, and copied: the live tensors keep training.
                    best_state = {k: v.detach().cpu().clone()
                                  for k, v in model.state_dict().items()}
    return dict(valid=best_valid, test=test_there, epoch=best_epoch,
                rows=len(test), state=best_state)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", default="../../data/chicago/gnn/owners.npz")
    parser.add_argument("--out", default="../../serving/gnn/owner_filing.pt")
    parser.add_argument("--split", default="component",
                        choices=["component", "random"])
    parser.add_argument("--epochs", type=int, default=400)
    parser.add_argument("--hidden", type=int, default=256)
    parser.add_argument("--layers", type=int, default=3)
    parser.add_argument("--dropout", type=float, default=0.2)
    parser.add_argument("--lr", type=float, default=0.01)
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--save", action="store_true", default=None,
                        help="write the weights and the card; on by default for "
                             "one seed on the component split, off otherwise")
    # Some scatter operations are missing on Metal. The fallback is declared
    # rather than silent: a run that quietly moved to the CPU and took an hour
    # looks like a hung script.
    parser.add_argument("--device", default="auto", choices=["auto", "cpu"])
    args = parser.parse_args()

    bundle = np.load(args.data, allow_pickle=True)
    data = {k: bundle[k] for k in ("features", "owns", "knowable", "label")}
    device = torch.device("mps" if args.device == "auto"
                          and torch.backends.mps.is_available() else "cpu")
    knowable, label = data["knowable"], data["label"]
    print(f"{len(data['features']):,} nodes x {data['features'].shape[1]} columns, "
          f"{len(data['owns']):,} edges, {len(knowable):,} labelled, on {device}")

    if args.split == "component":
        together = co_ownership(data["owns"], knowable, len(bundle["people"]),
                                len(bundle["shops"]))
        components, group = connected_components(together, directed=False)
        print(f"{components:,} connected groups of owners, "
              f"largest {np.bincount(group).max():,}")

        def slices_for(seed):
            return by_component(seed, group, components, len(knowable))
    else:
        def slices_for(seed):
            return at_random(seed, label)

    save = args.save
    if save is None:
        save = args.seeds == 1 and args.split == "component"

    print(f"\n{'seed':>4s} {'valid':>8s} {'test':>8s} {'at epoch':>9s} "
          f"{'test rows':>10s}")
    print("-" * 44)
    results = []
    for seed in range(args.seeds):
        started = time.perf_counter()
        got = run(seed, data, slices_for(seed), device, epochs=args.epochs,
                  hidden=args.hidden, layers=args.layers, dropout=args.dropout,
                  lr=args.lr, keep=save and seed == 0)
        results.append(got)
        print(f"{seed:>4d} {got['valid']:>8.4f} {got['test']:>8.4f} "
              f"{got['epoch']:>9d} {got['rows']:>10,}"
              f"   ({time.perf_counter() - started:.0f}s)")
    tests = [r["test"] for r in results]
    if len(tests) > 1:
        print(f"\nmean {np.mean(tests):.4f}   spread {max(tests) - min(tests):.4f}"
              f"   <- a margin smaller than the spread is not a margin")

    if not save:
        print("\nnothing written: pass --save, or run one seed on the component "
              "split, to produce the engine the lesson loads")
        return 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(results[0]["state"], out)
    card = {
        "task": "a new licence on anything the owner holds, 2018-2021",
        "observed_to": 2015,
        "split": ("by connected component of co-ownership"
                  if args.split == "component" else "at random -- leaky"),
        "columns": int(data["features"].shape[1]),
        "hidden": args.hidden, "layers": args.layers, "dropout": args.dropout,
        "epochs": args.epochs, "seed": 0, "metric": "roc_auc",
        "valid": round(results[0]["valid"], 4),
        "test": round(results[0]["test"], 4),
        "test_rows": int(results[0]["rows"]),
        "trained": datetime.date.today().isoformat(),
    }
    card_path = out.with_suffix(".json")
    card_path.write_text(json.dumps(card, indent=1) + "\n")
    print(f"\nwrote {out}  ({out.stat().st_size / 1e6:.1f} MB)")
    print(f"wrote {card_path}  — the lesson checks the engine against it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
