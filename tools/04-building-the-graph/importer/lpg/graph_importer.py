"""
Graph Database Importer Classes
Batch import functionality for: Neo4j, FalkorDB
"""

import re
from itertools import islice
from typing import Iterable

from tqdm import tqdm

from database.lpg.graph_db import Neo4jDB, FalkorDB


class Neo4jBaseImporter(Neo4jDB):
    """Batch importer for Neo4j."""
    
    def __init__(self):
        super().__init__()
        self.batch_size = 1000

    def batch_store(self, query: str, generator: Iterable, size: int = None, **kwargs):
        def batched(iterable, n):
            it = iter(iterable)
            while batch := list(islice(it, n)):
                yield batch

        # One failing batch must not abandon the rest. The try used to wrap the
        # whole loop, so a single bad row stopped every batch after it while the
        # caller carried on -- projections, clustering, the lot -- producing a
        # result that looked complete. Measured 12/8: an organisation whose name
        # broke the Lucene parser aborted the pass at 4,000 rows out of 210,740,
        # and the only trace was one printed line.
        failed, failures, seen_kinds = 0, [], set()
        with self._driver.session(database=self._database) as session:
            batches = batched(generator, self.batch_size)

            if size:
                total_batches = (size + self.batch_size - 1) // self.batch_size
                batches = tqdm(batches, total=total_batches, desc="Loading data into Neo4j...")
            else:
                batches = tqdm(batches, desc="Loading data into Neo4j...")

            for i, batch in enumerate(batches):
                if not batch:
                    continue
                try:
                    session.run(query, {"batch": batch})
                except Exception as e:
                    failed += 1
                    # Kept by kind rather than by arrival, and long enough to
                    # carry the cause. Measured 23/10/2026: 23 batches of ~211
                    # failed in the organisation pass and all five slots held
                    # the same Lucene ParseException, cut at 200 characters one
                    # token before it says what it encountered -- so the report
                    # proved something had gone wrong and nothing about what.
                    # 400 characters reaches `Encountered " <AND> "AND ""`,
                    # which names the offending term.
                    message = str(e)[:400]
                    kind = message.split("Caused by:")[-1][:120]
                    if kind not in seen_kinds and len(failures) < 5:
                        seen_kinds.add(kind)
                        failures.append(f"batch {i}: {message}")

        if failed:
            # Loud, and at the end, where it cannot scroll past unnoticed.
            print(f"\n*** {failed} batch(es) FAILED out of ~{total_batches if size else '?'}. "
                  f"The load is INCOMPLETE. ***")
            for f in failures:
                print(f"    {f}")
            if failed > len(failures):
                print(f"    ... and {failed - len(failures)} more, of these kinds "
                      f"or others not kept")

    def create_indices(self, indices):
        for index in indices:
            with self._driver.session(database=self._database) as session:
                session.run(index)


class FalkorDBBaseImporter(FalkorDB):
    """
    Batch importer for FalkorDB using parameterized UNWIND queries.
    
    FalkorDB supports parameterized UNWIND ($batch), but property names
    with spaces break in parameterized mode. This importer transparently:
    
    1. Sanitizes dict keys:  'Owner First Name' -> 'Owner_First_Name'
    2. Rewrites query refs:  item.`Owner First Name` -> item.Owner_First_Name
    3. Passes as parameter:  self._graph.query(query, {'batch': data})
    
    No changes needed in caller query strings — sanitization is automatic.
    
    Performance improvement based on recommendation from FalkorDB team.
    Previous approach: inline query string building (~5s for 100K rows)
    Current approach:  parameterized UNWIND (~3s for 100K rows, ~40% faster)
    """
    
    # Precompiled regex for backtick-quoted property references in queries
    # Matches: item.`Owner First Name`, item.`Purchase Order (Contract) Number`
    _BACKTICK_REF_RE = re.compile(r'(\w+)\.`([^`]+)`')
    
    # Regex for sanitizing property names
    _SANITIZE_RE = re.compile(r'[^a-zA-Z0-9_]')
    _MULTI_UNDERSCORE_RE = re.compile(r'_+')
    
    def __init__(self):
        super().__init__()
        self.batch_size = 5000  # 5x larger batches — parameterized queries handle it

    def batch_store(self, query: str, generator: Iterable, size: int = None, **kwargs):
        """
        Batch store data into FalkorDB using parameterized UNWIND queries.
        
        Transparently sanitizes property names so callers can keep using
        backtick-quoted field references (item.`Owner First Name`) — the
        sanitization happens here, not in the query generation code.
        
        Args:
            query: Cypher query with $batch parameter (UNWIND $batch AS item ...)
            generator: Iterable of data dictionaries  
            size: Total size for progress bar
        """
        def batched(iterable, n):
            it = iter(iterable)
            while batch := list(islice(it, n)):
                yield batch

        # Rewrite query once: item.`Owner First Name` -> item.Owner_First_Name
        sanitized_query = self._sanitize_query(query)

        try:
            batches = batched(generator, self.batch_size)

            if size:
                total_batches = (size + self.batch_size - 1) // self.batch_size
                batches = tqdm(batches, total=total_batches, desc="Loading data into FalkorDB...")
            else:
                batches = tqdm(batches, desc="Loading data into FalkorDB...")

            for batch in batches:
                if not batch:
                    continue
                
                # Sanitize dict keys to match rewritten query
                sanitized_batch = [self._sanitize_row(row) for row in batch]
                
                # Parameterized query — no inline string building
                self._graph.query(sanitized_query, {'batch': sanitized_batch})

        except Exception as e:
            print(f"Batch insert failed: {e}")

    # -----------------------------------------------------------------
    # Key / query sanitization
    # -----------------------------------------------------------------

    @classmethod
    def _sanitize_key(cls, name: str) -> str:
        """
        Sanitize a property name for FalkorDB parameterized queries.
        
        Replaces spaces, parentheses, and other non-identifier characters
        with underscores, then collapses runs of underscores.
        
        Examples:
            'Owner First Name'                   -> 'Owner_First_Name'
            'Purchase Order (Contract) Number'   -> 'Purchase_Order_Contract_Number'
            'Address 1'                          -> 'Address_1'
            'Full or Part-Time'                  -> 'Full_or_Part_Time'
            'RECORD_ID'                          -> 'RECORD_ID' (unchanged)
        """
        sanitized = cls._SANITIZE_RE.sub('_', name)
        sanitized = cls._MULTI_UNDERSCORE_RE.sub('_', sanitized)
        return sanitized.strip('_')

    def _sanitize_row(self, row: dict) -> dict:
        """
        Sanitize all keys in a data row dict.
        
        Keys that are already clean identifiers pass through unchanged.
        Keys with spaces/special chars get sanitized to match the rewritten query.
        None values are preserved (queries use coalesce() to handle them).
        """
        sanitized = {}
        for key, value in row.items():
            clean_key = self._sanitize_key(key) if not key.isidentifier() else key
            sanitized[clean_key] = value
        return sanitized

    @classmethod
    def _sanitize_query(cls, query: str) -> str:
        """
        Rewrite backtick-quoted property references in a query to use
        sanitized (underscored) names, matching what _sanitize_row produces.
        
        Transforms:
            item.`Owner First Name`                  -> item.Owner_First_Name
            item.`Purchase Order (Contract) Number`  -> item.Purchase_Order_Contract_Number  
            coalesce(item.`Address 1`, 'Unknown')    -> coalesce(item.Address_1, 'Unknown')
        
        Non-backticked references (item.RECORD_ID, item.DATA_SOURCE) are
        left unchanged — they're already valid identifiers.
        """
        def replace_match(match):
            var_name = match.group(1)    # e.g. 'item'
            field_name = match.group(2)  # e.g. 'Owner First Name'
            sanitized = cls._sanitize_key(field_name)
            return f'{var_name}.{sanitized}'
        
        return cls._BACKTICK_REF_RE.sub(replace_match, query)

    # -----------------------------------------------------------------
    # Index creation
    # -----------------------------------------------------------------

    def create_indices(self, indices):
        """
        Create indices in FalkorDB.
        Example: CREATE INDEX FOR (n:Label) ON (n.property)
        Or legacy: CREATE INDEX ON :Label(property)
        """
        for index in indices:
            try:
                self._graph.query(index)
            except Exception as e:
                print(f"Index creation failed: {index} - {e}")


# =============================================================================
# Factory
# =============================================================================

def get_importer(db_type: str):
    """
    Factory function to get a graph database importer.
    
    Args:
        db_type: One of 'neo4j', 'memgraph', 'turingdb', 'falkordb'
    
    Returns:
        Importer instance
    """
    importers = {
        'neo4j': Neo4jBaseImporter,
        'falkordb': FalkorDBBaseImporter,
    }
    
    if db_type.lower() not in importers:
        raise ValueError(f"Unknown database type: {db_type}. Choose from: {list(importers.keys())}")
    
    return importers[db_type.lower()]()