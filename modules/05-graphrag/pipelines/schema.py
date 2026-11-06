"""Build a description of the graph that a model can reason over.

The first step of the GraphRAG, and it runs once. A model asked to query a graph
it has not been told about writes queries that are syntactically perfect and
match nothing.

What is written here is measured, not asserted. `Organization.name` is not
unique -- 206,113 distinct values over 210,740 nodes -- and that single line
tells a model more than a paragraph of warning would: filtering by name does not
give you a node, it gives you a handful.

    python3 -m pipelines.schema           # build it, or read the cache
    python3 -m pipelines.schema --force   # rebuild even if cached
    python3 -m pipelines.schema --show    # print it

    from pipelines.schema import warm_up
    schema = warm_up()          # ~20s the first time, instant afterwards

Cached to `schema.md`, and the cache carries the node count it was built from.
A cache that goes stale in silence is worse than no cache: the model keeps
reasoning over a graph that no longer exists.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from neo4j import GraphDatabase

from pipelines.config import setting

CACHE = Path(__file__).resolve().parent.parent / "schema.md"

# Counting distinct values over every property of every label is the expensive
# part, and the long tail of properties adds little. Twelve covers the labels
# that matter here; raising it costs seconds per label.
MAX_PROPERTIES = 12

# A property with few distinct values is an enumeration, and knowing the values
# stops a model inventing one.
ENUM_LIMIT = 12



def _driver():
    return GraphDatabase.driver(
        setting("neo4j", "uri"),
        auth=(setting("neo4j", "user"), setting("neo4j", "password")))


def _labels(session) -> list[str]:
    return [r["label"] for r in session.run("CALL db.labels() YIELD label RETURN label")]


def _properties(session, label: str) -> list[str]:
    # Sampled, because unwinding the keys of two million nodes to learn that they
    # all have the same eight is a minute spent on a known answer.
    rows = session.run(
        f"MATCH (n:`{label}`) WITH n LIMIT 500 UNWIND keys(n) AS k RETURN DISTINCT k AS k")
    return [r["k"] for r in rows]


def _label_section(session, label: str) -> str:
    total = session.run(f"MATCH (n:`{label}`) RETURN count(*) AS n").single()["n"]
    if not total:
        return ""

    lines = [f"### {label}", "", f"{total:,} nodes", "", "| property | distinct | present | note |",
             "|---|---:|---:|---|"]

    for prop in _properties(session, label)[:MAX_PROPERTIES]:
        row = session.run(
            f"MATCH (n:`{label}`) RETURN count(DISTINCT n.`{prop}`) AS distinct, "
            f"count(n.`{prop}`) AS present").single()
        distinct, present = row["distinct"], row["present"]

        note = _describe(session, label, prop, distinct, total)

        lines.append(f"| {prop} | {distinct:,} | {present / total:.0%} | {note} |")

    return "\n".join(lines) + "\n"


# Below this, "distinct == total" means nothing: every property of a single
# node is trivially unique.
MIN_FOR_UNIQUENESS = 20

# Almost-unique is the dangerous shape. It looks like a key, a model uses it as
# one, and the query quietly returns several nodes where the question wanted one.
NEAR_UNIQUE = 0.9


# Three examples for every property with 13 to 100 distinct values was tried on
# 4/11/2026 and reverted the same day. It was aimed at one failure -- the schema
# calls `Department.id` "usable as an identifier" and shows no value, so the
# model writes `Chicago Fire Department` where the graph holds
# `CHICAGO FIRE DEPARTMENT`, and the pipeline answers 0 instead of 1,470.
#
# It did not fix that, and it broke two other questions. Three runs each,
# `temperature=0`:
#
#                                      without examples   with examples
#   contracts in the graph                 ok ok ok          ok ok ok
#   departments assign contracts           ok ok ok          no no no
#   Chicago Fire Department                no no no          no no no
#   vendor holding the most contracts      ok ok ok          ok err err
#
# Why it failed to help is the useful part: the three examples are the first
# three by scan order, so `Department.id` came out as `ADMINISTRATIVE
# ADJUDICATION, BOARD OF ELECTION COMMISSIONERS, BOARD OF ETHICS`. Supplied by
# hand, with `CHICAGO FIRE DEPARTMENT` among them, the same change took that
# question from 0 to 1,470. A static schema cannot carry the right example for
# every question -- which is what resolving a name at query time is for.
def _describe(session, label: str, prop: str, distinct: int, total: int) -> str:
    if total < MIN_FOR_UNIQUENESS:
        return f"{distinct} value(s) — too few nodes to judge"
    if distinct == total:
        return "**unique** — usable as an identifier"
    if distinct / total >= NEAR_UNIQUE:
        return (f"**almost unique** — {total - distinct:,} repeat, so filtering by "
                f"it can return more than one node")
    if distinct <= ENUM_LIMIT:
        values = session.run(
            f"MATCH (n:`{label}`) WHERE n.`{prop}` IS NOT NULL "
            f"RETURN DISTINCT n.`{prop}` AS v LIMIT {ENUM_LIMIT}")
        return "one of " + ", ".join(f"`{r['v']}`" for r in values)
    return f"categorical — {distinct:,} values"


def _relationships(session) -> str:
    # db.schema.visualization() returns virtual nodes whose labels() come back
    # empty, so every endpoint renders as (:None). apoc.meta.data samples the
    # real graph instead; it emits each relationship twice, and keeping only the
    # rows whose `label` is a real node label picks the orientation we want.
    rows = session.run("""
        CALL db.labels() YIELD label WITH collect(label) AS nodeLabels
        CALL apoc.meta.data({sample: 500, maxRels: 10})
        YIELD label, property, type, other
        WHERE type = 'RELATIONSHIP' AND label IN nodeLabels
        RETURN label AS start, property AS type, other AS ends
        ORDER BY start, type
    """)
    lines = ["## Relationships", "",
             "Direction matters and Neo4j will not warn you: a pattern written the "
             "wrong way round is legal, matches nothing, and returns no error.", "",
             "| pattern | count | per start node |", "|---|---:|---|"]

    for r in rows:
        start, rtype = r["start"], r["type"]
        for end in (r["ends"] or []):
            stats = session.run(
                f"MATCH (a:`{start}`)-[:`{rtype}`]->(b:`{end}`) "
                f"WITH a, count(DISTINCT b) AS k "
                f"RETURN count(*) AS sources, avg(k) AS mean, max(k) AS most").single()
            if not stats["sources"]:
                continue
            lines.append(
                f"| `({start})-[:{rtype}]->({end})` | {stats['sources']:,} | "
                f"avg {stats['mean']:.2f}, max {stats['most']} |")
    return "\n".join(lines) + "\n"


def build(session) -> str:
    total = session.run("MATCH (n) RETURN count(*) AS n").single()["n"]
    parts = [
        "# Graph schema",
        "",
        "Generated from the database. Every figure is measured; nothing here is "
        "a design intention.",
        "",
        f"<!-- nodes: {total} -->",
        "",
        "## Node labels",
        "",
    ]
    for label in sorted(_labels(session)):
        section = _label_section(session, label)
        if section:
            parts.append(section)
    parts.append(_relationships(session))
    return "\n".join(parts)


def _cached_total(text: str) -> int | None:
    for line in text.splitlines():
        if line.startswith("<!-- nodes:"):
            return int(line.split(":")[1].split("-->")[0])
    return None


def warm_up(force: bool = False, quiet: bool = False) -> str:
    """Return the schema, building it only when it is missing or out of date.

    The check is one `count(*)`. Against twenty seconds of rebuilding it is
    free, and it is the only thing standing between a cached schema and a model
    reasoning confidently about a graph that has since been reloaded.
    """
    def say(message: str) -> None:
        if not quiet:
            print(message)

    driver = _driver()
    try:
        with driver.session(database=setting("neo4j", "database")) as session:
            live = session.run("MATCH (n) RETURN count(*) AS n").single()["n"]

            if CACHE.exists() and not force:
                text = CACHE.read_text()
                cached = _cached_total(text)
                if cached == live:
                    say(f"schema cached ({live:,} nodes, unchanged)")
                    return text
                say(f"graph changed: {cached:,} nodes cached, {live:,} now — rebuilding")
            else:
                say("no schema cached, building it (about 20 seconds)")

            text = build(session)
            CACHE.write_text(text)
            say(f"schema built: {live:,} nodes, written to {CACHE.name}")
            return text
    finally:
        driver.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="rebuild even if cached")
    parser.add_argument("--show", action="store_true", help="print the schema")
    args = parser.parse_args()

    text = warm_up(force=args.force)
    if args.show:
        print("\n" + text)
    else:
        print(f"  {text.count(chr(10) + '### ')} labels, "
              f"{text.count(chr(10) + '| `(')} relationship patterns")
        print(f"  {CACHE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
