"""The graph primitives, in one place, for the three things that need them.

    from pipelines.graph import find_entity, contracts_of, about_contracts

Before this file the same four operations existed three times: once inside the
GraphRAG pipeline, once inside the benchmark's scenario 3, once inside the
agent's tools. `find_entity` here and `link` there resolved the same name to the
same group with two copies of the same Cypher, and they had already drifted.

The split is deliberate:

    find_entity / contracts_of / about_contracts / neighbourhood
        return **rows**. They are queries, and a query returns data.

    render_entities / render_contracts / render_about
        turn rows into the **exact strings** a model is shown. That text is
        prompt engineering -- it is tuned against a model, it carries warnings
        about what a list does not prove (decision 41), and changing a word of
        it moves the agent's routing on unrelated questions.

Keeping the two apart is what lets the notebook show a retrieval as a table and
the agent send it as text, without two implementations that disagree by
Christmas.

It also makes the claim of section 8 checkable rather than rhetorical: the agent
is not a different retriever, it is these same functions called in an order
decided at runtime instead of written down in advance.
"""

from __future__ import annotations

# Past this a vendor's reach is a list to fetch with contracts_of, not a line of
# text to read: decision 41.
ENUMERATION = 2000

# Decision 33: resolve to the group, and name it after the member holding the
# most contracts. `OrganizationGroup.name` is one of its members' names but is
# not chosen for prominence -- L28 answers to `WALSH CONSTRUCTIONQ`, a node with
# one contract, over `WALSH CONSTRUCTION COMPANY OF ILL` which has 48.
FIND_ORG = """
CALL db.index.fulltext.queryNodes('organization_name', $q) YIELD node, score
MATCH (node)-[:BELONGS_TO_ORG_GROUP]->(g:OrganizationGroup)
WITH g, max(score) AS score
MATCH (m:Organization)-[:BELONGS_TO_ORG_GROUP]->(g)
OPTIONAL MATCH (m)<-[:HAS_VENDOR]-(c:Contract)
WITH g, score, m, count(DISTINCT c) AS weight
WITH g, score, sum(weight) AS contracts, collect({name: m.name, w: weight}) AS members
WHERE contracts > 0
WITH g, score, contracts, members ORDER BY score DESC LIMIT 50
WITH g, contracts, [x IN members WHERE x.w = reduce(mx = 0, y IN members |
        CASE WHEN y.w > mx THEN y.w ELSE mx END) | x.name][0] AS label
RETURN 'vendor:' + g.clusterId AS id, label, contracts ORDER BY contracts DESC
"""

FIND_DEPT = """
MATCH (d:Department) WHERE toUpper(d.id) CONTAINS toUpper($q)
OPTIONAL MATCH (d)-[:ASSIGNS_CONTRACT]->(c:Contract)
WITH d, count(DISTINCT c) AS contracts WHERE contracts > 0
RETURN 'department:' + d.id AS id, d.id AS label, contracts
ORDER BY contracts DESC LIMIT 5
"""

# A programme is named by the grant agreements, not by the CSV, and it is the
# only thing that groups contracts of different vendors: decision 43. It is not
# offered to the agent (decision 44) but the pipeline and the notebook use it.
FIND_PROGRAM = """
CALL db.index.fulltext.queryNodes('program_name', $q) YIELD node, score
MATCH (node)<-[:PART_OF_PROGRAM]-(c:Contract)
WITH node, score, count(DISTINCT c) AS contracts ORDER BY score DESC LIMIT 4
RETURN node.id AS id, node.name AS label, contracts
"""

# How an identifier reaches its contracts. Kept as patterns rather than whole
# queries so that two of them combine: on 17/9/2026 the agent was asked for Erie
# Neighborhood House's contracts with the Department of Public Health, had no
# tool that intersects, listed the department's 6,868 contracts, read the first
# 50, and answered that there were none. There are 22.
CONTRACT_PATTERN = {
    "vendor": ("(:OrganizationGroup {clusterId: $%s})<-[:BELONGS_TO_ORG_GROUP]-(:Organization)"
               "<-[:HAS_VENDOR]-(c:Contract)"),
    "department": "(:Department {id: $%s})-[:ASSIGNS_CONTRACT]->(c:Contract)",
    # The Program node carries its namespace inside `id` (decision 14), unlike a
    # cluster id or a department name, so the prefix is put back here.
    "program": "(:Program {id: 'program:' + $%s})<-[:PART_OF_PROGRAM]-(c:Contract)",
}

# The bridge. For each purchase order: the vendor resolved to its group and named
# after the member holding most contracts (#33), the department, the contract
# types -- and, per vendor group, how far it reaches. That last part is in no
# document of the contract, and it is the reason to cross from text to graph.
ABOUT = """
UNWIND $pos AS po
MATCH (c:Contract {id: po})
OPTIONAL MATCH (c)-[:HAS_VENDOR]->(:Organization)-[:BELONGS_TO_ORG_GROUP]->(g)
OPTIONAL MATCH (m:Organization)-[:BELONGS_TO_ORG_GROUP]->(g)
OPTIONAL MATCH (m)<-[:HAS_VENDOR]-(mc:Contract)
WITH c, g, m, count(DISTINCT mc) AS weight ORDER BY weight DESC
WITH c, g, collect(m.name)[0] AS vendor
OPTIONAL MATCH (dep:Department)-[:ASSIGNS_CONTRACT]->(c)
OPTIONAL MATCH (c)<-[:INCLUDED_IN_CONTRACT]-(:ContractRecord)-[:HAS_CONTRACT_TYPE]->(ct)
RETURN c.id AS po, vendor, g.clusterId AS vendorGroup,
       collect(DISTINCT dep.id) AS departments, collect(DISTINCT ct.id) AS types
"""

REACH = """
MATCH (g:OrganizationGroup {clusterId: $group})<-[:BELONGS_TO_ORG_GROUP]-(:Organization)
      <-[:HAS_VENDOR]-(c:Contract)
OPTIONAL MATCH (dep:Department)-[:ASSIGNS_CONTRACT]->(c)
RETURN count(DISTINCT c) AS contracts, collect(DISTINCT dep.id) AS departments
"""

# Grouped by relation type rather than emitted as triples: the paper's own
# saving, 19-53% fewer tokens for the same content.
TRAVERSE = """
UNWIND $nodes AS nid
MATCH (start) WHERE elementId(start) = nid
MATCH path = (start)-[*1..%d]-(other)
WITH other, relationships(path) AS rels, length(path) AS hops
RETURN labels(other)[0] AS label,
       coalesce(other.name, other.id) AS name,
       type(rels[-1]) AS via, hops, count(*) AS paths
ORDER BY hops, paths DESC
"""

COUNT_PATHS = """
UNWIND $nodes AS nid
MATCH (start) WHERE elementId(start) = nid
MATCH path = (start)-[*1..%d]-(other)
RETURN count(path) AS n
"""

MEMBERS = """
MATCH (g:OrganizationGroup {clusterId: $group})<-[:BELONGS_TO_ORG_GROUP]-(m:Organization)
RETURN [x IN collect(elementId(m))] AS nodes
"""


# --- the queries ----------------------------------------------------------


def find_entity(session, name: str, limit: int = 6) -> list[dict]:
    """A name to identifiers, never the other way round (decision 39).

    Organizations first, then departments, because a term that matches both is
    almost always the company. The caller chooses; this returns candidates, and
    returning several is information -- on 20/9/2026 `Patson Inc` came back as
    two entities with the same score, one holding 30 contracts and one holding
    50, and nothing downstream could have known that from a single answer.
    """
    rows = [dict(r) for r in session.run(FIND_ORG, q=f'"{name}"')]
    rows += [dict(r) for r in session.run(FIND_DEPT, q=name)]
    return rows[:limit]


def find_program(session, name: str) -> list[dict]:
    return [dict(r) for r in session.run(FIND_PROGRAM, q=f'"{name}"')]


def contracts_query(kind: str, within: str | None) -> str:
    query = f"MATCH {CONTRACT_PATTERN[kind] % 'a'} WITH DISTINCT c"
    if within:
        query += f" WHERE EXISTS {{ MATCH {CONTRACT_PATTERN[within] % 'b'} }}"
    return query + " RETURN c.id AS po, c.name AS name ORDER BY c.id"


def contracts_of(session, entity_id: str, within: str | None = None) -> list[dict]:
    """Every contract of an entity, optionally intersected with a second one.

    The intersection is a query, not a comparison of two lists in a prompt:
    decision 41.
    """
    kind, _, value = entity_id.partition(":")
    within_kind, _, within_value = (within or "").partition(":")
    return [dict(r) for r in session.run(
        contracts_query(kind, within_kind or None), a=value, b=within_value)]


def about_contracts(session, pos: list[str]) -> list[dict]:
    """Purchase orders to vendor, department, type, and the vendor's reach.

    The reach -- how many contracts the vendor holds and across how many
    departments -- is what no document of a single contract can say, and it is
    computed once per group rather than once per purchase order.
    """
    rows = {r["po"]: dict(r) for r in session.run(ABOUT, pos=pos)}
    reach: dict[str, tuple] = {}
    out = []
    for po in pos:
        row = rows.get(po)
        if not row:
            out.append({"po": po, "found": False})
            continue
        group = row["vendorGroup"]
        if group and group not in reach:
            r = session.run(REACH, group=group).single()
            reach[group] = (r["contracts"], sorted(filter(None, r["departments"])))
        total, departments = reach.get(group, (0, []))
        out.append({"po": po, "found": True, "vendor": row["vendor"], "group": group,
                    "departments": sorted(filter(None, row["departments"])),
                    "types": sorted(filter(None, row["types"])),
                    "reachContracts": total, "reachDepartments": departments})
    return out


PROFILE = """
%s
OPTIONAL MATCH (dep:Department)-[:ASSIGNS_CONTRACT]->(c)
OPTIONAL MATCH (c)<-[:INCLUDED_IN_CONTRACT]-(r:ContractRecord)-[:HAS_CONTRACT_TYPE]->(t)
RETURN count(DISTINCT c) AS contracts,
       collect(DISTINCT dep.id) AS departments,
       collect(DISTINCT t.id) AS types,
       min(c.startDate) AS firstSeen, max(c.endDate) AS lastSeen
"""


def about_entity(session, entity_id: str) -> dict:
    """What an entity amounts to, as one row rather than a repeated aside.

    The same aggregate already reached the agent inside `about_contracts`,
    printed again on every purchase order as the vendor's reach. That is where
    it was ignored: asked which departments Bigane Paving had worked for, with
    all four named on every line it had been given, the agent summarised the
    contracts it happened to sample and answered two. Measured 23/9/2026, three
    runs of three, `temperature=0`.

    A set the caller must not recompute belongs in a tool of its own, whose
    whole output is that set -- decision 42, which puts the answer's list in the
    code, applied to a list that is not of contracts.
    """
    kind, _, value = entity_id.partition(":")
    row = session.run(PROFILE % ("MATCH " + CONTRACT_PATTERN[kind] % "a"), a=value).single()
    return {"id": entity_id, "contracts": row["contracts"],
            "departments": sorted(filter(None, row["departments"])),
            "types": sorted(filter(None, row["types"])),
            "first": row["firstSeen"], "last": row["lastSeen"]}


def neighbourhood(session, nodes: list[str], hops: int = 2,
                  cap: int = 100) -> tuple[str, dict]:
    """The neighbourhood of a set of nodes, grouped by relation and cut at `cap`.

    The rows come ordered by hops first and path count second, so `[:cap]` is
    not a neutral sample: it spends the budget on the nearest ring and drops the
    least connected neighbours. What was cut is returned alongside the text,
    because the text itself cannot show it -- see decision 37.
    """
    paths = session.run(COUNT_PATHS % hops, nodes=nodes).single()["n"]
    rows = [dict(r) for r in session.run(TRAVERSE % hops, nodes=nodes)]
    grouped: dict[str, list[str]] = {}
    for row in rows[:cap]:
        grouped.setdefault(f"{row['via']} ({row['label']})", []).append(str(row["name"]))
    text = "\n".join(f"{relation}: {', '.join(sorted(set(names))[:20])}"
                     for relation, names in grouped.items())
    dropped = rows[cap:]
    # What was cut, described by distance and by kind. Not by a path-count
    # threshold: the ordering is by hops first, so the last row kept can have
    # one path while a dropped row two rings out has twenty-three, and "cut
    # everything below N paths" would be false. Corrected 23/9/2026.
    size = {"kept": min(cap, len(rows)), "rows": len(rows), "paths": paths,
            "labels": sorted({r["label"] for r in dropped}),
            "hops": sorted({r["hops"] for r in dropped})}
    return text, size


def members_of(session, group: str) -> list[str]:
    """The element ids of a group's organizations, to start a traversal from."""
    row = session.run(MEMBERS, group=group).single()
    return row["nodes"] if row else []


# --- the text a model is shown -------------------------------------------


def contract_line(po: str, title: str, cap: int) -> str:
    """One contract per line, identifier labelled, title quoted.

    On 17/9/2026 the agent completed a three-step chain, received the right 22
    contracts, and answered with their titles. Titles repeat -- three different
    contracts are called `CDPH-MNTL-HLTH: PO 140746 ERIE NEIGHBORHOOD HOUSE` --
    and quote other purchase-order numbers in their own text, so the answer
    listed 22 lines from which a reader could identify 5. Written as `po: title`
    the two were easy to swap; labelled, they are not.
    """
    return f'purchase_order={po}  title="{" ".join(str(title or "").split())[:cap]}"'


def render_entities(rows: list[dict]) -> str:
    return "\n".join(f"{r['id']} | {r['label']} | {r['contracts']} contracts" for r in rows)


def render_contracts(rows: list[dict], entity_id: str, within: str | None,
                     limit: int = 50) -> str:
    both = f" that also belong to {within}" if within else ""
    if not rows:
        return f"no contracts of {entity_id}{both}"
    head = "\n".join(contract_line(r["po"], r["name"], 70) for r in rows[:limit])
    if len(rows) <= limit:
        return f"{len(rows)} contracts of {entity_id}{both}, complete list\n{head}"
    # Decision 37 asks for a cut list to say it was cut. On 17/9/2026 that was
    # not enough: told "... and 6818 more", the agent read 50 lines and concluded
    # a contract was absent. So the tool also says what the list cannot be used
    # for, and what to do instead.
    return (f"{len(rows)} contracts of {entity_id}{both}, showing {limit}\n{head}\n"
            f"... and {len(rows) - limit} more. THIS LIST IS INCOMPLETE: you cannot "
            f"conclude from it that a contract is absent. To find the contracts that "
            f"also meet a second condition, call contracts_of again with `within`.")


def render_entity(row: dict) -> str:
    years = ""
    if row["first"] and row["last"]:
        years = f", {str(row['first'])[:4]}-{str(row['last'])[:4]}"
    departments = "; ".join(row["departments"]) or "none recorded"
    text = (f"{row['id']}: {row['contracts']} contracts{years}\n"
            f"all {len(row['departments'])} departments: {departments}")
    if row["types"]:
        text += f"\ncontract types: {'; '.join(row['types'])}"
    return text


def render_about(rows: list[dict], issued: set[str] | None = None) -> str:
    lines = []
    for row in rows:
        if not row.get("found"):
            lines.append(f"{row['po']}: not in the graph")
            continue
        parts = []
        if row["vendor"]:
            total, departments = row["reachContracts"], row["reachDepartments"]
            if total > ENUMERATION:
                spread = f"{total:,} contracts -- use contracts_of for the list"
            else:
                spread = (f"{total} contracts across {len(departments)} departments: "
                          f"{', '.join(departments)}")
            parts.append(f"vendor {row['vendor']} (id vendor:{row['group']}; {spread})")
            if issued is not None and row["group"]:
                issued.add(f"vendor:{row['group']}")
        if row["departments"]:
            parts.append(f"department {', '.join(row['departments'])}")
        if row["types"]:
            parts.append(f"type {', '.join(row['types'])}")
        lines.append(f"{row['po']}: {'; '.join(parts) or 'nothing recorded'}")
    return "\n".join(lines)
