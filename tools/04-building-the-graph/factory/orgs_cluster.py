"""Organisation entity resolution, and the bridge between the two islands.

Organizations arrive from two sources that share no key: contracts identify a
vendor by `contracts:<vendor id>`, licences by `licenses:<account number>`.
Nothing joins them except the resolution done here, so an OrganizationGroup
spanning both is the only way a query can go from a contract to the licences of
the firm that won it.

The same two corrections as people_cluster, arrived at separately (decision 13):
groups come from the finest Louvain level rather than from WCC, and the tokens
too common to discriminate are computed from the data instead of listed by hand.
The shape of the failure was different, though -- here it was a chain of weak
edges through the word ENTERPRISES, not a hub of short names.
"""

# Cypher string literal: strips a trailing unit designator from an address.
UNIT_RE = r"'(?i)\\s+(#|STE|SUITE|UNIT|APT|FL|FLOOR|RM|ROOM)\\b.*$'"


def chi_orgs_similarity_factory(base_importer_cls, backend: str):
    import logging
    
    class ChicagoOrgsSimilarity(base_importer_cls):
        def __init__(self):
            super().__init__()
            self.backend = backend

        def get_record_rows(self, nodes=None):
            query = """
            MATCH (n:Organization)
            WHERE NOT (n.name IS NULL OR n.name = " " OR n.name = "?") AND
                  NOT n:RecordProcessed AND
                  ($nodes IS NULL OR elementId(n) in $nodes)
            RETURN n.id as id
            """
            with self._driver.session(database=self._database) as session:
                result = session.run(query, {"nodes": nodes})
                for record in iter(result):
                    yield dict(record)

        def count_record_rows(self, nodes=None):
            query = """
            MATCH (n:Organization)
            WHERE NOT (n.name IS NULL OR n.name = " " OR n.name = "?") AND
                  NOT n:RecordProcessed AND
                  ($nodes IS NULL OR elementId(n) in $nodes)
            RETURN COUNT(*) as rows
            """
            with self._driver.session(database=self._database) as session:
                return session.run(query, {"nodes": nodes}).single()["rows"]

        def get_cluster_rows(self):
            query = "MATCH (n:OrganizationGroup) RETURN DISTINCT n.clusterId as id"
            with self._driver.session(database=self._database) as session:
                result = session.run(query)
                for record in iter(result):
                    yield dict(record)

        def count_cluster_rows(self):
            query = "MATCH (n:OrganizationGroup) RETURN COUNT(DISTINCT n.clusterId) as rows"
            with self._driver.session(database=self._database) as session:
                return session.run(query).single()["rows"]

        def compute_stopwords(self, min_freq=1000):
            """Tokens too common to discriminate, measured rather than listed.

            A token appearing in more than `min_freq` organisation names carries
            no evidence: two firms sharing only `ENTERPRISES` are not the same
            firm. Computing the list instead of hard-coding it keeps it true when
            the data changes, and makes the choice inspectable.

            Measured 17/8 on 210,740 organisations: only 35 tokens clear 1,000
            occurrences, while 86,168 appear in fewer than ten names. The generic
            tail is tiny and the discriminating head is enormous -- which is why
            a stoplist works here and a global similarity threshold cannot.

            The list is worth reading, not just applying. Alongside the expected
            legal forms and business words it contains CHICAGO, and five given
            names -- MARIA, JOSE, MICHAEL, JOHN, JAMES -- from sole traders who
            named the firm after themselves. The same names that concentrate the
            errors in person resolution reappear one level up.
            """
            query = """
            MATCH (o:Organization) WHERE o.name IS NOT NULL
            WITH o, apoc.text.split(toUpper(apoc.text.replace(o.name,'[^a-zA-Z0-9\\s]','')), '\\s+') AS w
            UNWIND w AS token
            WITH token WHERE size(token) > 2
            WITH token, count(*) AS freq WHERE freq >= $minFreq
            RETURN collect(token) AS stopwords
            """
            with self._driver.session(database=self._database) as session:
                rec = session.run(query, {"minFreq": min_freq}).single()
                words = rec["stopwords"] if rec else []
            logging.info(f"Stopwords computed from the data: {len(words)} tokens "
                         f"appearing in {min_freq}+ names")
            return words

        def create_org_similarity(self, nodes=None):
            """Link organisations that two independent signals agree on.

            Never merge on one signal. A company name alone proves nothing here:
            names repeat, and two `JOHNSON CONSTRUCTION INC` in different
            neighbourhoods score 1.0 against each other while being different
            firms. Every rule pairs the name with something else, and the weaker
            the second signal, the higher the name has to score.

                SAME_ADDRESS    identical address     name >= 0.3
                NORM_ADDRESS    address minus unit    name >= 0.5
                SAME_ZIP        same postal code      name >= 0.8
                SHARED_PEOPLE   2+ owners in common   name >= 0.5

            The previous version had only the first, and enforced the address
            with a hard MATCH: the address was a gate, not a signal, so anything
            with near-identical names at a different site was discarded without
            being looked at. Measured 12/8: 1,487 shared addresses produced 393
            bridging groups between the contracts and licences islands, out of
            14,094 contract-side organisations. The bottleneck was neither signal
            alone but their conjunction -- which is why widening means admitting
            other *pairs*, not lowering a threshold.

            One full-text pass serves every rule. Address and postcode are
            filters over the candidates, not blocking keys, so the postcode
            holding 7,872 organisations costs nothing: its pairs are never
            enumerated. A name reaching 0.8 is certainly inside the `~0.3`
            candidate set already.

            One edge per pair. `method` records the strongest rule that fired,
            `methods` all of them -- without the list, ablating a rule would mean
            re-running the whole pass to learn what it contributed.
            """
            # Tokens must start with a letter and contain only alphanumerics:
            # anything else reaches Lucene as a malformed fuzzy term and throws
            # a ParseException. Purely numeric tokens like the 1023 of
            # `1023 ENTERPRISES LLC` are the common case, and they carry no
            # identifying weight anyway.
            query = """
            UNWIND $batch as item
            MATCH (o:Organization {id: item.id})
            SET o:RecordProcessed
            WITH o,
                trim(apoc.text.replace(o.name, '(?i)\\b(?:co|ltd|inc|corp|llc|llp|pvt|gmbh|s.a.|s.l.|and|not)\\b', '')) as clean_name
            WITH o, clean_name,
                apoc.text.split(apoc.text.replace(clean_name, '[^a-zA-Z0-9\\s]', ''), "\\s+") as name_words
            WITH o, clean_name,
                [x IN name_words WHERE size(trim(x)) > 2 AND trim(x) IS NOT NULL
                 AND trim(x) =~ '^[A-Za-z][A-Za-z0-9]*$'
                 AND NOT toUpper(trim(x)) IN $stopwords] as valid_name_words
            WHERE size(valid_name_words) > 0
            CALL db.index.fulltext.queryNodes(
                "organization_name",
                apoc.text.join([x IN valid_name_words | trim(x) + "~0.3"], " AND ")
            )
            YIELD node, score
            WHERE node <> o AND NOT EXISTS ((node)-[:IS_SIMILAR_TO]-(o))
            WITH o, clean_name, node,
                trim(apoc.text.replace(node.name, '(?i)\\b(?:co|ltd|inc|corp|llc|llp|pvt|gmbh|s.a.|s.l.|and|not)\\b', '')) as clean_node_name
            WITH o, node,
                apoc.text.sorensenDiceSimilarity(clean_name, clean_node_name) as simil
            WHERE simil > 0.3

            // An organisation can carry several addresses, so the signals are
            // compared as sets: a plain MATCH would multiply the rows.
            WITH o, node, simil,
                 [(o)-[:HAS_ADDRESS]->(a) | a.id]                   AS addrO,
                 [(node)-[:HAS_ADDRESS]->(a) | a.id]                AS addrN,
                 [(o)-[:HAS_ADDRESS]->(a) | a.addressPostalCode]    AS zipO,
                 [(node)-[:HAS_ADDRESS]->(a) | a.addressPostalCode] AS zipN,
                 size([(o)<-[:WORKS_FOR_ORG]-(p)-[:WORKS_FOR_ORG]->(node) | p]) AS sharedPeople
            WITH o, node, simil, sharedPeople,
                 size(apoc.coll.intersection(addrO, addrN)) > 0 AS sameAddress,
                 size(apoc.coll.intersection(
                     [x IN addrO | toUpper(trim(apoc.text.replace(apoc.text.replace(x, __UNIT_RE__, ''), '\\s+', ' ')))],
                     [x IN addrN | toUpper(trim(apoc.text.replace(apoc.text.replace(x, __UNIT_RE__, ''), '\\s+', ' ')))]
                 )) > 0 AS normAddress,
                 size(apoc.coll.intersection(zipO, zipN)) > 0 AS sameZip

            WITH o, node, simil,
                 [m IN [
                     CASE WHEN sameAddress AND simil >= 0.3 THEN 'SAME_ADDRESS' END,
                     CASE WHEN normAddress AND simil >= 0.5 THEN 'NORM_ADDRESS' END,
                     CASE WHEN sameZip     AND simil >= 0.8 THEN 'SAME_ZIP' END,
                     CASE WHEN sharedPeople >= 2 AND simil >= 0.5 THEN 'SHARED_PEOPLE' END
                 ] WHERE m IS NOT NULL] AS methods
            WHERE size(methods) > 0
            MERGE (node)-[r:IS_SIMILAR_TO]->(o)
            ON CREATE SET r.score = simil,
                          r.method = methods[0],
                          r.methods = methods
            """.replace("__UNIT_RE__", UNIT_RE)
            stopwords = self.compute_stopwords()
            # The stoplist is pasted into the query text with str(), not passed
            # as a parameter. It holds because the tokens are alphanumeric by
            # construction -- compute_stopwords strips everything else and drops
            # anything shorter than three characters. If that ever stops being
            # true the result is invalid Cypher and a failed batch, which is the
            # loud way to fail, not the silent one.
            query = query.replace('$stopwords', str(stopwords))
            # TODO: the progress total counts every unprocessed organisation
            # while the generator below honours `nodes`. Harmless today, because
            # nothing calls this with a node list; wrong the moment something
            # does.
            size = self.count_record_rows()
            self.batch_store(query, self.get_record_rows(nodes), size=size)

        def project_graph(self, node_label='Organization'):
            """Weighted, undirected projection: Louvain needs the similarity score."""
            query = """
            MATCH (source:Organization)-[r:IS_SIMILAR_TO]->(target:Organization)
            RETURN gds.graph.project(
                'organizationResolved',
                source,
                target,
                { relationshipProperties: r { .score } },
                { undirectedRelationshipTypes: ['*'] }
            )
            """
            with self._driver.session(database=self._database) as session:
                session.run(query)

        def run_louvain(self):
            """Communities, not connected components -- see decision 12.

            WCC ignores weights: a chain of weak edges swallows everything it
            touches. Measured 12/8 on the group that named itself `M & A INC`:
            661 organisations, 1,510 edges, density 0.0069, average degree 4.6.
            Sparse and chain-like, which is exactly the shape WCC merges and
            Louvain cuts -- companies sharing only the word ENTERPRISES and a
            postcode, linked one to the next until the component held 661 firms
            that have nothing to do with each other.
            """
            query = """
            CALL gds.louvain.write('organizationResolved', {
                relationshipWeightProperty: 'score',
                writeProperty: 'louvainLevels',
                includeIntermediateCommunities: true,
                concurrency: 1
            })
            YIELD communityCount, modularity
            RETURN communityCount, modularity
            """
            with self._driver.session(database=self._database) as session:
                session.run(query)

        def set_cluster_key(self):
            """Finest Louvain level, and an entity of its own for the unmatched.

            Same reasoning as people_cluster: Louvain climbs to maximise
            modularity, which rewards large well-separated communities, while we
            want firms -- small dense groups of near-identical records. Keep the
            first pass, discard the aggregations above it.
            """
            query = """
            MATCH (o:Organization)
            WITH o, toIntegerList(o.louvainLevels) AS levels
            SET o.louvainFinest   = CASE WHEN levels IS NOT NULL THEN levels[0] ELSE NULL END,
                o.louvainCoarsest = CASE WHEN levels IS NOT NULL THEN levels[-1] ELSE NULL END,
                o.clusterKey      = CASE
                    WHEN levels IS NOT NULL THEN 'L' + toString(levels[0])
                    ELSE 'R' + toString(o.id)
                END
            """
            with self._driver.session(database=self._database) as session:
                session.run(query)

        def delete_projection(self):
            query = "CALL gds.graph.drop('organizationResolved')"
            with self._driver.session(database=self._database) as session:
                session.run(query)

        def create_record_clusters(self):
            query = """
            CALL apoc.periodic.iterate(
"MATCH (n:Organization) RETURN DISTINCT n.clusterKey as id",
                \"MERGE (n:OrganizationGroup {clusterId: id})\",
                {batchSize:10000})
            YIELD batches, total RETURN batches, total
            """
            with self._driver.session(database=self._database) as session:
                session.run(query)

        def create_connections_to_clusters(self):
            query = """
            UNWIND $batch as item
            MATCH (p:Organization {clusterKey: item.id})
            MATCH (c:OrganizationGroup {clusterId: item.id})
            MERGE (p)-[:BELONGS_TO_ORG_GROUP]->(c)
            SET c.ids = apoc.coll.toSet(coalesce(c.ids, []) + coalesce(toString(p.id), [])),
                c.names = apoc.coll.toSet(coalesce(c.names, []) + coalesce(p.name, [])),
                c.sources = apoc.coll.toSet(coalesce(c.sources, []) + coalesce(p.source, []))
            """
            size = self.count_cluster_rows()
            self.batch_store(query, self.get_cluster_rows(), size=size)

        def create_final_names_of_clusters(self):
            # Shortest of the names wins -- see contracts.py
            # merge_vendors_and_orders() for why, and for what it costs.
            query = """
            UNWIND $batch as item
            MATCH (c:OrganizationGroup {clusterId: item.id})
            WITH c, reduce(shortest = head(c.names), name IN c.names | CASE WHEN size(name) < size(shortest) THEN name ELSE shortest END) AS shortestName
            SET c.name = shortestName
            """
            size = self.count_cluster_rows()
            self.batch_store(query, self.get_cluster_rows(), size=size)
        
        def apply_updates(self):
            logging.info("Creating similarity IS_SIMILAR_TO relationships...")
            self.create_org_similarity()
            
            logging.info("Creating graph projection...")
            self.project_graph()
            
            logging.info("Running Louvain algorithm...")
            self.run_louvain()

            logging.info("Assigning cluster keys...")
            self.set_cluster_key()
            
            logging.info("Deleting projection...")
            self.delete_projection()
            
            logging.info("Creating organization clusters...")
            self.create_record_clusters()
            
            logging.info("Creating connections to clusters...")
            self.create_connections_to_clusters()
            
            logging.info("Creating cluster names...")
            self.create_final_names_of_clusters()

    return ChicagoOrgsSimilarity

if __name__ == '__main__':
    from util.cli_entry import run_backend_importer

    run_backend_importer(
        chi_orgs_similarity_factory,
        description="Run Chicago Organization Similarity pipeline with selected backend.",
        file_help="No file needed.",
        default_base_path="./data/",
        require_file=False
    )