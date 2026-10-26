"""Canonical person name, shared by every source that creates PersonRecord.

Entity resolution compares PersonRecord.fullName through the
`person_record_fullName` full-text index and a Sorensen-Dice threshold. Two
sources that normalise names differently simply never match each other, and the
failure is silent: fewer pairs, no error, nothing in the output that says
anything went wrong.

That is why the expression lives here once and is interpolated into each
importer's query. Copying it would give two implementations that agree today
and drift the first time one of them learns about apostrophes or suffixes.

Business Owners already provides first/middle/last as separate columns;
Employees provides a single `Name` field that its importer splits first. The
layouts differ, the normalisation must not.

Everything here happens before any name exists. Loading is batched -- one query
per N rows, with `UNWIND $batch AS item` -- so there are two separate moments:
the query *text* is built once in Python at start-up, and the expression inside
it is evaluated by Neo4j thousands of times, row by row. This file lives
entirely in the first: it normalises nothing, it generates the Cypher that will.
That is why the arguments below are expressions rather than values.
"""

PLACEHOLDER = "__CANONICAL_NAME__"


def canonical_full_name(first, middle, last):
    """Return the Cypher expression yielding the canonical name, or NULL.

    The three arguments are Cypher *expressions*, not values: each importer
    passes whatever reads its own columns. This is what lets the normalisation
    stay identical while the source layout differs.

    Empty input yields NULL rather than an empty string, because
    people_cluster.py filters on `fullName IS NULL` to skip unusable records.
    """
    joined = (
        f"coalesce({first}, '') + ' ' + "
        f"coalesce({middle}, '') + ' ' + "
        f"coalesce({last}, '')"
    )
    collapsed = f'trim(apoc.text.replace({joined}, "\\s+", " "))'
    return (
        f"CASE WHEN {collapsed} = '' THEN NULL "
        f"ELSE apoc.text.capitalizeAll(toLower({collapsed})) END"
    )


def with_canonical_name(query, first, middle, last):
    """Replace PLACEHOLDER in `query` with the canonical name expression.

    A placeholder rather than an f-string because the queries contain Cypher
    map literals such as `{id: item.RECORD_ID}`, which an f-string would try to
    interpolate.
    """
    # Raising beats str.replace()'s own behaviour, which returns the query
    # untouched when the target is absent. A query that lost its placeholder in
    # a rewrite is still valid Cypher: it loads every record with id, firstName,
    # lastName and source, and only fullName is missing. people_cluster.py then
    # filters on `fullName IS NULL` and drops the whole source from resolution,
    # while the counts still add up and nothing logs anything. This moves that
    # failure to import time, where it names the placeholder it could not find.
    if PLACEHOLDER not in query:
        raise ValueError(f"query does not contain {PLACEHOLDER}")
    return query.replace(PLACEHOLDER, canonical_full_name(first, middle, last))
