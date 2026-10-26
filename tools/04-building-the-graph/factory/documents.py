"""The contract PDFs, as text, joined to the revision that filed them.

The last step of the corpus pipeline described in this folder's README, and the one
that makes the module 5 comparison possible: with the pages in the graph, the
same question can be answered from the structured facts, from the document
text, or from both -- and the two can disagree, which is the point.

The join lands on ContractRecord, not on Contract. A purchase order is not a
unique document: each revision is filed separately and carries its own file, and
PO 27019 alone has seven. Attaching the text to the order would merge seven
different documents onto one node and lose which revision said what, the same
distinction decision 8 draws for the contract type.

The join key is the viewer URL the manifest already shares with
`ContractRecord.pdfFile`. Measured 17/8: 120 of 120 manifest rows match exactly
one record, so no fuzzy matching is needed here and none is done.

Input is `corpus_manifest.csv` plus the extracted text in `corpus/`, both under
`data/chicago/`. The PDFs themselves are never read by this importer and never
enter git -- only the PII-filtered text does.
"""


def chi_documents_importer_factory(base_importer_cls, backend: str):
    import csv
    import json
    import logging
    from pathlib import Path

    # Decision 14: an identifier carries the namespace it belongs to, so a
    # document id cannot collide with a licence or an organisation id.
    DOC_PREFIX = "contracts:doc:"
    PAGE_PREFIX = "contracts:page:"

    class ChicagoDocumentsImporter(base_importer_cls):
        def __init__(self):
            super().__init__()
            self.backend = backend

        @staticmethod
        def corpus_dir(manifest_file):
            return Path(manifest_file).parent / "corpus"

        @staticmethod
        def collection_name(manifest_file):
            """Which collection a document came from, written on the node.

            A35 says the August stratified sample and the 2022-2026 census
            cannot be merged without losing every frequency. A Document merges
            on its id, so once both manifests are loaded the node itself says
            nothing about which sampling pulled it. Measured 21/10/2026, after
            loading both: 1,487 documents and 44,629 pages belong to both
            collections, and their provenance was not recoverable from the
            graph -- only from the two CSVs outside it.

            The manifest path is the label because the manifest is the thing
            that differs. The property is a list: a document really can belong
            to two samplings.
            """
            path = Path(manifest_file)
            return path.name if path.parent.name == "chicago" else f"{path.parent.name}/{path.name}"

        @staticmethod
        def doc_id(po_number, revision):
            return f"{DOC_PREFIX}{po_number}_r{revision}"

        @staticmethod
        def get_csv_size(manifest_file, encoding="utf-8"):
            with open(manifest_file, encoding=encoding) as f:
                return sum(1 for _ in csv.DictReader(f))

        @staticmethod
        def get_rows(manifest_file, encoding="utf-8"):
            extracted = {
                path.stem
                for path in ChicagoDocumentsImporter.corpus_dir(manifest_file).glob("*.jsonl")
                if not path.stem.startswith("_")  # _extraction_report and friends
            }
            with open(manifest_file, encoding=encoding) as f:
                for row in csv.DictReader(f):
                    stem = f"{row['po_number']}_r{row['revision']}"
                    yield {
                        "id": ChicagoDocumentsImporter.doc_id(row["po_number"], row["revision"]),
                        "url": row["pdf_url"],
                        "poNumber": row["po_number"],
                        "revision": int(row["revision"]),
                        "hasTextLayer": stem in extracted,
                        "collection": ChicagoDocumentsImporter.collection_name(manifest_file),
                    }

        @staticmethod
        def get_pages(manifest_file):
            collection = ChicagoDocumentsImporter.collection_name(manifest_file)
            for path in sorted(ChicagoDocumentsImporter.corpus_dir(manifest_file).glob("*.jsonl")):
                if path.stem.startswith("_"):
                    continue
                for line in path.read_text().splitlines():
                    if not line.strip():
                        continue
                    page = json.loads(line)
                    yield {
                        "id": f"{PAGE_PREFIX}{path.stem}_p{page['page']}",
                        "documentId": DOC_PREFIX + path.stem,
                        "page": page["page"],
                        "text": page.get("text", ""),
                        "nChars": page.get("n_chars", 0),
                        "sha256": page.get("sha256"),
                        "flags": page.get("flags", []),
                        "collection": collection,
                    }

        @staticmethod
        def get_withheld_pages(manifest_file):
            """Yield the pages the PII filter kept out of the corpus.

            Without the text: the extractor never wrote it to disk. What is
            carried is why the page was held back, which makes the filter's
            behaviour queryable.
            """
            report = ChicagoDocumentsImporter.corpus_dir(manifest_file) / "_extraction_report.json"
            if not report.exists():
                return
            for entry in json.loads(report.read_text()):
                doc_id = entry.get("doc_id")
                for excl in entry.get("pii_exclusions") or []:
                    signals = excl.get("signals") or {}
                    yield {
                        "id": f"{PAGE_PREFIX}{doc_id}_p{excl['page']}",
                        "documentId": DOC_PREFIX + doc_id,
                        "page": excl["page"],
                        "piiScore": excl.get("score"),
                        "piiReasons": excl.get("reasons") or [],
                        "personalEmails": signals.get("personal_emails", 0),
                        "phones": signals.get("phones", 0),
                        "streetAddresses": signals.get("street_addresses", 0),
                        "residentialMarkers": signals.get("residential_markers", 0),
                        "orgMarkers": signals.get("org_markers", 0),
                        "collection": ChicagoDocumentsImporter.collection_name(manifest_file),
                    }

        def import_withheld_pages(self, manifest_file):
            """Record the withheld pages as Page nodes carrying no text.

            They hang off the same HAS_PAGE relationship; `withheld` tells
            them apart, and `text` is absent rather than empty so that a naive
            concatenation cannot pick them up.

            Counting (:Document)-[:HAS_PAGE]->(:Page) now returns these too. A
            count of the corpus needs `WHERE p.text IS NOT NULL`, and one that
            omits it comes out larger with nothing to say so.
            """
            query = """
                UNWIND $batch AS row
                MATCH (d:Document {id: row.documentId})
                MERGE (p:Page {id: row.id})
                  SET p.page = row.page,
                      p.withheld = true,
                      p.piiScore = row.piiScore,
                      p.piiReasons = row.piiReasons,
                      p.personalEmails = row.personalEmails,
                      p.phones = row.phones,
                      p.streetAddresses = row.streetAddresses,
                      p.residentialMarkers = row.residentialMarkers,
                      p.orgMarkers = row.orgMarkers,
                      p.collections = CASE WHEN row.collection IN coalesce(p.collections, []) THEN p.collections ELSE coalesce(p.collections, []) + row.collection END
                MERGE (d)-[:HAS_PAGE]->(p)
            """
            self.batch_store(query, self.get_withheld_pages(manifest_file))

        def set_constraints(self):
            queries = [
                "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (node:Document) REQUIRE node.id IS UNIQUE",
                "CREATE CONSTRAINT page_id IF NOT EXISTS FOR (node:Page) REQUIRE node.id IS UNIQUE",
                "CREATE INDEX document_po_number IF NOT EXISTS FOR (node:Document) ON (node.poNumber)",
            ]
            for query in queries:
                with self._driver.session(database=self._database) as session:
                    session.run(query)

        def import_documents(self, manifest_file):
            """Create one Document per manifest row and hang it off its revision.

            A document with no extractable text still becomes a node, so that
            "the graph knows this, the documents do not" is something to select
            on rather than an absence nobody can see.

            Fails silently when the URL does not match: the MERGE creates the
            Document, the MATCH finds no record, and no error is raised. That is
            what `report_orphans` is for.
            """
            query = """
                UNWIND $batch AS row
                MERGE (d:Document {id: row.id})
                  SET d.url = row.url,
                      d.poNumber = row.poNumber,
                      d.revision = row.revision,
                      d.hasTextLayer = row.hasTextLayer,
                      d.source = 'CONTRACTS',
                      d.collections = CASE WHEN row.collection IN coalesce(d.collections, []) THEN d.collections ELSE coalesce(d.collections, []) + row.collection END
                WITH d, row
                // The viewer URL is the join key: the manifest and the record
                // hold the same string. A revision that never had a document
                // has no pdfFile, so it is skipped here rather than matched
                // loosely on the purchase order.
                MATCH (r:ContractRecord {pdfFile: row.url})
                MERGE (r)-[:HAS_DOCUMENT]->(d)
            """
            size = self.get_csv_size(manifest_file)
            self.batch_store(query, self.get_rows(manifest_file), size)

        def import_pages(self, manifest_file):
            """Store one Page per extracted page, in document order.

            Pages are kept whole. The page is the unit the PII filter
            reviewed, which is what makes a stored page traceable back to a
            human decision.

            Fails silently when the Document is missing: the MATCH drops the
            page and reports nothing. That can happen when the steps are run
            separately rather than through import_data.
            """
            query = """
                UNWIND $batch AS row
                MATCH (d:Document {id: row.documentId})
                MERGE (p:Page {id: row.id})
                  SET p.page = row.page,
                      p.withheld = false,
                      p.text = row.text,
                      p.nChars = row.nChars,
                      p.sha256 = row.sha256,
                      p.flags = row.flags,
                      p.collections = CASE WHEN row.collection IN coalesce(p.collections, []) THEN p.collections ELSE coalesce(p.collections, []) + row.collection END
                MERGE (d)-[:HAS_PAGE]->(p)
            """
            self.batch_store(query, self.get_pages(manifest_file))

        def report_orphans(self):
            """Count the documents that reached no revision, and say so loudly.

            The join in import_documents cannot fail with an error, only with an
            absence, and an absence at the end of a long load scrolls past. This
            is the same reason batch_store prints its failures at the end rather
            than raising.
            """
            query = """
                MATCH (d:Document)
                WHERE NOT (d)<-[:HAS_DOCUMENT]-(:ContractRecord)
                RETURN count(d) AS orphans
            """
            with self._driver.session(database=self._database) as session:
                orphans = session.run(query).single()["orphans"]
            if orphans:
                print(f"\n*** {orphans} document(s) matched no ContractRecord "
                      f"and are attached to nothing. ***")
                print("    The manifest and the graph disagree on pdfFile: "
                      "check that both were built from the same extract.")
            return orphans

        def import_data(self, manifest_file):
            logging.info("Loading constraints and indexes...")
            self.set_constraints()

            logging.info("Loading documents...")
            self.import_documents(manifest_file)

            logging.info("Loading pages...")
            self.import_pages(manifest_file)

            logging.info("Loading the pages the PII filter withheld...")
            self.import_withheld_pages(manifest_file)

            logging.info("Checking that every document reached a revision...")
            self.report_orphans()

    return ChicagoDocumentsImporter


if __name__ == '__main__':
    from util.cli_entry import run_backend_importer

    run_backend_importer(
        chi_documents_importer_factory,
        description="Load the extracted contract text as Document and Page nodes.",
        file_help="The corpus manifest, corpus_manifest.csv. The extracted text is read "
                  "from the corpus/ directory beside it.",
        default_base_path="./data/chicago/",
    )
