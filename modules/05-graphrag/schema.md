# Graph schema

Generated from the database. Every figure is measured; nothing here is a design intention.

<!-- nodes: 3026400 -->

## Node labels

### Address

210,078 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| id | 210,078 | 100% | **unique** — usable as an identifier |
| addressPostalCode | 5,376 | 100% | categorical — 5,376 values |
| addressState | 66 | 100% | categorical — 66 values |
| addressCity | 2,790 | 100% | categorical — 2,790 values |
| latitude | 86,882 | 83% | categorical — 86,882 values |
| longitude | 86,881 | 83% | categorical — 86,881 values |

### Certification

6 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| id | 6 | 100% | 6 value(s) — too few nodes to judge |
| source | 1 | 100% | 1 value(s) — too few nodes to judge |
| name | 6 | 100% | 6 value(s) — too few nodes to judge |

### Claim

1,185 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| id | 1,185 | 100% | **unique** — usable as an identifier |
| source | 1 | 100% | one of `document` |
| page | 125 | 100% | categorical — 125 values |
| doc | 999 | 100% | categorical — 999 values |
| date | 473 | 100% | categorical — 473 values |
| kind | 4 | 100% | one of `department-lineage`, `same-organization`, `specification-mismatch`, `contract-lineage` |
| edgeType | 3 | 85% | one of `SUCCEEDED_BY`, `SAME_AS`, `SUPERSEDES` |
| subject | 477 | 100% | categorical — 477 values |
| objects | 455 | 100% | categorical — 455 values |

### ComplianceAudit

10 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| id | 10 | 100% | 10 value(s) — too few nodes to judge |
| source | 1 | 100% | 1 value(s) — too few nodes to judge |
| status | 3 | 60% | 3 value(s) — too few nodes to judge |
| page | 7 | 100% | 7 value(s) — too few nodes to judge |
| doc | 9 | 100% | 9 value(s) — too few nodes to judge |
| goalPercent | 10 | 100% | 10 value(s) — too few nodes to judge |
| creditPercent | 8 | 80% | 8 value(s) — too few nodes to judge |
| award | 8 | 80% | 8 value(s) — too few nodes to judge |
| totalPaid | 8 | 80% | 8 value(s) — too few nodes to judge |
| progress | 7 | 70% | 7 value(s) — too few nodes to judge |
| prime | 7 | 80% | 7 value(s) — too few nodes to judge |

### Contract

88,916 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| id | 88,916 | 100% | **unique** — usable as an identifier |
| name | 34,868 | 100% | categorical — 34,868 values |
| names | 34,868 | 100% | categorical — 34,868 values |
| startDate | 6,079 | 78% | categorical — 6,079 values |
| endDate | 6,143 | 79% | categorical — 6,143 values |

### ContractDescription

917 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| id | 917 | 100% | **unique** — usable as an identifier |
| text | 858 | 100% | **almost unique** — 59 repeat, so filtering by it can return more than one node |
| tier | 2 | 100% | one of `T2`, `T1` |
| builtFrom | 9 | 100% | one of `['modification']`, `['contract_summary']`, `['contract_summary', 'modification']`, `['ordinance']`, `['ordinance', 'summary']`, `['contract_summary', 'modification', 'summary']`, `['contract_summary', 'summary']`, `['modification', 'summary']`, `['summary']` |
| sourceDocuments | 872 | 100% | **almost unique** — 45 repeat, so filtering by it can return more than one node |
| incorporatesByReference | 2 | 100% | one of `True`, `False` |
| embedding | 128 | 14% | categorical — 128 values |
| neighbourText | 128 | 14% | categorical — 128 values |
| neighbourEmbedding | 129 | 14% | categorical — 129 values |

### ContractRecord

185,730 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| id | 185,730 | 100% | **unique** — usable as an identifier |
| source | 1 | 100% | one of `CONTRACTS` |
| contractId | 88,916 | 100% | categorical — 88,916 values |
| name | 37,109 | 99% | categorical — 37,109 values |
| amount | 74,536 | 100% | categorical — 74,536 values |
| approvalDateRaw | 8,469 | 100% | categorical — 8,469 values |
| approvalDate | 8,469 | 100% | categorical — 8,469 values |
| vendorId | 14,094 | 100% | categorical — 14,094 values |
| specificationId | 40,626 | 93% | categorical — 40,626 values |
| startDateRaw | 6,197 | 65% | categorical — 6,197 values |
| endDateRaw | 8,046 | 65% | categorical — 8,046 values |
| startDate | 6,197 | 65% | categorical — 6,197 values |

### ContractType

55 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| id | 55 | 100% | **unique** — usable as an identifier |

### Department

76 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| id | 76 | 100% | **unique** — usable as an identifier |
| source | 2 | 100% | one of `CONTRACTS`, `EMPLOYEES` |
| componentId | 63 | 100% | categorical — 63 values |

### DepartmentGroup

63 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| clusterId | 63 | 100% | **unique** — usable as an identifier |
| name | 63 | 100% | **unique** — usable as an identifier |
| ids | 63 | 100% | **unique** — usable as an identifier |
| sources | 3 | 100% | one of `['CONTRACTS']`, `['EMPLOYEES', 'CONTRACTS']`, `['EMPLOYEES']` |

### Document

14,499 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| id | 14,499 | 100% | **unique** — usable as an identifier |
| source | 1 | 100% | one of `CONTRACTS` |
| poNumber | 9,225 | 100% | categorical — 9,225 values |
| url | 14,499 | 100% | **unique** — usable as an identifier |
| revision | 116 | 100% | categorical — 116 values |
| hasTextLayer | 2 | 100% | one of `False`, `True` |
| collections | 3 | 100% | one of `['corpus_manifest.csv', '2022-2026/manifest.csv']`, `['corpus_manifest.csv']`, `['2022-2026/manifest.csv']` |

### Evidence

1,185 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| id | 1,185 | 100% | **unique** — usable as an identifier |
| source | 1,084 | 100% | **almost unique** — 101 repeat, so filtering by it can return more than one node |
| kind | 1 | 100% | one of `document` |
| quote | 485 | 100% | categorical — 485 values |
| learnedOn | 1 | 100% | one of `2026-10-21` |

### LicenseRecord

1,203,437 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| id | 1,203,437 | 100% | **unique** — usable as an identifier |
| source | 1 | 100% | one of `LICENSES` |
| name | 193,419 | 100% | categorical — 193,419 values |
| startDate | 6,380 | 100% | categorical — 6,380 values |
| endDate | 3,958 | 100% | categorical — 3,958 values |
| addressPostalCode | 3,543 | 100% | categorical — 3,543 values |
| addressState | 56 | 100% | categorical — 56 values |
| addressCity | 2,435 | 100% | categorical — 2,435 values |
| license_id | 1,203,437 | 100% | **unique** — usable as an identifier |
| businessName | 222,911 | 100% | categorical — 222,911 values |
| businessId | 196,646 | 100% | categorical — 196,646 values |
| address | 198,616 | 100% | categorical — 198,616 values |

### LicenseType

150 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| id | 150 | 100% | **unique** — usable as an identifier |
| description | 150 | 100% | **unique** — usable as an identifier |

### Modification

2,312 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| id | 2,312 | 100% | **unique** — usable as an identifier |
| source | 1 | 100% | one of `DOC_MODIFICATION` |
| number | 2,312 | 100% | **unique** — usable as an identifier |
| page | 4 | 100% | one of `1`, `2`, `10`, `55` |
| doc | 1,952 | 100% | categorical — 1,952 values |
| date | 537 | 100% | categorical — 537 values |
| reason | 6 | 96% | one of `DOLLAR AMOUNT CHANGE`, `TIME EXTENSION`, `VLI & TIME EXTENSION`, `SCOPE CHANGE`, `UNIT PRICE CHANGE`, `COST REDUCTION` |
| reasonRaw | 76 | 100% | categorical — 76 values |
| amounts | 510 | 100% | categorical — 510 values |

### Organization

212,009 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| id | 212,009 | 100% | **unique** — usable as an identifier |
| clusterKey | 198,064 | 99% | **almost unique** — 13,945 repeat, so filtering by it can return more than one node |
| source | 3 | 100% | one of `CONTRACTS`, `LICENSES`, `DOC_ORGANIZATION` |
| name | 207,238 | 100% | **almost unique** — 4,771 repeat, so filtering by it can return more than one node |
| names | 206,142 | 99% | **almost unique** — 5,867 repeat, so filtering by it can return more than one node |
| addresses | 178,239 | 99% | categorical — 178,239 values |
| addressPostalCodes | 14,941 | 99% | categorical — 14,941 values |
| addressStates | 344 | 99% | categorical — 344 values |
| addressCities | 4,685 | 99% | categorical — 4,685 values |
| louvainLevels | 8,826 | 10% | categorical — 8,826 values |
| louvainFinest | 8,826 | 10% | categorical — 8,826 values |
| louvainCoarsest | 8,469 | 10% | categorical — 8,469 values |

### OrganizationGroup

198,064 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| clusterId | 198,064 | 100% | **unique** — usable as an identifier |
| name | 195,817 | 100% | **almost unique** — 2,247 repeat, so filtering by it can return more than one node |
| names | 196,087 | 100% | **almost unique** — 1,977 repeat, so filtering by it can return more than one node |
| ids | 198,064 | 100% | **unique** — usable as an identifier |
| sources | 3 | 100% | one of `['CONTRACTS']`, `['CONTRACTS', 'LICENSES']`, `['LICENSES']` |

### Page

279,017 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| id | 279,017 | 100% | **unique** — usable as an identifier |
| page | 1,713 | 100% | categorical — 1,713 values |
| withheld | 2 | 100% | one of `False`, `True` |
| text | 170,569 | 99% | categorical — 170,569 values |
| nChars | 7,330 | 99% | categorical — 7,330 values |
| sha256 | 170,569 | 99% | categorical — 170,569 values |
| flags | 4 | 99% | one of `[]`, `['ocr_degraded']`, `['dup_overlay_suspect']`, `['dup_overlay_suspect', 'ocr_degraded']` |
| embedding | 75,133 | 33% | categorical — 75,133 values |
| collections | 3 | 100% | one of `['corpus_manifest.csv', '2022-2026/manifest.csv']`, `['corpus_manifest.csv']`, `['2022-2026/manifest.csv']` |

### Person

215,393 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| clusterId | 215,393 | 100% | **unique** — usable as an identifier |
| name | 204,824 | 95% | **almost unique** — 10,569 repeat, so filtering by it can return more than one node |
| method | 1 | 100% | one of `louvain-finest` |
| fullNames | 204,824 | 95% | **almost unique** — 10,569 repeat, so filtering by it can return more than one node |
| titles | 15,994 | 100% | categorical — 15,994 values |
| employerIds | 160,214 | 90% | categorical — 160,214 values |

### PersonRecord

372,585 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| id | 372,585 | 100% | **unique** — usable as an identifier |
| clusterKey | 215,393 | 97% | categorical — 215,393 values |
| wccCommunity | 206,310 | 97% | categorical — 206,310 values |
| fullName | 270,611 | 97% | categorical — 270,611 values |
| firstName | 42,482 | 94% | categorical — 42,482 values |
| lastName | 91,526 | 94% | categorical — 91,526 values |
| middleName | 9,159 | 44% | categorical — 9,159 values |
| source | 10 | 100% | one of `DOC_BUYER`, `DOC_CHIEF_PROCUR`, `DOC_CITY_CONTACT`, `DOC_COMMISSIONER`, `DOC_EDS`, `DOC_MAILBOX`, `DOC_MODIFICATION`, `DOC_VENDOR_CONTACT`, `EMPLOYEES`, `OWNERS` |
| title | 1,947 | 99% | categorical — 1,947 values |
| louvainLevels | 61,584 | 56% | categorical — 61,584 values |
| louvainFinest | 61,584 | 56% | categorical — 61,584 values |
| louvainCoarsest | 52,655 | 56% | categorical — 52,655 values |

### ProcurementType

15 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| id | 15 | 100% | 15 value(s) — too few nodes to judge |

### Program

68 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| id | 68 | 100% | **unique** — usable as an identifier |
| source | 1 | 100% | one of `DOCUMENTS` |
| name | 68 | 100% | **unique** — usable as an identifier |
| names | 68 | 100% | **unique** — usable as an identifier |

### ReasonCode

6 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| id | 6 | 100% | 6 value(s) — too few nodes to judge |
| source | 1 | 100% | 1 value(s) — too few nodes to judge |
| name | 6 | 100% | 6 value(s) — too few nodes to judge |

### RecordProcessed

539,315 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| id | 539,315 | 100% | **unique** — usable as an identifier |
| clusterKey | 380,146 | 100% | categorical — 380,146 values |
| wccCommunity | 196,191 | 65% | categorical — 196,191 values |
| fullName | 268,759 | 65% | categorical — 268,759 values |
| firstName | 42,482 | 65% | categorical — 42,482 values |
| lastName | 91,526 | 65% | categorical — 91,526 values |
| middleName | 9,159 | 30% | categorical — 9,159 values |
| source | 4 | 100% | one of `EMPLOYEES`, `CONTRACTS`, `OWNERS`, `LICENSES` |
| title | 1,219 | 65% | categorical — 1,219 values |
| louvainLevels | 70,410 | 42% | categorical — 70,410 values |
| louvainFinest | 68,208 | 42% | categorical — 68,208 values |
| louvainCoarsest | 59,835 | 42% | categorical — 59,835 values |

### Specification

40,624 nodes

| property | distinct | present | note |
|---|---:|---:|---|
| id | 40,624 | 100% | **unique** — usable as an identifier |
| source | 1 | 100% | one of `CONTRACTS` |

## Relationships

Direction matters and Neo4j will not warn you: a pattern written the wrong way round is legal, matches nothing, and returns no error.

| pattern | count | per start node |
|---|---:|---|
| `(Claim)-[:ABOUT]->(Contract)` | 1,185 | avg 1.00, max 1 |
| `(ComplianceAudit)-[:EXTRACTED_FROM]->(Page)` | 10 | avg 1.00, max 1 |
| `(Contract)-[:AWARDED_UNDER]->(Specification)` | 80,223 | avg 1.00, max 4 |
| `(Contract)-[:HAS_DESCRIPTION]->(ContractDescription)` | 917 | avg 1.00, max 1 |
| `(Contract)-[:HAS_VENDOR]->(Organization)` | 88,916 | avg 1.01, max 3 |
| `(Contract)-[:HAS_VENDOR]->(RecordProcessed)` | 81,742 | avg 1.01, max 3 |
| `(Contract)-[:PART_OF_PROGRAM]->(Program)` | 88 | avg 1.00, max 1 |
| `(ContractRecord)-[:HAS_CONTRACT_TYPE]->(ContractType)` | 141,139 | avg 1.00, max 1 |
| `(ContractRecord)-[:HAS_DOCUMENT]->(Document)` | 14,502 | avg 1.00, max 1 |
| `(ContractRecord)-[:HAS_PROCUREMENT_TYPE]->(ProcurementType)` | 55,152 | avg 1.00, max 1 |
| `(ContractRecord)-[:INCLUDED_IN_CONTRACT]->(Contract)` | 185,730 | avg 1.00, max 1 |
| `(ContractRecord)-[:RECORDED_DEPARTMENT]->(Department)` | 175,111 | avg 1.00, max 1 |
| `(ContractRecord)-[:RECORDED_SPECIFICATION]->(Specification)` | 159,674 | avg 1.00, max 1 |
| `(ContractRecord)-[:RECORDED_VENDOR]->(Organization)` | 185,730 | avg 1.00, max 1 |
| `(ContractRecord)-[:RECORDED_VENDOR]->(RecordProcessed)` | 171,838 | avg 1.00, max 1 |
| `(Department)-[:ASSIGNS_CONTRACT]->(Contract)` | 72 | avg 1201.86, max 16964 |
| `(Department)-[:BELONGS_TO_ORG_GROUP]->(DepartmentGroup)` | 76 | avg 1.00, max 1 |
| `(Department)-[:IS_SIMILAR_TO]->(Department)` | 11 | avg 1.18, max 3 |
| `(Document)-[:HAS_PAGE]->(Page)` | 8,332 | avg 33.49, max 1635 |
| `(Evidence)-[:CITES]->(Page)` | 1,185 | avg 1.00, max 1 |
| `(Evidence)-[:SUPPORTS]->(Claim)` | 1,185 | avg 1.00, max 1 |
| `(LicenseRecord)-[:HAS_LICENSE_TYPE]->(LicenseType)` | 1,203,437 | avg 1.00, max 1 |
| `(Modification)-[:EXTRACTED_FROM]->(Page)` | 2,312 | avg 1.00, max 1 |
| `(Modification)-[:HAS_REASON]->(ReasonCode)` | 2,214 | avg 1.00, max 1 |
| `(Modification)-[:MODIFIES]->(ContractRecord)` | 2,312 | avg 1.00, max 1 |
| `(Modification)-[:MODIFIES_CONTRACT]->(Contract)` | 2,312 | avg 1.00, max 1 |
| `(Organization)-[:BELONGS_TO_ORG_GROUP]->(OrganizationGroup)` | 210,740 | avg 1.00, max 1 |
| `(Organization)-[:DISCLOSED_FOR]->(Contract)` | 1,168 | avg 2.48, max 60 |
| `(Organization)-[:HAS_ADDRESS]->(Address)` | 210,509 | avg 1.33, max 430 |
| `(Organization)-[:IS_SIMILAR_TO]->(Organization)` | 12,665 | avg 1.27, max 17 |
| `(Organization)-[:IS_SIMILAR_TO]->(RecordProcessed)` | 12,665 | avg 1.27, max 17 |
| `(Organization)-[:ORG_HAS_LICENSE]->(LicenseRecord)` | 196,646 | avg 6.12, max 3777 |
| `(Person)-[:WORKS_FOR_ORG]->(Organization)` | 193,848 | avg 1.48, max 217 |
| `(Person)-[:WORKS_FOR_ORG]->(RecordProcessed)` | 176,311 | avg 1.45, max 191 |
| `(PersonRecord)-[:ACTED_ON]->(Contract)` | 6,543 | avg 1.00, max 1 |
| `(PersonRecord)-[:EXTRACTED_FROM]->(Page)` | 10,891 | avg 1.00, max 1 |
| `(PersonRecord)-[:FILED_EDS_FOR]->(Organization)` | 4,096 | avg 1.00, max 1 |
| `(PersonRecord)-[:IS_SIMILAR_TO]->(PersonRecord)` | 192,159 | avg 3.72, max 147 |
| `(PersonRecord)-[:IS_SIMILAR_TO]->(RecordProcessed)` | 192,159 | avg 3.72, max 147 |
| `(PersonRecord)-[:RECORD_RESOLVED_TO]->(Person)` | 361,694 | avg 1.00, max 1 |
| `(PersonRecord)-[:WORKS_FOR_DEPARTMENT]->(Department)` | 31,760 | avg 1.00, max 1 |
| `(RecordProcessed)-[:BELONGS_TO_ORG_GROUP]->(OrganizationGroup)` | 187,740 | avg 1.00, max 1 |
| `(RecordProcessed)-[:HAS_ADDRESS]->(Address)` | 187,511 | avg 1.32, max 430 |
| `(RecordProcessed)-[:IS_SIMILAR_TO]->(PersonRecord)` | 192,159 | avg 3.72, max 147 |
| `(RecordProcessed)-[:IS_SIMILAR_TO]->(RecordProcessed)` | 202,814 | avg 3.59, max 147 |
| `(RecordProcessed)-[:IS_SIMILAR_TO]->(Organization)` | 10,655 | avg 1.26, max 17 |
| `(RecordProcessed)-[:ORG_HAS_LICENSE]->(LicenseRecord)` | 174,646 | avg 6.00, max 3777 |
| `(RecordProcessed)-[:RECORD_RESOLVED_TO]->(Person)` | 351,575 | avg 1.00, max 1 |
| `(RecordProcessed)-[:WORKS_FOR_DEPARTMENT]->(Department)` | 31,760 | avg 1.00, max 1 |
