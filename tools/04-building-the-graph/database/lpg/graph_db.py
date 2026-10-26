"""
Graph Database Connection Classes
Supports: Neo4j, FalkorDB
"""

from neo4j import GraphDatabase
import configparser
import os


class Neo4jDB:
    """Neo4j graph database connection handler."""
    
    def __init__(self, uri=None, user=None, password=None, database=None):
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database

        # Order: explicit argument, then environment, then config.ini, then the
        # values in docker/docker-compose.yml. Environment before file so that
        # nothing has to be written to disk to connect -- a committed config is
        # where a real password eventually ends up.
        params = self._load_config(os.path.join(os.path.dirname(__file__), 'config.ini'))
        uri = self.uri or os.environ.get('NEO4J_URI') \
            or params.get('uri', 'bolt://localhost:7687')
        user = self.user or os.environ.get('NEO4J_USER') \
            or params.get('user', 'neo4j')
        password = self.password or os.environ.get('NEO4J_PASSWORD') \
            or params.get('password', 'kgtp-local')
        self._database = self.database or os.environ.get('NEO4J_DATABASE') \
            or params.get('database', 'neo4j')

        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._session = None
    
    def _load_config(self, config_path):
        config = configparser.ConfigParser()
        config.read(config_path)
        return config['neo4j'] if 'neo4j' in config else {}

    def query(self, cypher, parameters=None):
        with self._driver.session(database=self._database) as session:
            result = session.run(cypher, parameters or {})
            return [record.data() for record in result]

    def close(self):
        self._driver.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class FalkorDB:
    """
    FalkorDB graph database connection handler.
    Uses Redis protocol with the falkordb Python client.
    
    Install: pip install falkordb
    """
    
    def __init__(self, host=None, port=None, password=None, graph=None):
        try:
            from falkordb import FalkorDB as FalkorClient
        except ImportError:
            raise ImportError("falkordb package not found. Install with: pip install falkordb")

        self.host = host
        self.port = port
        self.password = password
        self.graph = graph

        params = self._load_config(os.path.join(os.path.dirname(__file__), 'config.ini'))
        host = self.host or params.get('host', 'localhost')
        port = self.port or int(params.get('port', 6379))
        password = self.password or params.get('password', None)
        self._graph_name = self.graph or params.get('graph', 'default')

        # Connect to FalkorDB
        if password:
            self._client = FalkorClient(host=host, port=port, password=password)
        else:
            self._client = FalkorClient(host=host, port=port)
        
        # Select graph
        self._graph = self._client.select_graph(self._graph_name)
    
    def _load_config(self, config_path):
        config = configparser.ConfigParser()
        config.read(config_path)
        return config['falkordb'] if 'falkordb' in config else {}

    def select_graph(self, name):
        """Select a different graph."""
        self._graph_name = name
        self._graph = self._client.select_graph(name)

    def query(self, cypher, parameters=None):
        """Execute a Cypher query."""
        if parameters:
            result = self._graph.query(cypher, parameters)
        else:
            result = self._graph.query(cypher)
        return result.result_set

    def close(self):
        # FalkorDB client doesn't require explicit close
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Factory function for convenience
def get_graph_db(db_type, **kwargs):
    """
    Factory function to get a graph database connection.
    
    Args:
        db_type: One of 'neo4j', 'falkordb'
        **kwargs: Connection parameters specific to each database
    
    Returns:
        Database connection instance
    """
    databases = {
        'neo4j': Neo4jDB,
        'falkordb': FalkorDB,
    }
    
    if db_type.lower() not in databases:
        raise ValueError(f"Unknown database type: {db_type}. Choose from: {list(databases.keys())}")
    
    return databases[db_type.lower()](**kwargs)