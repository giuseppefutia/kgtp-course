"""Contracts: two layers, and most of the modelling decisions live here.

Each row of the source is one *revision* of a purchase order, so 185,730 rows
describe 88,916 contracts. The graph keeps both: ContractRecord is what the
source said, Contract is what we assert after reading every revision of it.

That split is the reason for the paired relationship names -- RECORDED_VENDOR
on the record against HAS_VENDOR on the contract -- and for the derive_* steps,
which recompute the entity layer from the records and must be re-run rather than
patched.
"""


def chi_contracts_importer_factory(base_importer_cls, backend: str):
    import logging

    class ChicagoContractsImporter(base_importer_cls):
        def __init__(self):
            super().__init__()
            self.backend = backend

        @staticmethod
        def get_csv_size(contracts_file, encoding="utf-8"):
            return sum(1 for _ in ChicagoContractsImporter.get_rows(contracts_file))

        @staticmethod
        def get_rows(contracts_file):
            import pandas as pd
            import numpy as np
            contracts = pd.read_csv(contracts_file, low_memory=False)
            contracts['DATA_SOURCE'] = "CONTRACTS"
            contracts['RECORD_TYPE'] = "CONTRACT"  # written, never read by any query
            if 'RECORD_ID' not in contracts:
                # TODO(A10): positional id. See licenses.py get_rows() for why
                # the offsets keep the sources apart by margin rather than by
                # construction. Contracts start at 0 and are the only source
                # with a natural key nearly available: PO + revision is unique
                # on all but 45 groups of rows.
                contracts.insert(0, 'RECORD_ID', range(0, len(contracts)))
            contracts.replace({np.nan: None}, inplace=True)
            for _, row in contracts.iterrows():
                yield row.to_dict()

        def set_constraints(self):
            queries = [
                "CREATE CONSTRAINT contract_record_id IF NOT EXISTS FOR (node:ContractRecord) REQUIRE node.id IS UNIQUE",
                "CREATE INDEX contract_record_contract_id IF NOT EXISTS FOR (node:ContractRecord) ON (node.contractId)",
                "CREATE CONSTRAINT contract_id IF NOT EXISTS FOR (node:Contract) REQUIRE node.id IS UNIQUE",
                "CREATE CONSTRAINT procurement_type_id IF NOT EXISTS FOR (node:ProcurementType) REQUIRE node.id IS UNIQUE",
                "CREATE CONSTRAINT department_id IF NOT EXISTS FOR (node:Department) REQUIRE node.id IS UNIQUE",
                "CREATE CONSTRAINT contract_type IF NOT EXISTS FOR (node:ContractType) REQUIRE node.id IS UNIQUE",
                "CREATE CONSTRAINT specification_id IF NOT EXISTS FOR (node:Specification) REQUIRE node.id IS UNIQUE",
                "CREATE CONSTRAINT organization_id IF NOT EXISTS FOR (node:Organization) REQUIRE node.id IS UNIQUE",
                "CREATE CONSTRAINT address_id IF NOT EXISTS FOR (node:Address) REQUIRE node.id IS UNIQUE",
                "CREATE FULLTEXT INDEX organization_name IF NOT EXISTS FOR (node:Organization) ON EACH [node.name]"
            ]
            for query in queries:
                with self._driver.session(database=self._database) as session:
                    session.run(query)

        def import_contract_records(self, contracts_file):
            """Write one ContractRecord per revision, dates typed and raw.

            Every date is stored twice, and the plain name carries
            the *typed* value because that is the name a query generator
            guesses: if approvalDate held the string, every temporal comparison
            would be a string comparison, and "06/15/2025" > "01/02/2026" is
            true. Plausible answers, wrong, no error.

            The raw text is kept beside it because seven dates in the source are
            semantically impossible -- years 0201, 0204, 0207, and a contract
            ending in 3030. Neo4j accepts them as perfectly formed dates, so
            parsing does not catch them and nothing downstream will. The
            original text is the only thing that lets anyone notice.

            Conversion does not repair those seven, it only makes them visible.
            A third of the rows have no start date at all (34.8%) and a third no
            end date (35.2%): the typed field is null, and a WHERE on it drops
            them silently.
            """
            query = """
            UNWIND $batch as item
            MERGE (n:ContractRecord {id: item.RECORD_ID})
            SET n.name = item.`Purchase Order Description`,
                n.amount = item.`Award Amount`,
                n.startDateRaw = item.`Start Date`,
                n.endDateRaw = item.`End Date`,
                n.approvalDateRaw = item.`Approval Date`,
                n.startDate = CASE WHEN coalesce(item.`Start Date`, '') <> ''
                    THEN date(datetime({epochMillis:
                        apoc.date.parse(item.`Start Date`, 'ms', 'MM/dd/yyyy')}))
                    ELSE NULL END,
                n.endDate = CASE WHEN coalesce(item.`End Date`, '') <> ''
                    THEN date(datetime({epochMillis:
                        apoc.date.parse(item.`End Date`, 'ms', 'MM/dd/yyyy')}))
                    ELSE NULL END,
                n.approvalDate = CASE WHEN coalesce(item.`Approval Date`, '') <> ''
                    THEN date(datetime({epochMillis:
                        apoc.date.parse(item.`Approval Date`, 'ms', 'MM/dd/yyyy')}))
                    ELSE NULL END,
                n.pdfFile = item.`Contract PDF`,
                n.vendorId = item.`Vendor ID`,
                n.contractId = item.`Purchase Order (Contract) Number`,
                n.specificationId = item.`Specification Number`,
                n.source = item.DATA_SOURCE
            """
            size = self.get_csv_size(contracts_file)
            self.batch_store(query, self.get_rows(contracts_file), size=size)

        def merge_vendors_and_orders(self, contracts_file):
            """Attach each revision to its purchase order and to its vendor.

            The MATCH is on the record's own key, never on contractId.
            contractId is the purchase order number, which every revision
            shares, so a MERGE on it binds *all* revisions of the order and
            each input row would write its vendor onto every one of them. PO
            27019 has nine revisions and two different vendors.

            The Contract keeps typed dates only: the entity is what we assert,
            the raw source text belongs to the record.

            The display name is the shortest of the accumulated names. It is a
            heuristic, not a rule -- shortest usually means least decorated
            ("ACME INC" over "ACME INC DBA ACME SUPPLY OF CHICAGO"), but it also
            prefers a truncated name over a complete one, and the full set stays
            in `names` precisely because of that. The same heuristic is repeated
            in licenses.py and in the three cluster factories; every copy is
            this one.
            """
            query = """
            UNWIND $batch AS item
            MATCH (n:ContractRecord {id: item.RECORD_ID})
            MERGE (m:Contract {id: item.`Purchase Order (Contract) Number`})
            SET m.names = apoc.coll.toSet(coalesce(m.names, []) + coalesce(item.`Purchase Order Description`, []))

            WITH item, n, m,
                [d IN [n.startDate] WHERE d IS NOT NULL] AS startDates,
                [d IN [n.endDate] WHERE d IS NOT NULL] AS endDates

            SET m.startDate = coalesce(apoc.coll.min(startDates), m.startDate),
                m.endDate = coalesce(apoc.coll.max(endDates), m.endDate)

            // Identifiers are strings, and namespaced by source.
            //
            // Two problems in one. Pandas types a column of pure digits as
            // int64, so ACCOUNT NUMBER arrived as a number while Vendor ID --
            // which contains letters -- arrived as text: the same property held
            // both, and MATCH on the wrong type returns zero rows without error.
            //
            // Normalising the type then revealed the second: three vendor ids
            // and three account numbers are the same string. The earlier check
            // that found "no collisions" had compared *typed* values, so the
            // absence was an accident of typing, not a property of the data.
            // The prefix makes collision impossible by construction rather than
            // absent by luck.
            //
            // ContractRecord.vendorId deliberately keeps the raw source value:
            // records hold what the source said, entities hold what we assert.
            MERGE (o:Organization {id: 'contracts:' + toString(item.`Vendor ID`)})
            SET o.names = apoc.coll.toSet(coalesce(o.names, []) + coalesce(item.`Vendor Name`, [])),
                o.source = item.DATA_SOURCE,
                o.addresses = apoc.coll.toSet(coalesce(o.addresses, []) + coalesce(item.`Address 1`, []) + coalesce(item.`Address 2`, [])),
                o.addressPostalCodes = apoc.coll.toSet(coalesce(o.addressPostalCodes, []) + coalesce(toString(item.Zip), [])),
                o.addressStates = apoc.coll.toSet(coalesce(o.addressStates, []) + coalesce(item.State, [])),
                o.addressCities = apoc.coll.toSet(coalesce(o.addressCities, []) + coalesce(item.City, []))
            
            WITH item, n, m, o
            SET o.name = trim(apoc.text.capitalize(reduce(shortest = head(o.names), name IN o.names | CASE WHEN size(name) < size(shortest) THEN name ELSE shortest END)))
            
            MERGE (n)-[:INCLUDED_IN_CONTRACT]->(m)
            MERGE (n)-[:RECORDED_VENDOR]->(o)

            // A missing value creates neither node nor edge. The previous
            // coalesce(..., "Unknown") turned absence into a category and, worse,
            // into a supernode: ProcurementType "Unknown" carried 130,578 edges,
            // 70% of all records, putting every contract without that field two
            // hops from every other one. Ruinous for pathfinding and pure noise
            // for graph traversal.
            FOREACH (_ IN CASE WHEN coalesce(item.`Address 1`, '') <> '' THEN [1] ELSE [] END |
                MERGE (a:Address {id: item.`Address 1`})
                SET a.addressPostalCode = toString(item.Zip),
                    a.addressState = item.State,
                    a.addressCity = item.City
                MERGE (o)-[r:HAS_ADDRESS]->(a)
                SET r.source = item.DATA_SOURCE
            )

            FOREACH (_ IN CASE WHEN coalesce(item.`Procurement Type`, '') <> '' THEN [1] ELSE [] END |
                MERGE (t:ProcurementType {id: item.`Procurement Type`})
                MERGE (n)-[:HAS_PROCUREMENT_TYPE]->(t)
            )
            """
            size = self.get_csv_size(contracts_file)
            self.batch_store(query, self.get_rows(contracts_file), size=size)

        def derive_contract_vendors(self):
            """Lift the vendor from the revisions up to the purchase order.

            Module 3 loads the entity layer only: ContractRecord does not exist
            there, so without this edge a Contract has no vendor at all and
            "who was awarded this contract" cannot be asked.

            One edge per distinct vendor, carrying the interval over which that
            vendor was the counterparty. 98.5% of purchase orders have a single
            vendor, so the edge is usually unique and the obvious query is
            exact; the remaining 1.5% carry the dates that say which one is
            current.

            Runs after every revision is loaded, not inside the batch: validTo
            for one vendor is the start of the next, which needs the whole
            history.

            Derived, therefore regenerated rather than patched. Re-running is
            safe: existing HAS_VENDOR edges are dropped first.
            """
            query = """
            MATCH (m:Contract)<-[:INCLUDED_IN_CONTRACT]-(r:ContractRecord)
                  -[:RECORDED_VENDOR]->(o:Organization)
            WITH m, o, min(r.approvalDate) AS firstSeen
            ORDER BY firstSeen
            WITH m, collect({vendor: o, from: firstSeen}) AS spans
            UNWIND range(0, size(spans) - 1) AS i
            WITH m,
                 spans[i].vendor AS vendor,
                 spans[i].from   AS validFrom,
                 CASE WHEN i + 1 < size(spans) THEN spans[i + 1].from ELSE NULL END AS validTo
            MERGE (m)-[v:HAS_VENDOR]->(vendor)
            SET v.validFrom = validFrom,
                v.validTo   = validTo
            """
            with self._driver.session(database=self._database) as session:
                session.run("MATCH (:Contract)-[v:HAS_VENDOR]->() DELETE v")
                session.run(query)

        def merge_departments_contract_types(self, contracts_file):
            """Hang the department and the contract type off the revision.

            Both belong to the revision, because that is what the source
            records. What happens to them afterwards differs, and the difference
            is the point:

                contract type -> stays on the record, nothing lifted
                    (decision 8). The field mixes two dimensions: "Time
                    Extension" and "Modification" describe what a revision did,
                    "PRO SERV-BUSINESS CONSULTING" describes what the contract
                    is. PO C027405 carries six such values across eight
                    revisions, so no single contract-level value would be
                    honest. A Contract with no type beats a Contract with the
                    wrong one -- absence is visible, error is not.

                department -> lifted to the contract with validity, like the
                    vendor (decision 9). Here the multiplicity is real: PO
                    T25581 moves across six departments between 2000 and 2007
                    with the same supplier. That is history worth keeping, not
                    noise worth flattening.

            Empty values create neither node nor edge, which is why both writes
            sit inside a FOREACH guard -- decision 10.
            """
            query = """
            UNWIND $batch as item
            MATCH (n:ContractRecord {id: item.RECORD_ID})
            MERGE (m:Contract {id: item.`Purchase Order (Contract) Number`})
            SET m.name = apoc.text.join(m.names, " + ")

            FOREACH (_ IN CASE WHEN coalesce(item.Department, '') <> '' THEN [1] ELSE [] END |
                MERGE (d:Department {id: item.Department})
                SET d.source = "CONTRACTS"
                MERGE (n)-[:RECORDED_DEPARTMENT]->(d)
            )

            FOREACH (_ IN CASE WHEN coalesce(item.`Contract Type`, '') <> '' THEN [1] ELSE [] END |
                // TODO(46): normalise the string before the MERGE. The portal
                // writes the same category in two cases, so this creates two
                // nodes for one thing -- DELEGATE AGENCY and Delegate Agency,
                // and the same for CONSTRUCTION, ONE SHOT and DEMOLITION.
                // Applied at the next rebuild, not by patching the graph.
                MERGE (ct:ContractType {id: item.`Contract Type`})
                MERGE (n)-[:HAS_CONTRACT_TYPE]->(ct)
            )
            """
            size = self.get_csv_size(contracts_file)
            self.batch_store(query, self.get_rows(contracts_file), size=size)

        def derive_contract_departments(self):
            """Lift the awarding department from the revisions to the order.

            Same shape as derive_contract_vendors, and for the same reason:
            module 3 loads the entity layer only, where ContractRecord does not
            exist, so without this edge a Contract has no department.

            Ordered by approvalDate, never by revision number. Revision values
            mix formats -- 0, 1, 2 alongside C00554, T20846, T90829 -- and the
            chronology does not follow them: on PO C027405, revision C00554 is
            from 2000 and revision 1 from 2003.
            """
            query = """
            MATCH (m:Contract)<-[:INCLUDED_IN_CONTRACT]-(r:ContractRecord)
                  -[:RECORDED_DEPARTMENT]->(d:Department)
            WITH m, d, min(r.approvalDate) AS firstSeen
            ORDER BY firstSeen
            WITH m, collect({dept: d, from: firstSeen}) AS spans
            UNWIND range(0, size(spans) - 1) AS i
            WITH m,
                 spans[i].dept AS dept,
                 spans[i].from AS validFrom,
                 CASE WHEN i + 1 < size(spans) THEN spans[i + 1].from ELSE NULL END AS validTo
            MERGE (dept)-[a:ASSIGNS_CONTRACT]->(m)
            SET a.validFrom = validFrom,
                a.validTo   = validTo
            """
            with self._driver.session(database=self._database) as session:
                session.run("MATCH ()-[a:ASSIGNS_CONTRACT]->() DELETE a")
                session.run(query)
        
        def derive_specifications(self):
            """The tender behind a contract, from a field the record already holds.

            `Specification Number` is the call the city published; a contract is
            what came out of it. Usually one tender, one award -- 37,427 of them.
            Sometimes several: specification 1301245 produced PO 333917 to F.H.
            Paschen as the primary award and PO 333324 to Leopardo as the
            secondary, and until this step nothing in the graph joined them.

            Derived rather than merged row by row, because import_contract_records
            already wrote the value onto the record: a second pass over 185,730
            CSV rows would buy nothing.

            Two values are refused. `99999999999` (13,950 records) and `00000`
            (1) are what the source writes when there is no tender, and a value
            carried by 3,478 contracts of 872 different vendors identifies
            nothing. The test is a single digit repeated, and deliberately not a
            size threshold: the largest real specification, 1070196, has 1,734
            contracts across 128 vendors because it is a city-wide term
            agreement -- a tender, not a filler. Measured 20/9/2026.

            The id carries its namespace (decision 14). The column mixes
            numbering spaces: `1301245` sits next to `B69683203`.

            The edge is written on the revision and lifted to the contract like
            the department (decision 9), but without validity, because a contract
            does not move between tenders. 267 contracts of 80,223 carry more
            than one value across their revisions and get an edge each: they are
            the same tender written twice -- `B74851001` and `B74851001A` --
            and choosing one would be inventing which.
            """
            records = """
            CALL apoc.periodic.iterate(
"MATCH (r:ContractRecord) WHERE coalesce(r.specificationId, '') <> '' AND NOT r.specificationId =~ '^(0+|9+)$' RETURN r",
"MERGE (s:Specification {id: 'spec:' + r.specificationId}) SET s.source = 'CONTRACTS' MERGE (r)-[:RECORDED_SPECIFICATION]->(s)",
                {batchSize: 10000})
            YIELD batches, total RETURN batches, total
            """
            contracts = """
            MATCH (r:ContractRecord)-[:RECORDED_SPECIFICATION]->(s:Specification)
            MATCH (r)-[:INCLUDED_IN_CONTRACT]->(m:Contract)
            MERGE (m)-[:AWARDED_UNDER]->(s)
            """
            with self._driver.session(database=self._database) as session:
                session.run("MATCH (:ContractRecord)-[e:RECORDED_SPECIFICATION]->() DELETE e")
                session.run("MATCH (:Contract)-[e:AWARDED_UNDER]->() DELETE e")
                session.run(records)
                session.run(contracts)

        def import_data(self, contracts_file):
            logging.info("Loading constraints and indexes...")
            self.set_constraints()
    
            logging.info("Loading contract records...")
            self.import_contract_records(contracts_file)
            
            logging.info("Merging vendors and orders...")
            self.merge_vendors_and_orders(contracts_file)

            logging.info("Merging departments and contract types...")
            self.merge_departments_contract_types(contracts_file)

            # Last: both need every revision in place to compute the intervals.
            logging.info("Deriving contract-level vendors...")
            self.derive_contract_vendors()

            logging.info("Deriving contract-level departments...")
            self.derive_contract_departments()

            logging.info("Deriving specifications...")
            self.derive_specifications()

    return ChicagoContractsImporter

if __name__ == '__main__':
    from util.cli_entry import run_backend_importer

    run_backend_importer(
        chi_contracts_importer_factory,
        description="Run Chicago Contracts Importer with selected backend.",
        file_help="Path to the Contracts CSV file",
        default_base_path="./data/"
    )