"""Business licences: the largest source, and the one that joins the islands.

1,203,437 rows, roughly one per licence term rather than one per business, so
the same account number recurs hundreds of times. Everything about this file
follows from that: Organization is built by accumulating sets across repeats,
and every pass over the CSV costs real minutes.

This is also the only importer that touches nodes it did not create. Its last
step draws WORKS_FOR_ORG from the Person entities built by people_cluster, so
it has an ordering dependency the others do not have -- see connect_people_to_org.
"""


def chi_licenses_importer_factory(base_importer_cls, backend: str):
    import logging

    class ChicagoLicensesImporter(base_importer_cls):
        def __init__(self):
            super().__init__()
            self.backend = backend

        @staticmethod
        def get_csv_size(licenses_file, encoding="utf-8"):
            return sum(1 for _ in ChicagoLicensesImporter.get_rows(licenses_file))

        @staticmethod
        def get_rows(licenses_file):
            import pandas as pd
            import numpy as np
            licenses = pd.read_csv(licenses_file, low_memory=False)
            licenses['DATA_SOURCE'] = "LICENSES"
            licenses['RECORD_TYPE'] = "LICENSE"  # written, never read by any query
            if 'RECORD_ID' not in licenses:
                # TODO(A10): RECORD_ID is the position of the row in the file,
                # not an identifier the source gave us, and the offsets that
                # keep the four sources apart are margins rather than
                # guarantees: licences run 1,000,000 to 2,203,437 and owners
                # start at 3,000,000, so 60% of the gap is already spent, by the
                # source that grows fastest. When it is crossed, MERGE
                # (n:PersonRecord {id: ...}) overwrites another source's record
                # and reports nothing.
                #
                # This is exactly what decision 14 rejected for Organization
                # ids: impossible by construction beats verified absent. The fix
                # is a source prefix, not a larger offset.
                #
                # Second consequence, independent of collisions: the id is not
                # stable across downloads. If the portal inserts a row, every id
                # after it shifts, and re-importing silently rewrites records
                # with someone else's data.
                licenses.insert(0, 'RECORD_ID', range(1000000, 1000000 + len(licenses)))
            licenses.replace({np.nan: None}, inplace=True)
            for _, row in licenses.iterrows():
                yield row.to_dict()

        def set_constraints(self):
            queries = [
                "CREATE CONSTRAINT license_record_id IF NOT EXISTS FOR (node:LicenseRecord) REQUIRE node.id IS UNIQUE",
                "CREATE CONSTRAINT license_type_id IF NOT EXISTS FOR (node:LicenseType) REQUIRE node.id IS UNIQUE",
                "CREATE CONSTRAINT organization_id IF NOT EXISTS FOR (node:Organization) REQUIRE node.id IS UNIQUE",
                "CREATE CONSTRAINT address_id IF NOT EXISTS FOR (node:Address) REQUIRE node.id IS UNIQUE",
                "CREATE FULLTEXT INDEX organization_name IF NOT EXISTS FOR (node:Organization) ON EACH [node.name]",
                "CREATE INDEX organization_component_id IF NOT EXISTS FOR (node:Organization) ON (node.componentId)",
                "CREATE INDEX organization_group_cluster_id IF NOT EXISTS FOR (node:OrganizationGroup) ON (node.clusterId)"
            ]
            for query in queries:
                with self._driver.session(database=self._database) as session:
                    session.run(query)

        def import_license_records(self, licenses_file):
            """Write one LicenseRecord per row of the source.

            businessId keeps the account number as the source wrote it, without
            the `licenses:` prefix that Organization carries. That is deliberate,
            not an oversight: records hold what the source said,
            entities hold what we assert. It also means the two cannot be
            joined by equality -- the prefix has to be added first.
            """
            # TODO: `Award Amount` and `Approval Date` do not exist in this CSV.
            # They are columns of the contracts source, left behind by a
            # copy-paste. A missing key on a Cypher parameter map evaluates to
            # null, so `n.amount` and `n.date` are simply never written and the
            # load reports nothing -- which is why they survived this long.
            query = """
            UNWIND $batch as item
            MERGE (n:LicenseRecord {id: item.RECORD_ID})
            SET n.license_id = item.`LICENSE ID`,
                n.name = coalesce(item.`LEGAL NAME`, item.`DOING BUSINESS AS NAME`),
                n.businessName = coalesce(item.`DOING BUSINESS AS NAME`, '-'),
                n.businessId = toString(item.`ACCOUNT NUMBER`),
                n.address = item.ADDRESS,
                n.addressPostalCode = item.`ZIP CODE`,
                n.addressState = item.STATE,
                n.addressCity = item.CITY,
                n.source = item.DATA_SOURCE,
                n.amount = item.`Award Amount`,
                n.date = item.`Approval Date`,
                n.startDate = item.`LICENSE TERM START DATE`,
                n.endDate = item.`LICENSE TERM EXPIRATION DATE`,
                n.status = item.`LICENSE STATUS`,
                n.code = item.`LICENSE CODE`,
                n.number = item.`LICENSE NUMBER`,
                n.siteNumber = item.`SITE NUMBER`,
                n.latitude = item.LATITUDE,
                n.longitude = item.LONGITUDE
            """
            size = self.get_csv_size(licenses_file)
            self.batch_store(query, self.get_rows(licenses_file), size=size)

        def import_license_type(self, licenses_file):
            query = """
            UNWIND $batch as item
            MERGE (n:LicenseType {id: toString(item.`LICENSE CODE`)})
            SET n.description = item.`LICENSE DESCRIPTION`
            """
            size = self.get_csv_size(licenses_file)
            self.batch_store(query, self.get_rows(licenses_file), size=size)

        def connect_license_to_type(self, licenses_file):
            query = """
            UNWIND $batch as item
            MERGE (n:LicenseType {id: toString(item.`LICENSE CODE`)})
            MERGE (m:LicenseRecord {id: item.RECORD_ID})
            MERGE (m)-[:HAS_LICENSE_TYPE]->(n)
            """
            size = self.get_csv_size(licenses_file)
            self.batch_store(query, self.get_rows(licenses_file), size=size)

        def import_organization(self, licenses_file):
            """Build one Organization per account number, accumulating its
            variants across every licence it ever held.

            The same account recurs once per licence term, each time with
            whatever name and address were on file that year. The set-valued
            properties -- names, addresses, addressCities -- are what makes the
            business searchable under all of them, and they are the input the
            organisation resolver blocks on later.

            Address is merged on the raw string, so the same doorway written
            two ways is two nodes. orgs_cluster works around it by comparing
            addresses with the unit designator stripped; nothing fixes it here.
            """
            query = """
            UNWIND $batch as item
            MERGE (o:Organization {id: 'licenses:' + toString(item.`ACCOUNT NUMBER`)})
            SET o.names = apoc.coll.toSet(coalesce(o.names, []) + coalesce(item.`LEGAL NAME`, item.`DOING BUSINESS AS NAME`, [])),
                o.otherNames = apoc.coll.toSet(coalesce(o.otherNames, []) + coalesce(item.`DOING BUSINESS AS NAME`, [])),
                o.source = item.DATA_SOURCE,
                o.addresses = apoc.coll.toSet(coalesce(o.addresses, []) + coalesce(item.ADDRESS, [])),
                o.addressPostalCodes = apoc.coll.toSet(coalesce(o.addressPostalCodes, []) + coalesce(toString(item.`ZIP CODE`), [])),
                o.addressStates = apoc.coll.toSet(coalesce(o.addressStates, []) + coalesce(item.STATE, [])),
                o.addressCities = apoc.coll.toSet(coalesce(o.addressCities, []) + coalesce(item.CITY, []))
            MERGE (a:Address {id: item.ADDRESS})
            SET a.addressPostalCode = toString(item.`ZIP CODE`),
                a.addressState = item.STATE,
                a.addressCity = item.CITY,
                a.latitude = item.LATITUDE,
                a.longitude = item.LONGITUDE
            MERGE (o)-[r:HAS_ADDRESS]->(a)
            SET r.source = item.DATA_SOURCE
            """
            size = self.get_csv_size(licenses_file)
            self.batch_store(query, self.get_rows(licenses_file), size=size)

        def connect_org_to_license(self, licenses_file):
            # The shortest of the accumulated names becomes the display name --
            # see contracts.py merge_vendors_and_orders() for why, and for what
            # the heuristic costs.
            query = """
            UNWIND $batch as item
            MERGE (n:Organization {id: 'licenses:' + toString(item.`ACCOUNT NUMBER`)})
            SET n.name = trim(apoc.text.capitalize(reduce(shortest = head(n.names), name IN n.names | CASE WHEN size(name) < size(shortest) THEN name ELSE shortest END)))
            MERGE (m:LicenseRecord {id: item.RECORD_ID})
            MERGE (n)-[:ORG_HAS_LICENSE]->(m)
            """
            size = self.get_csv_size(licenses_file)
            self.batch_store(query, self.get_rows(licenses_file), size=size)

        def connect_people_to_org(self, licenses_file):
            """Connect resolved Person entities to the firm they own.

            This is the step that turns two disconnected halves of the graph
            into one: owners carry an employerId, licences carry the account
            number it points at, and the edge is drawn between the *entity* and
            the organisation, never between the record and the organisation.

            It depends on people_cluster having run. The MATCH traverses
            RECORD_RESOLVED_TO, which only exists once the Person clusters are
            built; run this importer on a graph without them and the pass
            completes, reports success and writes zero edges. There is no check
            for it -- the failure looks exactly like a source with no owners.
            """
            query = """
            UNWIND $batch as item
            MERGE (n:Organization {id: 'licenses:' + toString(item.`ACCOUNT NUMBER`)})
            WITH n, item
            MATCH (m:PersonRecord {employerId: 'licenses:' + toString(item.`ACCOUNT NUMBER`)})-[:RECORD_RESOLVED_TO]->(p:Person)
            MERGE (p)-[r:WORKS_FOR_ORG]->(n)
            SET r.roles = p.titles
            """
            size = self.get_csv_size(licenses_file)
            self.batch_store(query, self.get_rows(licenses_file), size=size)
        
        def import_data(self, license_file):
            # TODO: six steps, each parsing the CSV twice -- once in
            # get_csv_size() to size a progress bar and once in get_rows() to
            # feed the batches. Measured 14/8: a single pass over this file
            # costs about 14s (4.3s to read, 9.5s to iterate), so twelve passes
            # spend at least three minutes re-reading the same rows, half of it
            # only so that tqdm can show a total. Counting once would remove
            # half of it; merging the six queries is a larger change, since
            # each one re-MERGEs the nodes it needs.
            logging.info("Loading constraints...")
            self.set_constraints()

            logging.info("Loading license records...")
            self.import_license_records(license_file)
    
            logging.info("Merging license types...")
            self.import_license_type(license_file)
    
            logging.info("Connecting licenses to types...")
            self.connect_license_to_type(license_file)
    
            logging.info("Importing organizations...")
            self.import_organization(license_file)
    
            logging.info("Connecting organizations to licenses...")
            self.connect_org_to_license(license_file)

            logging.info("Connecting people to organizations...")
            self.connect_people_to_org(license_file)

    return ChicagoLicensesImporter

if __name__ == '__main__':
    from util.cli_entry import run_backend_importer

    run_backend_importer(
        chi_licenses_importer_factory,
        description="Run Chicago Licenses Importer with selected backend.",
        file_help="Path to the Business Licenses CSV file",
        default_base_path="./data/"
    )