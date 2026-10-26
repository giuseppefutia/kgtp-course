"""Person entity resolution: records in, Person entities out.

Three stages, and the order is the whole design. Similarity edges first, from a
full-text blocking pass; then two community algorithms over those edges; then
one Person per community.

WCC used to decide the entities and now only offers a second opinion, because
it ignores edge weights and collapsed 37,824 records into a single person. What
replaced it is the *finest* Louvain level, not the final one -- decision 12
explains why the coarser levels are worse rather than better.

Everything here is derived from IS_SIMILAR_TO, so the thresholds in
create_people_similarity decide more about the graph than any algorithm choice
below them.
"""


def chi_people_similarity_factory(base_importer_cls, backend: str):
    import logging

    class ChicagoPeopleSimilarity(base_importer_cls):
        def __init__(self):
            super().__init__()
            self.backend = backend
            # 500 rather than the default 1000: every row in a batch runs its
            # own full-text query and similarity pass, so a batch here is far
            # heavier than a batch of plain writes. The number itself has never
            # been measured against alternatives.
            self.batch_size = 500

        def get_record_rows(self, nodes=None):
            query = """
            MATCH (n:PersonRecord)
            WHERE NOT (n.fullName IS NULL OR n.fullName = " " OR n.fullName = "?") AND
                  NOT n:RecordProcessed AND
                  ($nodes IS NULL OR elementId(n) in $nodes)
            RETURN n.id as id
            """
            with self._driver.session(database=self._database)  as session:
                result = session.run(query, {"nodes": nodes})
                for record in iter(result):
                    yield dict(record)

        def count_record_rows(self, nodes=None):
            query = """
            MATCH (n:PersonRecord)
            WHERE NOT (n.fullName IS NULL OR n.fullName = " " OR n.fullName = "?") AND
                  NOT n:RecordProcessed AND
                  ($nodes IS NULL OR elementId(n) in $nodes)
            RETURN COUNT(*) as rows
            """
            with self._driver.session(database=self._database)  as session:
                return session.run(query, {"nodes": nodes}).single()["rows"]

        def get_cluster_rows(self):
            query = """MATCH (n:Person) RETURN DISTINCT n.clusterId as id"""
            with self._driver.session(database=self._database)  as session:
                result = session.run(query)
                for record in iter(result):
                    yield dict(record)

        def count_cluster_rows(self):
            query = """MATCH (n:Person) RETURN COUNT(DISTINCT n.clusterId) as rows"""
            with self._driver.session(database=self._database)  as session:
                return session.run(query).single()["rows"]

        def create_people_similarity(self, nodes=None):
            """Propose candidate pairs by name, keep the ones that score.

            Two gates, and both are arbitrary numbers that decide the shape of
            every entity built afterwards. The full-text index proposes
            candidates with a fuzzy term per word (~0.65, so one or two edits
            per word); Sorensen-Dice over the whole name then keeps the pairs
            above 0.695.

            The second gate is measured against nothing. There is no ground
            truth for these names, so the threshold cannot be optimised, only
            defended. That asymmetry -- a threshold can be shown wrong but
            never shown right -- is why WCC is kept running as a disagreeing
            second opinion.

            The known weakness is short names. Dice over 'Li Ji' has four
            bigrams, so anything sharing one scores high, and the residue after
            decision 12 is still nine communities above 100 records. The remedy
            is here, in a threshold that accounts for name length, not
            downstream in the clustering.

            SET p:RecordProcessed makes the pass resumable and incremental: a
            second run skips whatever is already labelled. It also means that
            re-running after changing a threshold does nothing at all until the
            label is removed, and the pass will report success either way.
            """
            query = """
            UNWIND $batch as item
            MATCH (p:PersonRecord {id: item.id})
            SET p:RecordProcessed
            WITH p, p.fullName as name,
                 apoc.text.split(apoc.text.replace(p.fullName ,'[^a-zA-Z0-9\\s]', ''), "\\s+") as name_words
            WHERE size(name_words) > 0
            CALL db.index.fulltext.queryNodes(
                "person_record_fullName",
                apoc.text.join([x IN name_words | trim(x) + "~0.65"], " AND ")
            )
            YIELD node, score
            WITH p, name, node
            WHERE p <> node
            WITH p, node, apoc.text.sorensenDiceSimilarity(name, node.fullName) as simil
            WHERE simil > 0.695
            MERGE (node)-[r:IS_SIMILAR_TO {method: "SIMILAR_NAME"}]->(p)
            ON CREATE SET r.score = simil
            """
            size = self.count_record_rows(nodes)
            self.batch_store(query, self.get_record_rows(nodes), size=size)

        def project_wcc_graph(self, node_label ="PersonRecord"):
            query = """
            CALL gds.graph.project('personWcc', [$node_label], ['IS_SIMILAR_TO'])
            YIELD graphName, nodeCount, relationshipCount
            RETURN graphName, nodeCount, relationshipCount
            """
            with self._driver.session(database=self._database)  as session:
                session.run(query, {"node_label": node_label})

        def run_wcc(self):
            query = """
            CALL gds.wcc.write('personWcc', { writeProperty: 'wccCommunity' })
            YIELD nodePropertiesWritten, componentCount;
            """
            with self._driver.session(database=self._database)  as session:
                session.run(query)

        def delete_wcc_projection(self):
            query = "CALL gds.graph.drop('personWcc')"
            with self._driver.session(database=self._database)  as session:
                session.run(query)

        def create_record_clusters(self):
            query = """
            CALL apoc.periodic.iterate(
                "MATCH (n:PersonRecord) RETURN DISTINCT n.clusterKey as id",
                "MERGE (n:Person {clusterId: id}) SET n.method = 'louvain-finest'",
                {batchSize:10000})
            YIELD batches, total RETURN batches, total
            """
            with self._driver.session(database=self._database)  as session:
                session.run(query)

        def create_connections_to_clusters(self):
            query = """
            UNWIND $batch as item
            MATCH (p:PersonRecord {clusterKey: item.id})
            MATCH (c:Person {clusterId: item.id})
            MERGE (p)-[:RECORD_RESOLVED_TO]->(c)
            SET c.fullNames = coalesce(c.fullNames, []) + p.fullName,
                c.employerIds = coalesce(c.employerIds, []) + p.employerId,
                c.titles = coalesce(c.titles, []) + p.title
            """
            size = self.count_cluster_rows()
            self.batch_store(query, self.get_cluster_rows(), size=size)

        def create_final_names_of_clusters(self):
            # Shortest of the spellings wins -- see contracts.py
            # merge_vendors_and_orders() for why, and for what it costs. On
            # people it costs more than on companies: the shortest spelling of a
            # person is often the one missing a middle name.
            query = """
            UNWIND $batch as item
            MATCH (c:Person {clusterId: item.id})
            WITH c, reduce(shortest = head(c.fullNames), name IN c.fullNames |
                           CASE WHEN size(name) < size(shortest) THEN name ELSE shortest END) AS shortestName
            SET c.name = shortestName
            """
            size = self.count_cluster_rows()
            self.batch_store(query, self.get_cluster_rows(), size=size)

        def project_louvain_graph(self):
            query = """
            MATCH (source:PersonRecord)-[r:IS_SIMILAR_TO]->(target:PersonRecord)
            RETURN gds.graph.project(
                'personLouvain',
                source,
                target,
                { relationshipProperties: r { .score } },
                { undirectedRelationshipTypes: ['*'] }
            )
            """
            with self._driver.session(database=self._database)  as session:
                session.run(query)

        def run_louvain(self):
            # concurrency 1 makes the result reproducible. Louvain has no
            # randomSeed option in GDS 2.13; the non-determinism comes from the
            # order in which parallel threads move nodes, so serialising removes
            # it. Measured cost: ~2s on 207,885 nodes and 1,428,116 edges.
            query = """
            CALL gds.louvain.write('personLouvain', {
                relationshipWeightProperty: 'score',
                writeProperty: 'louvainLevels',
                includeIntermediateCommunities: true,
                concurrency: 1
            })
            YIELD communityCount, modularity, modularities
            """
            with self._driver.session(database=self._database)  as session:
                session.run(query)

        def set_louvain_cluster(self):
            """Take the FINEST Louvain level as the entity, and give every
            unmatched record an entity of its own.

            Louvain returns a hierarchy, not a partition. Measured 12/8 on this
            graph, the four levels get worse as they climb:

                level 0   61,599 communities   largest   234   9 over 100
                level 1   53,822                         976  72
                level 2   52,779                       1,503 128
                level 3   52,660                       2,467 104

            Level 0 wins for a structural reason, not by luck: Louvain climbs to
            maximise modularity, which rewards large well-separated communities.
            We do not want communities, we want *people* -- small, extremely
            dense groups of near-identical records. The algorithm's objective is
            not ours, so we keep its first pass (weighted local moving, which
            can refuse a weak edge) and discard the aggregations above it.

            Records with no IS_SIMILAR_TO edge never enter the projection and
            get no community. They are people seen once, so each becomes its own
            entity -- what WCC used to do implicitly. Skipping them would leave
            them without a Person, and licenses.py resolves through
            RECORD_RESOLVED_TO.

            Diagnostic properties left on every record, so the comparison lives
            in the graph rather than in a notebook someone has to re-run:

                wccCommunity      WCC, comparison only, forms nothing
                louvainLevels     the whole hierarchy, one entry per level
                louvainFinest     level 0 -- what the entities are built from
                louvainCoarsest   last level -- what a naive reading would use
                clusterKey        the key actually used

            These are diagnostics, not domain. A query generator answering "who
            was awarded this contract" should never touch them.
            """
            query = """
            MATCH (p:PersonRecord)
            WITH p, toIntegerList(p.louvainLevels) AS levels
            SET p.louvainFinest   = CASE WHEN levels IS NOT NULL THEN levels[0] ELSE NULL END,
                p.louvainCoarsest = CASE WHEN levels IS NOT NULL THEN levels[-1] ELSE NULL END,
                p.clusterKey      = CASE
                    WHEN levels IS NOT NULL THEN 'L' + toString(levels[0])
                    ELSE 'R' + toString(p.id)
                END
            """
            with self._driver.session(database=self._database)  as session:
                session.run(query)

        def delete_louvain_projection(self):
            query = "CALL gds.graph.drop('personLouvain')"
            with self._driver.session(database=self._database)  as session:
                session.run(query)
        
        def apply_updates(self):
            """Similarity, then both community algorithms, then the entities.

            Order matters and it changed on 12/8. The clusters used to come from
            WCC, which knows nothing about edge weights: two dense groups joined
            by a single weak edge become one cluster. On short names weak edges
            abound -- Sorensen-Dice over 'Li Ji', four bigrams, scores high
            against anything sharing one -- and the result was a single Person
            holding 37,824 records under 26,003 spellings, 10% of every person
            in the graph.

            Clusters now come from Louvain instead. WCC still runs, and its
            componentId still lands on the nodes, because the disagreement
            between the two partitions is worth having in the graph: it does not
            say which one is right, it says where the answer is unstable, and
            that is where a human should look. Real data has no ground truth to
            check against, so a second opinion is one of the few instruments
            left.
            """
            logging.info("Creating similarity IS_SIMILAR_TO relationships...")
            self.create_people_similarity()

            # WCC: kept for comparison only, no longer used to form entities.
            logging.info("Creating WCC graph projection...")
            self.project_wcc_graph()

            logging.info("Running WCC algorithm (comparison only)...")
            self.run_wcc()

            logging.info("Deleting WCC projection...")
            self.delete_wcc_projection()

            # Louvain: this is what the entities are built from.
            logging.info("Creating Louvain projection....")
            self.project_louvain_graph()

            logging.info("Running Louvain algorithm...")
            self.run_louvain()

            logging.info("Assigning cluster keys (Louvain level 0 + singletons)...")
            self.set_louvain_cluster()

            logging.info("Deleting Louvain projection...")
            self.delete_louvain_projection()

            logging.info("Creating person clusters...")
            self.create_record_clusters()

            logging.info("Creating connections to clusters...")
            self.create_connections_to_clusters()

            logging.info("Creating cluster names...")
            self.create_final_names_of_clusters()

    return ChicagoPeopleSimilarity

if __name__ == '__main__':
    from util.cli_entry import run_backend_importer

    run_backend_importer(
        chi_people_similarity_factory,
        description="Run Chicago People Similarity pipeline with selected backend.",
        file_help="No file needed.",
        default_base_path="./data/",
        require_file=False
    )