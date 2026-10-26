"""Incremental person resolution: what happens when new records arrive.

The full pipeline resolves the whole graph at once. This one takes a batch of
new owner rows, computes similarity for those rows only, finds the existing
clusters they touch, and rebuilds just those -- which is the realistic shape of
the problem, since a graph in use does not get re-resolved from scratch.

Read import_data before anything else: the last step is restore_initial_state,
which deletes the new clusters and the new records and puts the old edges back.
As written, a run leaves the graph exactly as it found it. This is a rehearsal
of the incremental path, not the incremental path itself, and the restore is
what makes it safe to run twice while the mechanism is still being designed.
"""


def chi_people_batch_importer_factory(base_importer_cls, backend: str):
    import logging
    from factory.owners import chi_people_importer_factory
    from factory.people_cluster import chi_people_similarity_factory
    
    class ChicagoPeopleBatchImporter(base_importer_cls):
        def __init__(self):
            super().__init__()
            self.backend = backend
            self.owner_importer = chi_people_importer_factory(base_importer_cls, backend)()
            self.cluster_importer = chi_people_similarity_factory(base_importer_cls, backend)()

        @staticmethod
        def get_csv_size(owners_file):
            return sum(1 for _ in ChicagoPeopleBatchImporter.get_rows(owners_file))

        @staticmethod
        def get_rows(owners_file):
            # TODO: unlike owners.py, this yields the CSV untouched -- no
            # DATA_SOURCE, no RECORD_ID, no NaN-to-None conversion. The query
            # below reads all three, so the input file has to carry them
            # already and nothing checks that it does. On Neo4j a missing
            # RECORD_ID fails loudly, since MERGE refuses a null property; a
            # missing DATA_SOURCE does not, and simply leaves the records
            # without a source.
            import pandas as pd
            owners = pd.read_csv(owners_file, low_memory=False)
            for _, row in owners.iterrows():
                yield row.to_dict()
        
        def get_new_records(self):
            query = """
            MATCH (n:PersonRecord:NewRecord)
            REMOVE n:RecordProcessed // Mark as unprocessed if already exists
            RETURN elementId(n) as id
            """
            with self._driver.session(database=self._database)  as session:
                result = session.run(query)
                for record in iter(result):
                    yield dict(record)

        def import_people_records(self, owners_file):
            # TODO: this is a second, hand-written copy of the canonical name
            # expression that factory/naming.py exists to keep single -- the
            # exact drift its module docstring warns about. Today the two agree.
            # The day one of them learns about apostrophes or suffixes, records
            # loaded through this path stop matching records loaded through
            # owners.py, and the only symptom is fewer similarity edges.
            #
            # with_canonical_name() takes the three column expressions and the
            # placeholder is already the same, so the copy can be replaced by
            # the call used in owners.py.
            import_people_records_query = """
            UNWIND $batch as item
            MERGE (n:PersonRecord:NewRecord {id: item.RECORD_ID})
            SET n.firstName = coalesce(item.`Owner First Name`, NULL)
            SET n.lastName = coalesce(item.`Owner Last Name`, NULL)
            SET n.middleName = coalesce(item.`Owner Middle Initial`, NULL)
            SET n.fullName = CASE
                WHEN trim(apoc.text.replace(
                    coalesce(item.`Owner First Name`, '') + ' ' +
                    coalesce(item.`Owner Middle Initial`, '') + ' ' +
                    coalesce(item.`Owner Last Name`, ''),
                    "\\s+", " ")) = '' THEN NULL
                ELSE apoc.text.capitalizeAll(toLower(trim(apoc.text.replace(
                    coalesce(item.`Owner First Name`, '') + ' ' +
                    coalesce(item.`Owner Middle Initial`, '') + ' ' +
                    coalesce(item.`Owner Last Name`, ''),
                    "\\s+", " "))))
            END
            SET n.source = item.DATA_SOURCE
            SET n.employerId = 'licenses:' + toString(item.`Account Number`)
            SET n.title = item.Title
            """
            size = self.get_csv_size(owners_file)
            self.batch_store(import_people_records_query, self.get_rows(owners_file), size=size)
        
        def create_new_person_similarity(self):
            nodes = [i["id"] for i in self.get_new_records()]
            self.cluster_importer.create_people_similarity(nodes=nodes)

        def label_affected_nodes(self):
            """Mark everything a partial re-clustering would disturb.

            Not only the new records: also the existing records that share a
            Person with anything the new ones resemble. Re-running a community
            algorithm on a subgraph that stopped short of those would split
            clusters that were whole.

            OldCluster is what makes the restore possible afterwards -- it is
            the only record of which Person a node belonged to before.
            """
            label_query = """
            MATCH (n:NewRecord)-[:IS_SIMILAR_TO]-(m:PersonRecord)-[:RECORD_RESOLVED_TO]->(p:Person)<-[:RECORD_RESOLVED_TO]-(x:PersonRecord)
            SET 
                n:AffectedPersonRecord,
                n:NewRecord,
                x:AffectedPersonRecord,
                m:AffectedPersonRecord,
                p:AffectedPerson,
                p:OldCluster
            """
            with self._driver.session(database=self._database)  as session:
                session.run(label_query)
        
        def resolve_new_records(self):
            """Rebuild the affected clusters from the affected records only.

            TODO(decision 12): this path still resolves with WCC, which the full
            pipeline stopped using because it ignores edge weights and merged
            37,824 records into one person. So the incremental result and a full
            re-run no longer agree, and the incremental one is the weaker of the
            two. Aligning it means projecting Louvain over the affected subgraph
            and taking level 0, as people_cluster does.
            """
            self.cluster_importer.project_wcc_graph(node_label="AffectedPersonRecord")

            # 1. Need to create a new WCC query to include timestamp to force new componentIds
            new_wcc_query = """
            WITH apoc.date.currentTimestamp() as timestamp
            CALL gds.wcc.stream('personWcc', {})
            YIELD nodeId, componentId

            WITH gds.util.asNode(nodeId) as n, componentId AS componentId, timestamp
            WITH n, apoc.text.join([toString(componentId), toString(timestamp)], "___") as component
            SET n.componentId = component
            """
            with self._driver.session(database=self._database) as session:
                session.run(new_wcc_query)
            
            # 2. Delete WCC projection
            self.cluster_importer.delete_wcc_projection()

            # 3. Create new Person clusters
            resolve_query = """
            MATCH (n:PersonRecord:AffectedPersonRecord)
            WITH n, n.componentId as component
            MERGE (p:Person:NewCluster {clusterId: component})
            MERGE (n)-[:RECORD_RESOLVED_TO]->(p)
            SET p.fullNames = coalesce(p.fullNames, []) + n.fullName,
                p.employerIds = coalesce(p.employerIds, []) + n.employerId,
                p.titles = coalesce(p.titles, []) + n.title
            WITH p, reduce(shortest = head(p.fullNames), name IN p.fullNames |
                        CASE WHEN size(name) < size(shortest) THEN name ELSE shortest END) AS shortestName
            SET p.name = shortestName
            """
            with self._driver.session(database=self._database) as session:
                session.run(resolve_query)
            
            # 4. Connect new cluster to the old cluster (useful for restoring purposes)
            cluster_conn_query = """
            MATCH (old:Person:OldCluster)<-[rOld:RECORD_RESOLVED_TO]-(n:PersonRecord:AffectedPersonRecord)-[:RECORD_RESOLVED_TO]->(new:Person:NewCluster)
            MERGE (new)-[:HAS_OLD_CLUSTER]->(old)
            DELETE rOld
            """
            with self._driver.session(database=self._database) as session:
                session.run(cluster_conn_query)
            
            # 5. Create connections between Person and Organization nodes
            per_org_query = """
            MATCH (e:Person:NewCluster)
            MATCH (o:Organization)
            WHERE o.id in e.employerIds
            MERGE (e)-[r:WORKS_FOR_ORG]->(o)
            """
            with self._driver.session(database=self._database) as session:
                session.run(per_org_query)

        def restore_initial_state(self):
            # Restore old information into the new cluster
            restore_cluster_query = """
                MATCH (n:PersonRecord:AffectedPersonRecord)-[:RECORD_RESOLVED_TO]-(new:Person:NewCluster)-[:HAS_OLD_CLUSTER]->(old:Person:OldCluster)
                MERGE (n)-[:RECORD_RESOLVED_TO]->(old)
                SET n.componentId = old.clusterId
            """
            with self._driver.session(database=self._database) as session:
                session.run(restore_cluster_query)

            # Delete affected labels
            cleanup_query = """
                MATCH (n:PersonRecord:AffectedPersonRecord)-[:RECORD_RESOLVED_TO]->(p:Person:OldCluster)
                REMOVE n:AffectedPersonRecord
                REMOVE p:AffectedPerson
                REMOVE p:OldCluster
            """
            with self._driver.session(database=self._database) as session:
                session.run(cleanup_query)
            
            # Delete new clusters and relationships
            delete_new_clusters_query = """
                MATCH (n:Person:NewCluster)
                DETACH DELETE n
            """
            with self._driver.session(database=self._database) as session:
                session.run(delete_new_clusters_query)

            # Delete new records
            delete_new_records_query = """
                MATCH (n:PersonRecord:NewRecord)
                DETACH DELETE n
            """
            with self._driver.session(database=self._database) as session:
                session.run(delete_new_records_query)

        def import_data(self, owners_file):
            # TODO: this read is never used -- a full parse of the file for
            # nothing. Each step below opens it again through get_rows().
            import pandas as pd
            owners = pd.read_csv(owners_file, low_memory=False)

            logging.info("Loading new or updated person record nodes...")
            self.import_people_records(owners_file)

            logging.info("Creating people similarity relationships...")
            self.create_new_person_similarity()

            logging.info("Labeling affected nodes...")
            self.label_affected_nodes()
    
            logging.info("Resolving affected person records into clusters...")
            self.resolve_new_records()

            logging.info("Restoring initial state of old clusters...")
            self.restore_initial_state()

    return ChicagoPeopleBatchImporter

if __name__ == '__main__':
    from util.cli_entry import run_backend_importer

    run_backend_importer(
        chi_people_batch_importer_factory,
        description="Run Chicago People Importer with selected backend for batch processing.",
        file_help="Path to the Business Owners CSV batch file",
        default_base_path="./data/"
    )