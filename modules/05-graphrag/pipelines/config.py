import configparser
import os
from pathlib import Path

# Next to the module first, then the working directory. Resolving only against
# the cwd was a bug with a long fuse: `tools/chicago/benchmark` imports these
# pipelines, finds no config.ini three levels up from where it was started, and
# silently falls back to the defaults below -- which point at localhost. The
# agent then got `Connection refused` from the rewriter, reported it as a failed
# tool, took a different path, and a battery case went red for a reason nothing
# in it mentioned. Measured 23/9/2026.
_MODULE = Path(__file__).resolve().parent.parent
CONFIG_PATHS = (_MODULE / "config.ini", Path("config.ini"),
                Path("../config.ini"), Path("../../config.ini"))

DEFAULTS = {
    # The same four the rest of the course falls back to, named in module 4's
    # README. They were `kgtp-local` and `neo4j` here, which meant this file
    # disagreed with the notebook beside it whenever `config.ini` was missing.
    "neo4j": {"uri": "bolt://localhost:7687", "user": "neo4j", "password": "password",
              "database": "kgtp"},
    "llm": {"base_url": "http://localhost:8000/v1", "api_key": "EMPTY",
            "model": "Qwen/Qwen3-4B-Instruct"},
    "embeddings": {"base_url": "https://kgtp-embed.ngrok-free.app/v1",
                   "api_key": "student-key-01", "model": "Qwen/Qwen3-Embedding-0.6B"},
}


def _file() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    for path in CONFIG_PATHS:
        if path.exists():
            parser.read(path)
            break
    return parser


_parser = _file()


def setting(section: str, key: str) -> str:
    """One value, from the environment, then config.ini, then the default.

    The environment comes first so a lab can be pointed at a different endpoint
    without editing a file that is under version control -- which is how a
    student's credentials end up in a pull request.
    """
    env = os.environ.get(f"KGTP_{section.upper()}_{key.upper()}")
    if env:
        return env
    # `NEO4J_PASSWORD` as well as `KGTP_NEO4J_PASSWORD`, because module 4's
    # README promises the four bare names to the whole course and a student who
    # exports them would otherwise find everything working except the one
    # pipeline that opens its own connection -- `text2cypher`, inside
    # `validate`, where the failure reads as the query being wrong.
    if section == "neo4j":
        env = os.environ.get(f"NEO4J_{key.upper()}")
        if env:
            return env
    if _parser.has_option(section, key):
        return _parser.get(section, key)
    return DEFAULTS[section][key]
