"""Departments resolved by hand, because there are few enough to list.

Contracts and payroll name the same body differently -- `DEPT OF LAW` against
`DEPARTMENT OF LAW` -- and neither source carries a department identifier. With
72 spellings on one side and 39 on the other the whole mapping fits on a screen,
so it is written out instead of computed: no threshold to defend, and the errors
are the ones a reader can see rather than the ones an algorithm hides.

A DepartmentGroup is attached with BELONGS_TO_ORG_GROUP, not with a name of its
own. The relationship type is shared with orgs_cluster, so a query looking for
departments has to ask for the organisation edge, and renaming it here would
leave every existing query matching nothing.
"""


def manual_match_factory(base_importer_cls, backend: str):
    import logging

    class ManualDepartmentMatcher(base_importer_cls):
        def __init__(self):
            super().__init__()
            self.backend = backend
        
        def get_cluster_rows(self):
            query = "MATCH (n:DepartmentGroup) RETURN DISTINCT n.clusterId as id"
            with self._driver.session(database=self._database) as session:
                result = session.run(query)
                for record in iter(result):
                    yield dict(record)

        def count_cluster_rows(self):
            query = "MATCH (n:DepartmentGroup) RETURN COUNT(DISTINCT n.clusterId) as rows"
            with self._driver.session(database=self._database) as session:
                return session.run(query).single()["rows"]

        def expand_department_pairs(self):
            """Expand the hand-written pairs into one row per link.

            The left value is a payroll spelling, the right one or more contract
            spellings separated by `|`. An empty side is skipped, which is how
            a department with no counterpart is expressed.

            The query needs both MATCHes to hit. A pair naming a department that
            is in neither source produces no edge, no warning and no trace in
            any count, so the list cannot be checked by reading the results --
            only by reading the list.

            A wrong pair costs more than one wrong edge: WCC merges whatever is
            connected, so two bad links in a chain collapse three departments
            into one DepartmentGroup.

            # TODO(A13): the list has both defects today.
            """
            raw_pairs = [
                ("DEPARTMENT OF BUILDINGS", "DEPARTMENT OF CONSTRUCTION AND PERMITS"),
                ("DEPARTMENT OF FINANCE", "FINANCE GENERAL"),
                ("DEPARTMENT OF LAW", "DEPT OF LAW"),
                ("DEPARTMENT OF CULTURAL AFFAIRS AND SPECIAL EVENTS", "DEPARTMENT OF SPECIAL EVENTS|OFFICE OF SPECIAL EVENTS|DEPARTMENT OF CULTURAL AFFAIRS"),
                ("OFFICE OF PUBLIC SAFETY ADMINISTRATION", ""),
                ("DEPARTMENT OF HUMAN RESOURCES", "DEPARTMENT OF HUMAN SERVICES"),
                ("DEPARTMENT OF ENVIRONMENT", "DEPARTMENT OF ENVIROMENT"),
                ("CHICAGO POLICE DEPARTMENT", "POLICE BOARD"),
                ("CHICAGO DEPARTMENT OF PUBLIC HEALTH", "DEPARTMENT OF HEALTH"),
                ("CHICAGO DEPARTMENT OF AVIATION", "DEPT OF AVIATION"),
                ("CHICAGO FIRE DEPARTMENT", "FIRE DEPARTMENT"),
                ("DEPARTMENT OF STREETS AND SANITATION", "DEPT OF STREETS & SANITATION"),
                ("DEPARTMENT OF FAMILY AND SUPPORT SERVICES", "DEPT OF FAMILY AND SUPPORT SERVICES"),
                ("DEPARTMENT OF FLEET AND FACILITY MANAGEMENT", "DEPT OF FLEET MGMT|DEPT OF FLEET AND FACILITY MANAGEMENT"),
                ("OFFICE OF EMERGENCY MANAGEMENT AND COMMUNICATIONS", "OFFICE OF EMERGENCY COMMUNICATION"),
                ("CIVILIAN OFFICE OF POLICE ACCOUNTABILITY", "INDEPENDENT POLICE REVIEW AUTHORITY"),
                ("DEPARTMENT OF BUSINESS AFFAIRS AND CONSUMER PROTECTION", "DEPT OF BUSINESS AFFAIRS & CONSUMER PROTECTION"),
                ("BOARD OF ELECTION COMMISSIONERS", "BOARD OF ELECTION COMMISSIONER"),
                ("DEPARTMENT OF TECHNOLOGY AND INNOVATION", "DEPT OF INNOVATION & TECHNOLOGY"),
                ("DEPARTMENT OF PLANNING AND DEVELOPMENT", "PLANNING & DEVELOPMENT"),
                ("COMMUNITY COMMISSION FOR PUBLIC SAFETY AND ACCOUNTABILITY", "OFFICE FOR PEOPLE WITH DISABILITIES"),
                ("OFFICE OF CITY CLERK", "CITY CLERK"),
                ("CHICAGO ANIMAL CARE AND CONTROL", "COMM ON ANIMAL CARE & CONTROL"),
                ("DEPARTMENT OF PROCUREMENT SERVICES", "DEPT OF PROCUREMENT SERVICES"),
                ("CHICAGO COMMISSION ON HUMAN RELATIONS", "COMMISSION ON HUMAN RELATIONS"),
                ("CITY TREASURER'S OFFICE", "CITY TREASURER"),
                ("DEPARTMENT OF ADMINISTRATIVE HEARING", "DEPARTMENT OF ADMINISTRATIVE HEARINGS"),
                ("CHICAGO POLICE BOARD", "POLICE BOARD"),
            ]
            for source, targets in raw_pairs:
                if not source or not targets:
                    continue
                for target in targets.split('|'):
                    yield{
                        "source": source.strip(),
                        "target": target.strip()
                    }


        def existing_departments(self):
            query = "MATCH (d:Department) RETURN collect(d.id) AS ids"
            with self._driver.session(database=self._database) as session:
                return set(session.run(query).single()["ids"])

        def create_manual_similarity_relationships(self):
            """Link the pairs whose two departments both exist, and print the rest.

            Both MATCHes have to hit. A pair naming a department the graph does
            not have produces no edge and no error, so the list would look
            applied while part of it did nothing at all -- and the only way to
            notice was to read the list against the sources by hand.

            Checking the names first does not make those pairs work: it makes
            them visible. A name that is absent is either a spelling the sources
            never used or one they stopped using, and both are corrections to
            the list, not to this code.

            This says nothing about the second defect. A pair joining two
            departments that both exist but are not the same body passes every
            check here and is merged, and WCC then chains whatever is connected.
            That one is only found by reading the pairs -- see A13.
            """
            known = self.existing_departments()
            pairs, dropped = [], []
            for pair in self.expand_department_pairs():
                missing = [name for name in (pair["source"], pair["target"])
                           if name not in known]
                if missing:
                    dropped.append((pair, missing))
                else:
                    pairs.append(pair)

            if dropped:
                total = len(pairs) + len(dropped)
                print(f"\n*** {len(dropped)} of {total} pairs name a department that is "
                      f"not in the graph. They are skipped. ***")
                for pair, missing in dropped:
                    print(f"    {pair['source']} -> {pair['target']}")
                    print(f"        not found: {', '.join(missing)}")

            logging.info(f"Linking {len(pairs)} pairs of {len(pairs) + len(dropped)}")
            query = """
            UNWIND $batch as item
            MATCH (a:Department) WHERE a.id = item.source
            MATCH (b:Department) WHERE b.id = item.target AND a <> b
            MERGE (a)-[r:IS_SIMILAR_TO {method: "MANUAL_MATCH"}]->(b)
            ON CREATE SET r.score = 1.0
            """
            self.batch_store(query, iter(pairs), len(pairs))
        
        def project_graph(self, node_label='Department'):
            query = """
            CALL gds.graph.project(
                'departmentResolved',
                [$node_label],
                ['IS_SIMILAR_TO']
            )
            YIELD graphName, nodeCount, relationshipCount
            RETURN graphName, nodeCount, relationshipCount
            """
            with self._driver.session(database=self._database) as session:
                session.run(query, {"node_label": node_label})

        def run_wcc(self):
            query = """
            CALL gds.wcc.write('departmentResolved', { writeProperty: 'componentId' })
            YIELD nodePropertiesWritten, componentCount;
            """
            with self._driver.session(database=self._database) as session:
                session.run(query)

        def delete_projection(self):
            query = "CALL gds.graph.drop('departmentResolved')"
            with self._driver.session(database=self._database) as session:
                session.run(query)

        def create_record_clusters(self):
            query = """
            CALL apoc.periodic.iterate(
                \"MATCH (n:Department) RETURN DISTINCT n.componentId as id\",
                \"MERGE (n:DepartmentGroup {clusterId: id})\",
                {batchSize:10000})
            YIELD batches, total RETURN batches, total
            """
            with self._driver.session(database=self._database) as session:
                session.run(query)

        def create_connections_to_clusters(self):
            query = """
            UNWIND $batch as item
            MATCH (p:Department {componentId: item.id})
            MATCH (c:DepartmentGroup {clusterId: item.id})
            MERGE (p)-[:BELONGS_TO_ORG_GROUP]->(c)
            SET c.ids = apoc.coll.toSet(coalesce(c.ids, []) + coalesce(toString(p.id), [])),
                c.sources = apoc.coll.toSet(coalesce(c.sources, []) + coalesce(p.source, []))
            """
            size = self.count_cluster_rows()
            self.batch_store(query, self.get_cluster_rows(), size=size)

        def create_final_names_of_clusters(self):
            query = """
            UNWIND $batch as item
            MATCH (c:DepartmentGroup {clusterId: item.id})
            WITH c, reduce(shortest = head(c.ids), name IN c.ids | CASE WHEN size(name) < size(shortest) THEN name ELSE shortest END) AS shortestName
            SET c.name = shortestName
            """
            size = self.count_cluster_rows()
            self.batch_store(query, self.get_cluster_rows(), size=size)

        def apply_updates(self):
            
            logging.info("Creating manual similarity relationships from hardcoded pairs...")
            self.create_manual_similarity_relationships()

            logging.info("Creating graph projection...")
            self.project_graph()
            
            logging.info("Running WCC algorithm...")
            self.run_wcc()
            
            logging.info("Deleting projection...")
            self.delete_projection()
            
            logging.info("Creating organization clusters...")
            self.create_record_clusters()
            
            logging.info("Creating connections to clusters...")
            self.create_connections_to_clusters()
            
            logging.info("Creating cluster names...")
            self.create_final_names_of_clusters()

    return ManualDepartmentMatcher

if __name__ == '__main__':
    from util.cli_entry import run_backend_importer

    run_backend_importer(
        manual_match_factory,
        description="Manually link department pairs with IS_SIMILAR_TO relationships.",
        file_help="No file needed.",
        default_base_path="./data/chicago/",
        require_file=False
    )