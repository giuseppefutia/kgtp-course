# Knowledge Graph Training Program

Ground your LLMs with structured knowledge — and leave with a full pipeline,
from data ingestion to agentic retrieval, that you know how to keep
production-ready.

Nine weeks, one session a week, built throughout on the public procurement data
of the City of Chicago: 88,916 contracts and 1.2M business licences, published
by the city and not cleaned up for teaching. Every week is part lecture, part
hands-on lab, and part honest conversation about what actually works in
production.

## The nine modules

A module's folder appears here in the week it is taught, so `git pull` before
every one.

| | | |
|---|---|---|
| 1 | **The Connected World** — Why Graphs Change Everything | [`01-the-connected-world`](modules/01-the-connected-world) |
| 2 | **Modeling the World** — Schemas, Ontologies & Validation | [`02-modeling-the-world`](modules/02-modeling-the-world) |
| 3 | **Where Data Lives** — Databases, Queries & Graph Algorithms | [`03-where-data-lives`](modules/03-where-data-lives) |
| 4 | **Building the Graph** — Ingestion, Extraction & Ontology Design | |
| 5 | **GraphRAG** — Agents That Navigate Your Knowledge | |
| 6 | **Agentic Memory** — Building Systems That Learn Over Time | |
| 7 | **Graph Representation Learning** — How Machines Learn from Connections | |
| 8 | **Production & MLOps** — Keeping It Alive After Launch | |
| 9 | **Building the KG Culture** — From Proof of Concept to Strategic Asset | |

Each folder holds `lesson.ipynb`, which we work through together, and
`lab.ipynb`, which you do afterwards. A folder name is the title above with the
subtitle dropped, so you can find a module without translating.

Module 1 runs on [Colab](https://colab.research.google.com) only: it trains a
small graph network with PyTorch, which Colab already has and the environment
below deliberately leaves out. Every other module runs in that environment.

## Setting up

Python 3.11 or newer. From a terminal, in the folder where you cloned this
repository:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[notebooks]"
python -m ipykernel install --user --name kgtp --display-name "KGTP"
```

The environment lives in `.venv` inside the repository and is yours alone —
nothing outside it is touched, and deleting that folder undoes everything above.

The last line registers it as a Jupyter kernel. Every notebook asks for the
kernel named **KGTP** by name; without it an editor picks whichever Python it
finds first, and the notebooks fail on an import with everything correctly
installed one directory away.

Open a new terminal later and the environment is not active: run the `activate`
line again, or start your editor from a terminal where you already have.

## Licence

See [`LICENSE`](LICENSE).
