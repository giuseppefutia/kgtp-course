"""
Backend Abstraction Layer
Handles database-specific query syntax differences.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional


class BackendAdapter(ABC):
    """Abstract base class for backend-specific query adaptations."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Backend name identifier."""
        pass

    @abstractmethod
    def unique_constraint(self, label: str, property: str, name: Optional[str] = None) -> str:
        """Generate unique constraint query."""
        pass

    @abstractmethod
    def index(self, label: str, property: str, name: Optional[str] = None) -> str:
        """Generate index creation query."""
        pass

    @abstractmethod
    def fulltext_index(self, label: str, properties: List[str], name: Optional[str] = None) -> str:
        """Generate fulltext index query (if supported)."""
        pass

    @abstractmethod
    def coalesce_text(self, *fields: str, separator: str = " ") -> str:
        """Generate coalesce/concat expression for text fields."""
        pass

    @abstractmethod
    def capitalize_all(self, expression: str) -> str:
        """Generate capitalize expression."""
        pass

    @abstractmethod
    def regex_replace(self, text: str, pattern: str, replacement: str) -> str:
        """Generate regex replace expression."""
        pass

    def supports_apoc(self) -> bool:
        """Whether this backend supports APOC procedures."""
        return False

    def supports_fulltext(self) -> bool:
        """Whether this backend supports fulltext indexes."""
        return False

    def supports_merge(self) -> bool:
        """Whether this backend supports MERGE clause."""
        return True

    def supports_case(self) -> bool:
        """Whether this backend supports CASE expressions."""
        return True


class Neo4jAdapter(BackendAdapter):
    """Neo4j-specific query syntax."""

    @property
    def name(self) -> str:
        return "neo4j"

    def unique_constraint(self, label: str, property: str, name: Optional[str] = None) -> str:
        constraint_name = name or f"{label.lower()}_{property}"
        return f"CREATE CONSTRAINT {constraint_name} IF NOT EXISTS FOR (n:{label}) REQUIRE n.{property} IS UNIQUE"

    def index(self, label: str, property: str, name: Optional[str] = None) -> str:
        index_name = name or f"{label.lower()}_{property}"
        return f"CREATE INDEX {index_name} IF NOT EXISTS FOR (n:{label}) ON (n.{property})"

    def fulltext_index(self, label: str, properties: List[str], name: Optional[str] = None) -> str:
        index_name = name or f"{label.lower()}_{'_'.join(properties)}_fulltext"
        props = ", ".join([f"n.{p}" for p in properties])
        return f"CREATE FULLTEXT INDEX {index_name} IF NOT EXISTS FOR (n:{label}) ON EACH [{props}]"

    def coalesce_text(self, *fields: str, separator: str = " ") -> str:
        """
        Generate: coalesce(field1, '') + ' ' + coalesce(field2, '') + ...
        """
        parts = [f"coalesce({f}, '')" for f in fields]
        join_str = f" + '{separator}' + "
        return join_str.join(parts)

    def capitalize_all(self, expression: str) -> str:
        return f"apoc.text.capitalizeAll(toLower({expression}))"

    def regex_replace(self, text: str, pattern: str, replacement: str) -> str:
        return f"apoc.text.replace({text}, '{pattern}', '{replacement}')"

    def supports_apoc(self) -> bool:
        return True

    def supports_fulltext(self) -> bool:
        return True


class FalkorDBAdapter(BackendAdapter):
    """FalkorDB-specific query syntax."""

    @property
    def name(self) -> str:
        return "falkordb"

    def unique_constraint(self, label: str, property: str, name: Optional[str] = None) -> str:
        # FalkorDB doesn't support constraints - use index instead
        return f"CREATE INDEX FOR (n:{label}) ON (n.{property})"

    def index(self, label: str, property: str, name: Optional[str] = None) -> str:
        return f"CREATE INDEX FOR (n:{label}) ON (n.{property})"

    def fulltext_index(self, label: str, properties: List[str], name: Optional[str] = None) -> str:
        # FalkorDB fulltext via procedure
        return f"CALL db.idx.fulltext.createNodeIndex('{label}', '{properties[0]}')"

    def coalesce_text(self, *fields: str, separator: str = " ") -> str:
        parts = [f"coalesce({f}, '')" for f in fields]
        join_str = f" + '{separator}' + "
        return join_str.join(parts)

    def capitalize_all(self, expression: str) -> str:
        return f"toLower({expression})"

    def regex_replace(self, text: str, pattern: str, replacement: str) -> str:
        return f"replace({text}, '{pattern}', '{replacement}')"

    def supports_apoc(self) -> bool:
        return False

    def supports_fulltext(self) -> bool:
        return True


# =============================================================================
# Registry
# =============================================================================

BACKEND_ADAPTERS: Dict[str, BackendAdapter] = {
    "neo4j": Neo4jAdapter(),
    "falkordb": FalkorDBAdapter(),
}


def get_adapter(backend: str) -> BackendAdapter:
    """
    Get the adapter for a specific backend.
    
    Args:
        backend: Backend name ('neo4j', 'memgraph', 'turingdb', 'falkordb')
    
    Returns:
        BackendAdapter instance
    
    Raises:
        ValueError: If backend is not supported
    """
    if backend not in BACKEND_ADAPTERS:
        raise ValueError(f"Unknown backend: {backend}. Choose from: {list(BACKEND_ADAPTERS.keys())}")
    return BACKEND_ADAPTERS[backend]


def list_backends() -> List[str]:
    """Return list of available backend names."""
    return list(BACKEND_ADAPTERS.keys())