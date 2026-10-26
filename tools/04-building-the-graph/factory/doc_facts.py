"""What the documents say, as nodes and edges, each carrying the page it came from.

Runs after `factory.documents`, which puts the corpus itself in the graph. This
importer loads what was read *out of* the pages: the people, the modifications,
the subcontracting commitments, the compliance outcomes, and the disagreements
between a document and the record.

    python -m factory.doc_facts --backend neo4j --file manifest.csv \
        --base_path ./data/chicago/2022-2026/

Input is the extraction output beside the manifest -- `forms/`, `typed/` --
produced by `corpus/parse_forms.py` and `corpus/extract_typed.py`. This file
never reads a PDF and never calls a model.

=============================================================================
PROVENANCE IS NOT OPTIONAL HERE -- see DECISIONS #64
=============================================================================
Nothing loaded by this importer comes from a published CSV, so every node and
every edge says where it came from, in three ways that answer three different
questions:

  `source`      which extraction produced it: the eight DOC_* values on a
                PersonRecord name the form that carried the name, the same way
                OWNERS and EMPLOYEES name the file on the records already in
                the graph. The DOC_ prefix is what isolates all of it at once.
  `doc`, `page` the exact page, as `167067_r11` and `4`. Not the dataset: the
                line. From any edge a reader gets back to the PDF.
  `date`        when the document was filed, taken from the approval date of
                the revision it belongs to. 100% of the person-to-contract
                edges can be dated this way, which is what makes "who handled
                this contract in 2024" answerable.

One predicate finds everything this importer wrote:

    MATCH ()-[r]->() WHERE r.source = 'document' RETURN count(r)

And one edge makes the page reachable instead of merely recorded, for the
13,213 records that have a single page to point at:

    MATCH (n)-[:EXTRACTED_FROM]->(pg:Page) RETURN labels(n)[0], count(*)

=============================================================================
WHY PersonRecord AND NOT Person -- measured 21/10/2026
=============================================================================
The 10,891 people arrive as records, unresolved, and nothing writes
RECORD_RESOLVED_TO. The graph already separates the two layers for the licence
and employee files; documents get the same treatment, and the resolution is the
module 4 exercise rather than a step hidden in a loader.

It is a better exercise than resolution over the whole graph for three reasons
that the data, not the design, provides: the scale is 10,891 records instead of
358,511; 381 of the people already exist as records from the other datasets, so
there is a partial answer key to check against (the pattern of #22); and the
error types are varied and real -- 38.4% of the surface forms carry a courtesy
title, 13.2% a middle initial, and one person is written eight ways, including
`KENYA HARRJSON-BONNER` where OCR read I as J.

Organizations keep the label the graph already uses -- there is no
OrganizationRecord -- but they are new nodes under their own id namespace,
`contracts:org:doc:<slug>`, against the `contracts:<vendorId>` of the CSVs.
1,269 of them, and nothing points at an existing one. An earlier version of
this importer did point at them -- it matched the name written on the page
against the 210,740 organisations from the CSVs and hung
FILED_EDS_FOR and SUBCONTRACTS_FOR off whatever it found. That is entity
resolution, performed inside a loader, by a rule nobody declared and with no
record of what it decided. Two consequences made it indefensible rather than
merely untidy: 9 of the 98 subcontracting commitments lost their edge because
the prime's name did not match anything, and the 16 subcontractors whose name
*did* already exist kept a separate node anyway, so the graph was half resolved
in one direction and half in the other.

Now both endpoints of an edge between two document-named firms are nodes this
importer wrote, and the join to the rest of the entity layer is a declared step
with its own output. The gap is one query away from being visible, and closing
it is the module 4 exercise:

    MATCH (o:Organization) WHERE o.source = 'DOC_ORGANIZATION'
      AND NOT (o)-[:BELONGS_TO_ORG_GROUP]->() RETURN count(o)

What that exercise will find, measured 21/10/2026 outside the graph: 880 of the
1,269 carry a name that an organisation from the CSVs already carries exactly,
once case and punctuation are dropped; 229 more agree only on their first 12
characters (`Black Dog Petroleum` against `BLACK DOG PETROLEUM, LLC`); 160 match
nothing. So two thirds are a lookup, a fifth needs a decision, and an eighth are
firms the published data does not contain. `nameKey` is on the new nodes for the
exercise to start from, and deliberately not written onto the CSV ones.

The one join this importer does make is by identifier, not by name: a purchase
order number read off the page selects the Contract it names. That is a lookup,
and `po_in_text` disagreeing with the record is loaded as a claim rather than
silently resolved.
"""


def chi_doc_facts_importer_factory(base_importer_cls, backend: str):
    import csv
    import json
    import logging
    import re
    from collections import Counter
    from pathlib import Path

    # Decision 14: an identifier carries the namespace it belongs to.
    P = "contracts:personrec:"
    MOD = "contracts:mod:"
    REASON = "contracts:reason:"
    CERT = "contracts:cert:"
    CLAIM = "contracts:claim:"
    EV = "contracts:evidence:"
    AUDIT = "contracts:audit:"
    # The namespace is what keeps these apart from the 210,740 organisations
    # of the CSVs, whose ids are `contracts:<vendorId>`. Same label, new nodes.
    ORG = "contracts:org:doc:"

    # The six reason codes that are real. Measured 21/10/2026: these cover
    # 2,263 of the 2,444 requests; the other 94 distinct values are vendor
    # names the line pattern mistook for a code, and they are dropped rather
    # than loaded as codes nobody can interpret.
    REASON_CODES = {
        "TIME EXTENSION", "DOLLAR AMOUNT CHANGE", "VLI & TIME EXTENSION",
        "SCOPE CHANGE", "UNIT PRICE CHANGE", "COST REDUCTION",
    }

    def norm_person(name):
        """The grouping key. Deliberately crude, and not used to merge anything.

        First token plus last token, which is the key a reader reaches for
        first and which fails on this data: 38.4% of the forms start with
        `Mr.`/`Ms.` and 1.5% end with `Jr`, so `Mr. Aaron Royster Jr` and
        `Mr. Carl Porter Jr` share the key `mr jr`. It is kept as a property so
        the module 4 exercise can start by showing what it does.
        """
        t = re.sub(r"[^a-z ]", " ", (name or "").lower()).split()
        return f"{t[0]} {t[-1]}" if len(t) >= 2 else None

    def norm_org(name):
        """Truncated to 14: used to build ids, never to compare two names."""
        return re.sub(r"[^a-z0-9]", "", (name or "").lower())[:14]

    def slug_org(name):
        """The id fragment for an organisation record.

        24 characters and not the 14 of `norm_org`: two firms are named on one
        Schedule D page often enough that a short slug would collide and merge
        them by accident -- the very thing this importer stopped doing.
        """
        return re.sub(r"[^a-z0-9]", "", (name or "").lower())[:24]

    def norm_full(name):
        """Untruncated, for the comparison in claim_rows.

        Using the truncated form here weakens the containment test and invents
        disagreements: measured 21/10/2026 it reported 1,531 claims where the
        full form reports 1,170.
        """
        return re.sub(r"[^a-z0-9]", "", (name or "").lower())

    class ChicagoDocFactsImporter(base_importer_cls):
        def __init__(self):
            super().__init__()
            self.backend = backend

        # --- reading the extraction output -------------------------------

        @staticmethod
        def paths(manifest_file):
            base = Path(manifest_file).parent
            return base, base / "forms", base / "typed"

        @staticmethod
        def jsonl(path):
            if not path.exists():
                return
            for line in open(path):
                if line.strip():
                    yield json.loads(line)

        @staticmethod
        def revision_dates(manifest_file):
            """(po, revision) -> approval date, and po -> any date as a fallback."""
            by_rev, by_po = {}, {}
            with open(manifest_file) as f:
                for row in csv.DictReader(f):
                    d = row.get("approval_date") or None
                    by_rev[(row["po_number"], row["revision"])] = d
                    by_po.setdefault(row["po_number"], d)
            return by_rev, by_po

        @staticmethod
        def doc_urls(manifest_file):
            """doc stem -> viewer URL, the key documents.py joined revisions on."""
            out = {}
            with open(manifest_file) as f:
                for row in csv.DictReader(f):
                    out[f'{row["po_number"]}_r{row["revision"]}'] = row.get("pdf_url")
            return out

        def people_rows(self, manifest_file):
            """One record per extracted occurrence, with its role and its page.

            One per occurrence and not one per person: a record is what a source
            asserts, and the same person asserted by eight forms is eight
            records. Collapsing them here would do the resolution silently.
            """
            base, forms, typed = self.paths(manifest_file)
            by_rev, by_po = self.revision_dates(manifest_file)

            def emit(name, source, role, doc, page, po, rev, **extra):
                if not name or not norm_person(name):
                    return None
                return {
                    "id": f"{P}{source}:{doc}:{page}:{norm_org(name)}",
                    "fullName": " ".join(str(name).split()),
                    "nameKey": norm_person(name),
                    "source": source, "role": role or "",
                    "doc": doc, "page": page, "poNumber": po,
                    "date": by_rev.get((po, rev)) or by_po.get(po),
                    **{k: v for k, v in extra.items() if v},
                }

            for r in self.jsonl(forms / "modification_summary.jsonl"):
                if not r.get("contact_person"):
                    continue
                po, rev = r["doc_id"].split("_r")
                row = emit(r["contact_person"], "DOC_MODIFICATION", "modification contact",
                           r["doc_id"], r["page"], po, rev, side="city")
                if row:
                    yield row

            path = forms / "city_people_resolved.json"
            if path.exists():
                for x in json.load(open(path)):
                    src = "DOC_" + re.sub(r"[^A-Z]", "_", x["role"].upper())[:12].strip("_")
                    row = emit(x["name"], src, x["role"], f'{x["po_number"]}_r{x["revision"]}',
                               x["page"], x["po_number"], x["revision"], side="city",
                               email=x.get("email"), phone=x.get("phone"),
                               employeeNo=x.get("employee_no"))
                    if row:
                        yield row

            for r in self.jsonl(typed / "city_contact.jsonl"):
                if not r.get("filled"):
                    continue
                po, rev = r["doc_id"].split("_r")
                for p in (r.get("people") or []):
                    if not isinstance(p, dict) or not p.get("name"):
                        continue
                    city = str(p.get("side", "")).lower().startswith("cit")
                    row = emit(p["name"], "DOC_CITY_CONTACT" if city else "DOC_VENDOR_CONTACT",
                               p.get("role") or p.get("title") or "", r["doc_id"], r["page"],
                               po, rev, side="city" if city else "contractor",
                               title=p.get("title"), email=p.get("email"), phone=p.get("phone"))
                    if row:
                        yield row

            for r in self.jsonl(forms / "eds_certificate.jsonl"):
                if not r.get("filed_by") or len(str(r["filed_by"])) > 80:
                    continue
                po, rev = r["doc_id"].split("_r")
                row = emit(r["filed_by"], "DOC_EDS", r.get("filer_title") or "",
                           r["doc_id"], r["page"], po, rev, side="contractor",
                           title=r.get("filer_title"), edsNumber=r.get("eds_number"),
                           organization=r.get("disclosing_party"))
                if row:
                    yield row

        def modification_rows(self, manifest_file):
            base, forms, typed = self.paths(manifest_file)
            by_rev, by_po = self.revision_dates(manifest_file)
            urls = self.doc_urls(manifest_file)
            seen = set()
            for r in self.jsonl(forms / "modification_summary.jsonl"):
                po, rev = r["doc_id"].split("_r")
                for q in (r.get("requests") or []):
                    num = q.get("number")
                    if not num or num in seen:
                        continue
                    seen.add(num)
                    yield {
                        "id": f"{MOD}{num}", "number": num,
                        "reason": q.get("reason") if q.get("reason") in REASON_CODES else None,
                        "reasonRaw": q.get("reason"),
                        "amounts": r.get("amounts_on_page") or [],
                        "revision": r.get("revision"), "poNumber": po,
                        "url": urls.get(r["doc_id"]),
                        "doc": r["doc_id"], "page": r["page"],
                        "date": by_rev.get((po, rev)) or by_po.get(po),
                    }

        def subcontract_rows(self, manifest_file):
            base, forms, typed = self.paths(manifest_file)
            by_po = self.revision_dates(manifest_file)[1]
            path = typed / "subcontract_edges.json"
            if not path.exists():
                return
            for e in json.load(open(path)):
                doc, _, page = e["page"].partition("#")
                pg = int(page or 0)
                prime = e.get("prime_record") or e.get("prime_in_text")
                yield {
                    "subId": f'{ORG}{slug_org(e["sub"])}',
                    "subName": " ".join(e["sub"].split()),
                    # A firm does not subcontract to itself: on 4 of the 98 forms
                    # the two parties read as the same name, which is an
                    # extraction error, not a commitment. Dropping the id here
                    # keeps WORKS_ON and loses only SUBCONTRACTS_FOR.
                    "primeId": (f"{ORG}{slug_org(prime)}"
                                if slug_org(prime) and slug_org(prime) != slug_org(e["sub"])
                                else None),
                    "primeName": " ".join(prime.split()) if prime else None,
                    "amount": e.get("amount"), "percent": e.get("percent"),
                    "cert": e.get("cert"), "work": e.get("work"),
                    "poNumber": e["po"], "doc": doc, "page": pg,
                    "date": by_po.get(e["po"]),
                }

        def audit_rows(self, manifest_file):
            base, forms, typed = self.paths(manifest_file)
            for r in self.jsonl(typed / "compliance_audit.jsonl"):
                if not r.get("filled") or not r.get("goal_percent"):
                    continue
                yield {
                    "id": f'{AUDIT}{r["doc_id"]}:{r["page"]}',
                    "poNumber": r["po_number"], "prime": r.get("prime"),
                    "goal": r.get("goal_percent"), "credit": r.get("credit_percent"),
                    "award": r.get("award"), "totalPaid": r.get("total_paid"),
                    "status": r.get("status"), "progress": r.get("progress"),
                    "doc": r["doc_id"], "page": r["page"],
                }

        def claim_rows(self, manifest_file):
            """One claim per disagreement between a document and the record.

            Not a correction: neither side is overwritten. The department case
            is the clearest -- 2,435 contracts already have more than one
            department assigning them, up to six, and ASSIGNS_CONTRACT carries
            no date, so the graph holds the names and not the order. The claim
            is the assertion that two of those names are the same office in
            sequence; the evidence is the page that says so, on a dated
            revision.
            """
            base, forms, _ = self.paths(manifest_file)
            by_rev, by_po = self.revision_dates(manifest_file)
            record = {}
            with open(manifest_file) as f:
                for row in csv.DictReader(f):
                    record.setdefault(row["po_number"], row)

            fields = [
                ("department_in_text", "department", "department-lineage", "SUCCEEDED_BY"),
                ("vendor_in_text", "vendor_name", "same-organization", "SAME_AS"),
                ("spec_in_text", "spec_number", "specification-mismatch", None),
                ("po_in_text", "po_number", "contract-lineage", "SUPERSEDES"),
            ]
            # The EDS certificate names the contract and the declaring party, so
            # it carries the same three comparisons under different labels.
            alias = {"contract_in_text": "po_in_text", "disclosing_party": "vendor_in_text"}
            for name in ("contract_summary.jsonl", "modification_summary.jsonl",
                         "eds_certificate.jsonl"):
                for r in self.jsonl(forms / name):
                    # On the labels-then-values layout the purchase order was used
                    # to accept the pairing, so it is no longer independent
                    # evidence about the record: those rows are left out.
                    if r.get("_layout") == "labels_then_values":
                        continue
                    for src, dst in alias.items():
                        if r.get(src) and not r.get(dst):
                            r[dst] = r[src]
                    rec = record.get(str(r.get("po_number")))
                    if not rec:
                        continue
                    po, rev = r["doc_id"].split("_r")
                    for field, col, kind, edge in fields:
                        t, v = r.get(field), rec.get(col)
                        if not t or not v:
                            continue
                        a, b = norm_full(t), norm_full(v)
                        if not a or not b or a == b or a[:12] in b or b[:12] in a:
                            continue
                        yield {
                            "id": f'{CLAIM}{kind}:{r["doc_id"]}:{r["page"]}:{field}',
                            "kind": kind, "edgeType": edge,
                            "subject": " ".join(str(t).split()), "objects": [v],
                            "poNumber": po, "doc": r["doc_id"], "page": r["page"],
                            "date": by_rev.get((po, rev)) or by_po.get(po),
                            "evidenceId": f'{EV}{r["doc_id"]}:{r["page"]}:{field}',
                            "quote": f'{col}: {" ".join(str(t).split())}'[:300],
                        }

        def org_rows(self, manifest_file):
            """One node per distinct firm name read off a document.

            Not one per occurrence, which is how the people are loaded: a name
            in the entity layer is an entity, and measured 21/10/2026 the 4,301
            occurrences name 1,269 firms. The page a name came from lives on the
            edge, which carries `doc` and `page` for every occurrence, so
            nothing is lost by aggregating the node.

            Three roles feed it -- the party an EDS certificate discloses, the
            firm committing to subcontract, and the prime it commits to -- and
            `roles` keeps them, because 30 firms appear in more than one.
            `surfaceForms` keeps every spelling that collapsed into the node,
            which is 40 firms written more than one way: the slug is built on
            the first 24 characters of the normalised name, so `Black Dog
            Petroleum` and `Black Dog Petroleum, LLC` are one node while two
            genuinely different firms are not.
            """
            base, forms, typed = self.paths(manifest_file)
            by_rev, by_po = self.revision_dates(manifest_file)
            agg = {}

            def add(name, role, doc, page, po, rev=None):
                slug = slug_org(name)
                if not slug:
                    return
                e = agg.setdefault(slug, {
                    "id": f"{ORG}{slug}", "name": " ".join(str(name).split()),
                    "nameKey": norm_full(name)[:14], "source": "DOC_ORGANIZATION",
                    "roles": set(), "names": set(), "n": 0,
                    "firstDoc": doc, "firstPage": page,
                    "date": by_rev.get((po, rev)) or by_po.get(po),
                })
                e["roles"].add(role)
                e["names"].add(" ".join(str(name).split()))
                e["n"] += 1

            for r in self.jsonl(forms / "eds_certificate.jsonl"):
                if not r.get("disclosing_party") or len(str(r["disclosing_party"])) > 120:
                    continue
                po, rev = r["doc_id"].split("_r")
                add(r["disclosing_party"], "EDS disclosing party",
                    r["doc_id"], r["page"], po, rev)

            for r in self.subcontract_rows(manifest_file):
                add(r["subName"], "subcontractor", r["doc"], r["page"], r["poNumber"])
                if r["primeId"]:
                    add(r["primeName"], "prime on the form",
                        r["doc"], r["page"], r["poNumber"])

            for e in agg.values():
                yield {**e, "roles": sorted(e["roles"]), "names": sorted(e["names"])}

        # --- writing -----------------------------------------------------

        def set_constraints(self):
            for q in [
                f"CREATE CONSTRAINT doc_personrec_id IF NOT EXISTS FOR (n:PersonRecord) REQUIRE n.id IS UNIQUE",
                "CREATE CONSTRAINT modification_id IF NOT EXISTS FOR (n:Modification) REQUIRE n.id IS UNIQUE",
                "CREATE CONSTRAINT reason_code_id IF NOT EXISTS FOR (n:ReasonCode) REQUIRE n.id IS UNIQUE",
                "CREATE CONSTRAINT certification_id IF NOT EXISTS FOR (n:Certification) REQUIRE n.id IS UNIQUE",
                "CREATE CONSTRAINT claim_id IF NOT EXISTS FOR (n:Claim) REQUIRE n.id IS UNIQUE",
                "CREATE CONSTRAINT evidence_id IF NOT EXISTS FOR (n:Evidence) REQUIRE n.id IS UNIQUE",
                "CREATE CONSTRAINT audit_id IF NOT EXISTS FOR (n:ComplianceAudit) REQUIRE n.id IS UNIQUE",
                "CREATE INDEX org_name_key IF NOT EXISTS FOR (n:Organization) ON (n.nameKey)",
                "CREATE INDEX personrec_name_key IF NOT EXISTS FOR (n:PersonRecord) ON (n.nameKey)",
                "CREATE INDEX personrec_source IF NOT EXISTS FOR (n:PersonRecord) ON (n.source)",
            ]:
                try:
                    with self._driver.session(database=self._database) as s:
                        s.run(q)
                except Exception as exc:  # a constraint that already exists is not news
                    logging.debug("constraint: %s", exc)

        def import_people(self, manifest_file):
            query = """
            UNWIND $batch AS row
            MERGE (p:PersonRecord {id: row.id})
              SET p.fullName = row.fullName, p.nameKey = row.nameKey,
                  p.source = row.source, p.role = row.role, p.side = row.side,
                  p.title = row.title, p.email = row.email, p.phone = row.phone,
                  p.doc = row.doc, p.page = row.page, p.edsNumber = row.edsNumber
            WITH p, row
            OPTIONAL MATCH (c:Contract {id: row.poNumber})
            FOREACH (_ IN CASE WHEN c IS NULL OR row.side <> 'city' THEN [] ELSE [1] END |
              MERGE (p)-[a:ACTED_ON]->(c)
                SET a.role = row.role, a.date = row.date, a.doc = row.doc,
                    a.page = row.page, a.source = 'document')
            """
            self.batch_store(query, self.people_rows(manifest_file))

        def import_orgs(self, manifest_file):
            """The organisations named in the documents, as new Organization nodes.

            The label is the one the graph already uses; the id namespace is
            not. Nothing here is merged into an existing organisation and
            nothing gets a BELONGS_TO_ORG_GROUP: both are the output of a
            resolution step, and a loader that wrote them would be deciding
            what that step is for.
            """
            query = """
            UNWIND $batch AS row
            MERGE (o:Organization {id: row.id})
              SET o.name = row.name, o.nameKey = row.nameKey, o.source = row.source,
                  o.roles = row.roles, o.surfaceForms = row.names,
                  o.occurrences = row.n, o.doc = row.firstDoc, o.page = row.firstPage
            """
            self.batch_store(query, self.org_rows(manifest_file))

        def import_org_contracts(self, manifest_file):
            """DISCLOSED_FOR: this firm's EDS was filed in this contract's file.

            One edge per certificate and not per firm, so the page is the
            certificate's own. The subcontractors reach their contract through
            WORKS_ON instead, which also carries the committed amount.
            """
            query = """
            UNWIND $batch AS row
            MATCH (o:Organization {id: row.orgId})
            MATCH (c:Contract {id: row.poNumber})
            MERGE (o)-[d:DISCLOSED_FOR]->(c)
              SET d.date = row.date, d.doc = row.doc, d.page = row.page,
                  d.source = 'document'
            """
            base, forms, _ = self.paths(manifest_file)
            by_rev, by_po = self.revision_dates(manifest_file)

            def rows():
                for r in self.jsonl(forms / "eds_certificate.jsonl"):
                    name = r.get("disclosing_party")
                    if not name or len(str(name)) > 120 or not slug_org(name):
                        continue
                    po, rev = r["doc_id"].split("_r")
                    yield {"orgId": f"{ORG}{slug_org(name)}", "poNumber": po,
                           "doc": r["doc_id"], "page": r["page"],
                           "date": by_rev.get((po, rev)) or by_po.get(po)}

            self.batch_store(query, rows())

        def import_eds_links(self, manifest_file):
            """FILED_EDS_FOR, from the filer's record to the declaring firm.

            The firm is the node `import_orgs` wrote from the same certificate,
            found by the slug of the name printed on it. Pointing the edge at an
            Organization from the CSVs would mean matching that name against
            theirs, which is the step this importer leaves undone.
            """
            query = """
            UNWIND $batch AS row
            MATCH (p:PersonRecord {id: row.id})
            MATCH (o:Organization {id: row.orgId})  // a DOC_ node, never a CSV one
            MERGE (p)-[f:FILED_EDS_FOR]->(o)
              SET f.edsNumber = row.edsNumber, f.date = row.date, f.doc = row.doc,
                  f.page = row.page, f.source = 'document'
            """

            def rows():
                for r in self.people_rows(manifest_file):
                    org = r.get("organization")
                    if r["source"] != "DOC_EDS" or not org or len(str(org)) > 120:
                        continue
                    if not slug_org(org):
                        continue
                    yield {**r, "orgId": f"{ORG}{slug_org(org)}"}

            self.batch_store(query, rows())

        def import_modifications(self, manifest_file):
            query = """
            UNWIND $batch AS row
            MERGE (m:Modification {id: row.id})
              SET m.number = row.number, m.reason = row.reason,
                  m.reasonRaw = row.reasonRaw, m.amounts = row.amounts,
                  m.date = row.date, m.doc = row.doc, m.page = row.page,
                  m.source = 'DOC_MODIFICATION'
            WITH m, row
            FOREACH (_ IN CASE WHEN row.reason IS NULL THEN [] ELSE [1] END |
              MERGE (rc:ReasonCode {id: 'contracts:reason:' + row.reason})
                SET rc.name = row.reason, rc.source = 'DOC_MODIFICATION'
              MERGE (m)-[hr:HAS_REASON]->(rc)
                SET hr.source = 'document', hr.doc = row.doc, hr.page = row.page)
            WITH m, row
            OPTIONAL MATCH (r:ContractRecord {pdfFile: row.url})
            FOREACH (_ IN CASE WHEN r IS NULL THEN [] ELSE [1] END |
              MERGE (m)-[x:MODIFIES]->(r)
                SET x.source = 'document', x.doc = row.doc, x.page = row.page,
                    x.date = row.date)
            WITH m, row
            OPTIONAL MATCH (c:Contract {id: row.poNumber})
            FOREACH (_ IN CASE WHEN c IS NULL THEN [] ELSE [1] END |
              MERGE (m)-[y:MODIFIES_CONTRACT]->(c)
                SET y.source = 'document', y.doc = row.doc, y.page = row.page)
            """
            self.batch_store(query, self.modification_rows(manifest_file))

        def import_subcontracts(self, manifest_file):
            """The commitment, between two records read off the same page.

            Both nodes were already written by `import_orgs`, so this matches
            them by id and only adds the edges. The prime is the one the record
            names, with the text version kept as a cross-check: measured
            21/10/2026 they agree on 51 of the 98 commitments.
            """
            query = """
            UNWIND $batch AS row
            MATCH (s:Organization {id: row.subId})
            WITH s, row
            OPTIONAL MATCH (c:Contract {id: row.poNumber})
            FOREACH (_ IN CASE WHEN c IS NULL THEN [] ELSE [1] END |
              MERGE (s)-[w:WORKS_ON]->(c)
                SET w.source = 'document', w.doc = row.doc, w.page = row.page,
                    w.amount = row.amount, w.percent = row.percent, w.work = row.work,
                    w.date = row.date)
            WITH s, row
            OPTIONAL MATCH (p:Organization {id: row.primeId})
            FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END |
              MERGE (s)-[sf:SUBCONTRACTS_FOR]->(p)
                SET sf.source = 'document', sf.doc = row.doc, sf.page = row.page,
                    sf.amount = row.amount, sf.percent = row.percent,
                    sf.poNumber = row.poNumber, sf.date = row.date)
            WITH s, row
            FOREACH (_ IN CASE WHEN row.cert IS NULL THEN [] ELSE [1] END |
              MERGE (ct:Certification {id: 'contracts:cert:' + row.cert})
                SET ct.name = row.cert, ct.source = 'DOC_SUBCONTRACTOR'
              MERGE (s)-[h:HOLDS_CERTIFICATION]->(ct)
                SET h.source = 'document', h.doc = row.doc, h.page = row.page)
            """
            self.batch_store(query, self.subcontract_rows(manifest_file))

        def import_provenance(self, manifest_file):
            """EXTRACTED_FROM: the record, and the page it was read off.

            `doc` and `page` are already on every node and every edge, and the
            page id is built from those two values, so this edge adds no
            information -- it makes the information traversable. Three things it
            buys, measured 21/10/2026:

            A query stops lying. Joining on a rebuilt id (`'contracts:page:' +
            n.doc + '_p' + toString(n.page)`) returns zero rows when the
            convention changes, and zero rows reads like an empty result rather
            than a broken query. An edge that is missing is a count that does
            not add up.

            Module 5 needs exactly this path: page -> vector -> record ->
            contract. Without the edge the retrieval has to assemble strings.

            And it makes `Evidence-[:CITES]->Page` stop being a special case:
            all 13,213 document-derived records now reach their page the same
            way the 1,185 claims already did.

            Organizations are left out on purpose: `import_orgs` aggregates them
            by name, so a firm named on nine pages has no single page to point
            at. Its pages are on its edges, which all carry `doc` and `page`.
            """
            PAGE = "'contracts:page:' + row.doc + '_p' + toString(row.page)"
            for label, rows in (("PersonRecord", self.people_rows(manifest_file)),
                                ("Modification", self.modification_rows(manifest_file)),
                                ("ComplianceAudit", self.audit_rows(manifest_file))):
                query = f"""
                UNWIND $batch AS row
                MATCH (n:{label} {{id: row.id}})
                MATCH (pg:Page {{id: {PAGE}}})
                MERGE (n)-[e:EXTRACTED_FROM]->(pg)
                  SET e.source = 'document', e.doc = row.doc, e.page = row.page
                """
                self.batch_store(query, rows)

        def import_audits(self, manifest_file):
            query = """
            UNWIND $batch AS row
            MERGE (a:ComplianceAudit {id: row.id})
              SET a.goalPercent = row.goal, a.creditPercent = row.credit,
                  a.award = row.award, a.totalPaid = row.totalPaid,
                  a.status = row.status, a.progress = row.progress,
                  a.prime = row.prime, a.doc = row.doc, a.page = row.page,
                  a.source = 'DOC_B2GNOW'
            WITH a, row
            OPTIONAL MATCH (c:Contract {id: row.poNumber})
            FOREACH (_ IN CASE WHEN c IS NULL THEN [] ELSE [1] END |
              MERGE (c)-[r:HAS_COMPLIANCE_AUDIT]->(a)
                SET r.source = 'document', r.doc = row.doc, r.page = row.page)
            """
            self.batch_store(query, self.audit_rows(manifest_file))

        def import_claims(self, manifest_file):
            """Claim plus Evidence, attached to the nodes the claim is about.

            Decision 20: an edge cannot be the target of another edge, so a
            claim about one hangs off both of its endpoints. Here the second
            endpoint is matched by name, and a claim whose other side is not in
            the graph still lands -- with one ABOUT instead of two.
            """
            query = """
            UNWIND $batch AS row
            MERGE (cl:Claim {id: row.id})
              SET cl.kind = row.kind, cl.edgeType = row.edgeType,
                  cl.subject = row.subject, cl.objects = row.objects,
                  cl.date = row.date, cl.doc = row.doc, cl.page = row.page,
                  cl.source = 'document'
            MERGE (ev:Evidence {id: row.evidenceId})
              SET ev.kind = 'document', ev.source = row.doc + '#' + toString(row.page),
                  ev.quote = row.quote, ev.learnedOn = date()
            MERGE (ev)-[:SUPPORTS]->(cl)
            WITH cl, row
            OPTIONAL MATCH (p:Page {id: 'contracts:page:' + row.doc + '_p' + toString(row.page)})
            FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END |
              MERGE (ev2:Evidence {id: row.evidenceId})
              MERGE (ev2)-[:CITES]->(p))
            WITH cl, row
            OPTIONAL MATCH (c:Contract {id: row.poNumber})
            FOREACH (_ IN CASE WHEN c IS NULL THEN [] ELSE [1] END |
              MERGE (cl)-[:ABOUT]->(c))
            """
            self.batch_store(query, self.claim_rows(manifest_file))

        def report(self):
            q = """
            CALL () { MATCH (n:PersonRecord) WHERE n.source STARTS WITH 'DOC_'
                      RETURN count(n) AS personRecords }
            CALL () { MATCH (n:Modification) RETURN count(n) AS modifications }
            CALL () { MATCH (n:Claim) RETURN count(n) AS claims }
            CALL () { MATCH (n:ComplianceAudit) RETURN count(n) AS audits }
            CALL () { MATCH (o:Organization) WHERE o.source = 'DOC_ORGANIZATION'
                      RETURN count(o) AS orgsFromDocuments }
            CALL () { MATCH (o:Organization) WHERE o.source = 'DOC_ORGANIZATION'
                        AND NOT (o)-[:BELONGS_TO_ORG_GROUP]->()
                      RETURN count(o) AS orgsWithoutGroup }
            CALL () { MATCH ()-[r]->() WHERE r.source = 'document'
                      RETURN count(r) AS edgesFromDocuments }
            CALL () { MATCH ()-[r:EXTRACTED_FROM]->(:Page)
                      RETURN count(r) AS recordsLinkedToTheirPage }
            RETURN personRecords, orgsFromDocuments, orgsWithoutGroup, modifications,
                   claims, audits, edgesFromDocuments, recordsLinkedToTheirPage
            """
            with self._driver.session(database=self._database) as s:
                row = s.run(q).single()
            print("\nloaded from documents:")
            for k, v in row.items():
                print(f"  {v:>9,}  {k}")
            return row

        def import_data(self, manifest_file):
            logging.info("Constraints and indexes...")
            self.set_constraints()
            logging.info("People, as records, with their role on the contract...")
            self.import_people(manifest_file)
            logging.info("Organisations named in the documents, as records...")
            self.import_orgs(manifest_file)
            logging.info("EDS filer to declaring organisation...")
            self.import_eds_links(manifest_file)
            self.import_org_contracts(manifest_file)
            logging.info("Modifications and their reason codes...")
            self.import_modifications(manifest_file)
            logging.info("Subcontracting commitments...")
            self.import_subcontracts(manifest_file)
            logging.info("Compliance outcomes...")
            self.import_audits(manifest_file)
            logging.info("Claims and evidence for the disagreements...")
            self.import_claims(manifest_file)
            logging.info("The page each record was read off...")
            self.import_provenance(manifest_file)
            self.report()

    return ChicagoDocFactsImporter


if __name__ == '__main__':
    from util.cli_entry import run_backend_importer

    run_backend_importer(
        chi_doc_facts_importer_factory,
        description="Load what the documents say: people, modifications, "
                    "subcontracts, compliance outcomes, and the disagreements.",
        file_help="The corpus manifest. The extraction output is read from "
                  "forms/ and typed/ beside it.",
        default_base_path="./data/chicago/",
    )
