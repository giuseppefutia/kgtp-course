"""Business Owners: one PersonRecord per owner, plus a pointer to their firm.

Owners is the only source that already provides first, middle and last name as
separate columns; Employees packs them into a single field and splits them
itself. The layouts differ, the canonical name must not -- see factory/naming.py.

The link to the firm is written here as a property and not as an edge: the
Organization does not exist yet at this point. licenses.py creates it from the
same account number and draws the edge afterwards, which is why the two files
must build the identifier the same way.
"""

from factory.naming import with_canonical_name


def chi_people_importer_factory(base_importer_cls, backend: str):
    import logging

    class ChicagoPeopleImporter(base_importer_cls):
        def __init__(self):
            super().__init__()
            self.backend = backend

        @staticmethod
        def get_csv_size(owners_file, encoding="utf-8"):
            return sum(1 for _ in ChicagoPeopleImporter.get_rows(owners_file))

        @staticmethod
        def get_rows(owners_file):
            import numpy as np
            import pandas as pd
            owners = pd.read_csv(owners_file, low_memory=False)
            owners['DATA_SOURCE'] = "OWNERS"
            owners['RECORD_TYPE'] = "PERSON"  # written, never read by any query
            if 'RECORD_ID' not in owners:
                # TODO(A10): positional id. See licenses.py get_rows() for why
                # the offsets keep the sources apart by margin rather than by
                # construction.
                owners.insert(0, 'RECORD_ID', range(3000000, 3000000 + len(owners)))
            owners.replace({np.nan: None}, inplace=True)
            for _, row in owners.iterrows():
                yield row.to_dict()

        def set_constraints(self):
            # The same block, minus the Department constraint, is repeated in
            # employees.py: both sources write PersonRecord, and whichever runs
            # first has to leave behind the indexes the other one needs. Two
            # copies that must agree. If one gains an index and the other does
            # not, the load still succeeds -- it just gets slower, which is the
            # kind of divergence nobody notices until it is measured.
            queries = [
                "CREATE CONSTRAINT person_id IF NOT EXISTS FOR (node:Person) REQUIRE node.clusterId IS UNIQUE",
                "CREATE CONSTRAINT person_record_id IF NOT EXISTS FOR (node:PersonRecord) REQUIRE node.id IS UNIQUE",
                # clusterKey is what create_connections_to_clusters matches on.
                # Without this index that MATCH scans every PersonRecord for
                # every cluster in every batch -- measured, it turns a two-minute
                # step into a thirty-minute one.
                "CREATE INDEX person_record_cluster_key IF NOT EXISTS FOR (node:PersonRecord) ON (node.clusterKey)",
                "CREATE INDEX person_record_wcc IF NOT EXISTS FOR (node:PersonRecord) ON (node.wccCommunity)",
                "CREATE INDEX person_record_employer_id IF NOT EXISTS FOR (node:PersonRecord) ON (node.employerId)",
                "CREATE FULLTEXT INDEX person_record_fullName IF NOT EXISTS FOR (node:PersonRecord) ON EACH [node.fullName]"
            ]
            for query in queries:
                with self._driver.session(database=self._database) as session:
                    session.run(query)

        def import_people_records(self, owners_file):
            """Write one PersonRecord per owner row.

            fullName is the key entity resolution blocks on, so it comes from
            the shared expression in factory/naming.py instead of a local copy:
            two sources that normalise names differently never match each other,
            and the failure is silent -- fewer pairs, no error, nothing in the
            output saying anything went wrong.

            employerId carries the `licenses:` prefix required by decision 14.
            The prefix is part of the identifier, not decoration: three account
            numbers are also contract vendor ids, so without it a MATCH would
            join the wrong firm and still return rows.
            """
            # TODO(A8): this query reads the natural-person columns only.
            # Measured 14/8: 10,117 rows of 329,934 have no first and no last
            # name because the owner is a company, named in `Legal Entity Owner`
            # -- Marsh & McLennan holding Mercer, ROPRO US holding RREEF. They
            # still become PersonRecords, nameless ones, which the resolver then
            # drops. What is lost with them is ten thousand company-to-company
            # ownership edges, which is where indirect control would be visible.
            import_people_records_query = with_canonical_name(
                """
            UNWIND $batch as item
            MERGE (n:PersonRecord {id: item.RECORD_ID})
            SET n.firstName = coalesce(item.`Owner First Name`, NULL)
            SET n.lastName = coalesce(item.`Owner Last Name`, NULL)
            SET n.middleName = coalesce(item.`Owner Middle Initial`, NULL)
            SET n.fullName = __CANONICAL_NAME__
            SET n.source = item.DATA_SOURCE
            SET n.employerId = 'licenses:' + toString(item.`Account Number`)
            SET n.title = item.Title
            """,
                "item.`Owner First Name`",
                "item.`Owner Middle Initial`",
                "item.`Owner Last Name`",
            )
            size = self.get_csv_size(owners_file)
            self.batch_store(import_people_records_query, self.get_rows(owners_file), size=size)
        
        def import_data(self, owners_file):
            logging.info("Loading constraints and indexes for person records and entities...")
            self.set_constraints()

            logging.info("Loading person record nodes...")
            self.import_people_records(owners_file)

    return ChicagoPeopleImporter

if __name__ == '__main__':
    from util.cli_entry import run_backend_importer

    run_backend_importer(
        chi_people_importer_factory,
        description="Run Chicago People Importer with selected backend.",
        file_help="Path to the Business Owners CSV file",
        default_base_path="./data/"
    )