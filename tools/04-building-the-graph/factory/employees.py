"""City employees: one PersonRecord per employee, attached to a Department.

Two things make this source different from Business Owners. The name arrives as
a single `LAST, GIVEN [GIVEN...] [I]` field and has to be split before it can be
normalised -- see split_name below, which is where the interesting failures are.

And the Department nodes created here carry the spellings used by the payroll,
which are not the spellings used by the contracts source: `DEPT OF LAW` against
`DEPARTMENT OF LAW`. Nothing reconciles them at load time; factory/dept_cluster
does it afterwards, from a hand-written list of pairs.
"""

from factory.naming import with_canonical_name


def chi_employees_importer_factory(base_importer_cls, backend: str):
    import logging

    class ChicagoEmployeesImporter(base_importer_cls):
        def __init__(self):
            super().__init__()
            self.backend = backend

        @staticmethod
        def get_csv_size(employees_file, encoding="utf-8"):
            return sum(1 for _ in ChicagoEmployeesImporter.get_rows(employees_file))

        @staticmethod
        def get_rows(employees_file):
            import numpy as np
            import pandas as pd
            employees = pd.read_csv(employees_file, low_memory=False)
            employees['DATA_SOURCE'] = "EMPLOYEES"
            employees['RECORD_TYPE'] = "PERSON"  # written, never read by any query
            if 'RECORD_ID' not in employees:
                # TODO(A10): positional id. See licenses.py get_rows() for why
                # the offsets keep the sources apart by margin rather than by
                # construction.
                employees.insert(0, 'RECORD_ID', range(4000000, 4000000 + len(employees)))

            def split_name(name):
                """Split 'LAST, GIVEN [GIVEN...] [I]' into given, middle, last.

                The trailing token is the middle initial when it is a single
                letter; whatever precedes it is the given name, which is often
                compound: 'LA VESHA N', 'MARY ANN C', 'MC KINLEY I',
                'JULIA RAYN C'.

                Taking the first token as the given name and the second as the
                middle name splits those compounds and throws away the real
                initial. That is 71 records out of 31,760 -- small, but not a
                random 71: compound given names cluster by origin, so the loss
                falls on one part of the population and not the rest.

                Four records carry no initial at all ('MARIA DE LOS ANGELES',
                'JOSE DE JESUS'): there the whole remainder is the given name.

                A trailing period is dropped so that 'JOSE A.' matches the
                unpunctuated initials that Business Owners provides.
                """
                if not isinstance(name, str):
                    return pd.Series([None, None, None])
                parts = name.split(',')
                last = parts[0].strip()
                rest = parts[1].split() if len(parts) > 1 else []
                if not rest:
                    return pd.Series([None, None, last])
                if len(rest) > 1 and len(rest[-1].strip('.')) == 1:
                    return pd.Series([" ".join(rest[:-1]), rest[-1].strip('.'), last])
                return pd.Series([" ".join(rest), None, last])

            employees[['Owner First Name', 'Owner Middle Initial', 'Owner Last Name']] = employees['Name'].apply(split_name)
            employees.replace({np.nan: None}, inplace=True)
            for _, row in employees.iterrows():
                yield row.to_dict()

        def set_constraints(self):
            # Same PersonRecord block as owners.py, plus the Department
            # constraint this source needs. Kept in sync by hand -- see the note
            # there for what a divergence would look like.
            queries = [
                "CREATE CONSTRAINT person_id IF NOT EXISTS FOR (node:Person) REQUIRE node.clusterId IS UNIQUE",
                "CREATE CONSTRAINT person_record_id IF NOT EXISTS FOR (node:PersonRecord) REQUIRE node.id IS UNIQUE",
                "CREATE CONSTRAINT department_id IF NOT EXISTS FOR (node:Department) REQUIRE node.id IS UNIQUE",
                "CREATE INDEX person_record_cluster_key IF NOT EXISTS FOR (node:PersonRecord) ON (node.clusterKey)",
                "CREATE INDEX person_record_wcc IF NOT EXISTS FOR (node:PersonRecord) ON (node.wccCommunity)",
                "CREATE INDEX person_record_employer_id IF NOT EXISTS FOR (node:PersonRecord) ON (node.employerId)",
                "CREATE FULLTEXT INDEX person_record_fullName IF NOT EXISTS FOR (node:PersonRecord) ON EACH [node.fullName]"
            ]
            for query in queries:
                with self._driver.session(database=self._database) as session:
                    session.run(query)

        def import_people_records(self, employees_file):
            """Write one PersonRecord per employee, with their department.

            fullName comes from the shared expression in factory/naming.py, for
            the reason given in owners.py: two sources that normalise names
            differently never match each other, and nothing says so.

            The `Owner ...` columns read below are not columns of this CSV. They
            are the three produced by split_name from the single `Name` field,
            deliberately named after the Business Owners layout so that one
            canonical-name expression can serve both sources.

            Salary and hours hang off the WORKS_FOR_DEPARTMENT edge rather than
            off the record, because they describe the employment and not the
            person. The file is a snapshot with no dates in it, so the edge
            holds current terms only: re-importing overwrites them, and nothing
            in the graph will say the old value ever existed.
            """
            import_people_records_query = with_canonical_name(
                """
            UNWIND $batch as item
            MERGE (n:PersonRecord {id: item.RECORD_ID})
            SET n.firstName = coalesce(item.`Owner First Name`, NULL)
            SET n.lastName = coalesce(item.`Owner Last Name`, NULL)
            SET n.middleName = coalesce(item.`Owner Middle Initial`, NULL)
            SET n.fullName = __CANONICAL_NAME__
            SET n.source = item.DATA_SOURCE
            SET n.title = item.`Job Titles`

            MERGE (d:Department {id: item.Department})
            SET d.source = item.DATA_SOURCE

            MERGE (n)-[r:WORKS_FOR_DEPARTMENT]->(d)
            SET r.employmentType = item.`Full or Part-Time`
            SET r.salaryType = item.`Salary or Hourly`
            SET r.typicalHours = item.`Typical Hours`
            SET r.annualSalary = item.`Annual Salary`
            SET r.hourlyRate = item.`Hourly Rate`
            """,
                "item.`Owner First Name`",
                "item.`Owner Middle Initial`",
                "item.`Owner Last Name`",
            )

            size = self.get_csv_size(employees_file)
            self.batch_store(import_people_records_query, self.get_rows(employees_file), size=size)

        def import_data(self, employees_file):
            logging.info("Loading constraints and indexes for person records and entities...")
            self.set_constraints()

            logging.info("Loading person record nodes...")
            self.import_people_records(employees_file)

    return ChicagoEmployeesImporter

if __name__ == '__main__':
    from util.cli_entry import run_backend_importer

    run_backend_importer(
        chi_employees_importer_factory,
        description="Run Chicago Employee Importer with selected backend.",
        file_help="Path to the Employees CSV file",
        default_base_path="./data/"
    )