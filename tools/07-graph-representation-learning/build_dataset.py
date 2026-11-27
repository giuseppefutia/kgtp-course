"""Turn the graph of module 4 into the three arrays a graph network is handed.

    python build_dataset.py
    python build_dataset.py --out ../../data/chicago/gnn/owners.npz
    python build_dataset.py --database kgtp

Two queries and some bookkeeping. The queries are the same two the lesson runs
in section 3, kept here word for word: this file exists so the training below it
can be reproduced outside a notebook, not to be a second opinion about what the
data is. If the two ever disagree, the lesson's own assertion fires -- it loads
the engine this pipeline trains and checks that it still scores what its card
says, which it cannot if the columns moved.

WHAT GOES IN THE FILE
---------------------
`features`  one row per node, owners first then businesses, 52 columns
`owns`      one (owner row, business row) pair per edge, one direction
`knowable`  the node rows that carry an answer
`label`     that answer: did the owner file again between 2018 and 2021
`people`    the cluster ids behind the owner rows, in order
`shops`     the business ids behind the business rows, in order

The two id lists are in the file for one reason: without them a row number is
not reversible, and the first thing anyone wants after training is to ask about
a named person.

EVERY DATE IS CUT AT 2015 EXCEPT THE LABEL
------------------------------------------
Which is the whole shape of the task: the model is standing in 2015 and asked
about 2018-2021. One column may look past the cut -- `opened`, the answer -- and
a feature that looks past it is the leak this module is mostly about.
"""

from __future__ import annotations

import argparse
import os
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from neo4j import GraphDatabase

# One row per (owner, business). Everything is cut at 2015 except `opened`.
OWNERS = """
MATCH (r:PersonRecord {source:'OWNERS'})-[:RECORD_RESOLVED_TO]->(p:Person)
MATCH (o:Organization {source:'LICENSES'}) WHERE o.id = r.employerId
MATCH (o)-[:ORG_HAS_LICENSE]->(l:LicenseRecord)
WITH p.clusterId AS person, r.title AS title, o.id AS business,
     min(toInteger(right(l.startDate,4)))  AS first_year,
     count(CASE WHEN toInteger(right(l.startDate,4)) >= 2012
                 AND toInteger(right(l.startDate,4)) <  2015 THEN 1 END) AS recent,
     max(CASE WHEN toInteger(right(l.startDate,4)) <= 2015
                AND toInteger(right(l.endDate,4))   >= 2015 THEN 1 ELSE 0 END) AS active,
     max(CASE WHEN toInteger(right(l.startDate,4)) >= 2018
                AND toInteger(right(l.startDate,4)) <  2021 THEN 1 ELSE 0 END) AS opened
RETURN person, title, business, first_year, recent, active, opened
"""

# What each business was by 2015. The owners have almost no attributes of their
# own, so this is where a neighbour's information comes from.
BUSINESSES = """
MATCH (o:Organization {source:'LICENSES'})-[:ORG_HAS_LICENSE]->(l:LicenseRecord)
  WHERE toInteger(right(l.startDate,4)) <= 2015
WITH o.id AS business, count(l) AS licences, count(DISTINCT l.code) AS kinds,
     min(toInteger(right(l.startDate,4))) AS first_year,
     collect(DISTINCT l.code)[0] AS code
RETURN business, licences, kinds, first_year, code
"""


def read(uri: str, user: str, password: str, database: str):
    """The two queries, into two dataframes."""
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session(database=database) as session:
            owners = pd.DataFrame([dict(r) for r in session.run(OWNERS)])
            businesses = pd.DataFrame([dict(r) for r in session.run(BUSINESSES)])
    finally:
        driver.close()
    return owners, businesses


def encode(owners: pd.DataFrame, businesses: pd.DataFrame):
    """Rows and pairs to arrays, and a node becomes a position.

    Owners first and businesses after, in one array. Keeping two numbering
    schemes is the mistake this function exists to avoid: an edge whose ends are
    numbered by different rules trains without complaint and means nothing.
    """
    people = sorted(owners["person"].unique())
    shops = sorted(owners["business"].unique())
    at = {k: i for i, k in enumerate(people)}
    at.update({k: len(people) + i for i, k in enumerate(shops)})

    titles = sorted(t for t in owners["title"].dropna().unique())
    column_of = {t: i for i, t in enumerate(titles)}
    own_columns = len(titles) + 4

    by_person = owners.groupby("person")
    derived = pd.DataFrame({"businesses": by_person["business"].nunique(),
                            "first": by_person["first_year"].min(),
                            "recent": by_person["recent"].sum()})

    owner_block = np.zeros((len(people), own_columns), dtype=np.float32)
    for title, rows in owners.dropna(subset=["title"]).groupby("title"):
        owner_block[[at[p] for p in rows["person"].unique()], column_of[title]] = 1.0
    where = np.array([at[p] for p in derived.index])
    # Capped, then scaled to [0, 1]. Uncapped, a handful of owners with hundreds
    # of licences would flatten everybody else onto the same value.
    owner_block[where, len(titles) + 0] = np.minimum(derived["businesses"], 20) / 20
    owner_block[where, len(titles) + 1] = np.clip(2015 - derived["first"].fillna(2015),
                                                  0, 40) / 40
    owner_block[where, len(titles) + 2] = (derived["recent"] > 0).astype(np.float32)
    owner_block[where, len(titles) + 3] = np.minimum(derived["recent"], 10) / 10

    top_codes = [c for c, _ in Counter(businesses["code"]).most_common(20)]
    code_of = {c: i for i, c in enumerate(top_codes)}
    shop_block = np.zeros((len(shops), 3 + len(top_codes) + 1), dtype=np.float32)
    known = businesses[businesses["business"].isin(at)]
    rows = np.array([at[b] - len(people) for b in known["business"]])
    shop_block[rows, 0] = np.clip(2015 - known["first_year"], 0, 40) / 40
    shop_block[rows, 1] = np.minimum(known["licences"], 50) / 50
    shop_block[rows, 2] = np.minimum(known["kinds"], 10) / 10
    for code, rows_of in known.groupby("code"):
        shop_block[[at[b] - len(people) for b in rows_of["business"]],
                   3 + code_of.get(code, len(top_codes))] = 1.0

    # One block per node type, and a flag saying which. An owner is zeros where a
    # business has its columns and the other way round: the standard way to put
    # two kinds of node in one homogeneous graph without pretending their
    # features are the same thing.
    features = np.zeros((len(people) + len(shops),
                         own_columns + shop_block.shape[1] + 1), dtype=np.float32)
    features[:len(people), :own_columns] = owner_block
    features[len(people):, own_columns:own_columns + shop_block.shape[1]] = shop_block
    features[:len(people), -1] = 1.0

    owns = np.array(sorted({(at[p], at[b])
                            for p, b in zip(owners["person"], owners["business"])}),
                    dtype=np.int64)

    # The cohort: owners holding something still live in 2015. Asking about an
    # owner whose last licence ended in 2009 is asking whether a closed business
    # reopens, which is a different question with a different base rate.
    cohort = owners.groupby("person")[["active", "opened"]].max()
    cohort = cohort[cohort["active"] == 1]
    knowable = np.array([at[p] for p in cohort.index])
    label = cohort["opened"].to_numpy().astype(np.int64)

    assert owns.max() < len(features), "an edge points past the end of the node array"
    assert (knowable < len(people)).all(), "a labelled node is not an owner"
    return dict(features=features, owns=owns, knowable=knowable, label=label,
                people=np.array(people, dtype=object),
                shops=np.array(shops, dtype=object),
                own_columns=np.int64(own_columns))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="../../data/chicago/gnn/owners.npz")
    parser.add_argument("--uri", default=os.environ.get("NEO4J_URI",
                                                        "bolt://localhost:7687"))
    parser.add_argument("--user", default=os.environ.get("NEO4J_USER", "neo4j"))
    parser.add_argument("--password",
                        default=os.environ.get("NEO4J_PASSWORD", "password"))
    # Named and not left to the server default. The default database on an
    # instance that has been used for anything else holds another graph, and
    # these queries do not raise on it: they return, with numbers from whatever
    # is in there.
    parser.add_argument("--database",
                        default=os.environ.get("NEO4J_DATABASE", "kgtp"))
    args = parser.parse_args()

    started = time.perf_counter()
    owners, businesses = read(args.uri, args.user, args.password, args.database)
    print(f"{len(owners):,} (owner, business) rows, "
          f"{len(businesses):,} businesses by 2015 "
          f"({time.perf_counter() - started:.0f} s for both queries)")

    built = encode(owners, businesses)
    people, shops = len(built["people"]), len(built["shops"])
    print(f"nodes {len(built['features']):,}  = {people:,} owners + {shops:,} businesses")
    print(f"columns {built['features'].shape[1]}     = {int(built['own_columns'])} owner "
          f"+ {built['features'].shape[1] - int(built['own_columns']) - 1} business "
          f"+ 1 type flag")
    print(f"edges {len(built['owns']):,}  = one per (owner, business); "
          f"no owner-to-owner edge exists")
    print(f"labelled {len(built['knowable']):,} of {len(built['features']):,} nodes "
          f"({len(built['knowable']) / len(built['features']):.0%}) — "
          f"{built['label'].mean():.1%} of them filed again")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, **built)
    print(f"\nwrote {out}  ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
