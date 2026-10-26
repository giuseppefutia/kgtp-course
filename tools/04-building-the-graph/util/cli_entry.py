import argparse
from util.logger import setup_logging
from util.cli_utils import run_importer, run_updater
from importer.lpg.graph_importer import (
    Neo4jBaseImporter,
    FalkorDBBaseImporter,
)

# Backend mapping - extend this to add new backends.
# Memgraph and TuringDB were dropped when the importers moved under lpg/:
# importer/lpg/graph_importer.py defines Neo4j and FalkorDB only.
BACKEND_MAP = {
    "neo4j": Neo4jBaseImporter,
    "falkordb": FalkorDBBaseImporter,
}

# Default batch sizes per backend
DEFAULT_BATCH_SIZES = {
    "neo4j": 1000,
    "falkordb": 1000,
}

def run_backend_importer(
    importer_factory_func,
    description,
    file_help,
    default_base_path="./data/",
    require_file=True,
):
    setup_logging()

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--backend", choices=list(BACKEND_MAP.keys()), required=True,
                        help="Which importer backend to use")
    
    # Only require --file if the importing flow needs it
    if require_file:
        parser.add_argument("--file", required=True, help=file_help)
    else:
        parser.add_argument("--file", help=file_help)

    parser.add_argument("--base_path", default=default_base_path,
                        help="Base directory where the file is located")
    
    parser.add_argument("--batch-size", type=int, default=None,
                        help="Batch size for imports (default: backend-specific)")

    args = parser.parse_args()

    base_cls = BACKEND_MAP.get(args.backend)
    if base_cls is None:
        raise ValueError(f"Unsupported backend: {args.backend}")

    # Determine batch size: CLI override > default for backend
    batch_size = args.batch_size or DEFAULT_BATCH_SIZES.get(args.backend, 1000)

    if require_file:
        run_importer(importer_factory_func, base_cls, args.backend, args.file, 
                     base_path=args.base_path, batch_size=batch_size)
    else:
        run_updater(importer_factory_func, base_cls, args.backend, batch_size=batch_size)