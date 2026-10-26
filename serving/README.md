# serving/

The two model endpoints the course runs against. They sit at the repository root
rather than inside a module because more than one module depends on them:
`tools/04-building-the-graph/build.py` probes the embedding endpoint before a
corpus build, the lesson of module 4 calls the other one for a single live
demonstration, and module 5 uses both.

| notebook | serves | who needs it |
|---|---|---|
| `embeddings.ipynb` | the embedding model, one vector per page | `build.py corpus`, the dense retriever |
| `llm.ipynb` | the strong model, OpenAI-compatible | the agent scenarios, the batch extraction |

Both run on a Colab GPU and expose vLLM through a FastAPI proxy over an ngrok
tunnel: vLLM has no authentication of its own, so it is never exposed directly.
Each notebook stands alone and says what the code does.

**They are instructor infrastructure, not a lab.** Nothing you are asked to do
needs them, and during a session they are the instructor's to start. They are
published for two reasons: so that the one phase of the build pipeline that
cannot be reproduced from a file is not a black box, and so that anyone with the
hardware can close that gap themselves rather than take the vectors on trust.

## Before you run either one

**Two Colab Secrets**, set from the key icon in the left sidebar and switched on
for the notebook:

| | |
|---|---|
| `HF_TOKEN` | <https://huggingface.co/settings/tokens> — fine-grained and read-only is enough; it downloads one model repo |
| `NGROK_TOKEN` | <https://dashboard.ngrok.com> → *Authtokens* |

Read from the Secrets panel rather than pasted into a cell, and the notebooks
will not start without them. The reason is the one failure that cannot be
undone: a token typed into a cell is saved inside the notebook, and these
notebooks are in a repository.

**The two addresses are reserved ngrok domains**, so a restart does not move the
endpoint. They are `kgtp-embed.ngrok-free.app` and `kgtp-llm.ngrok-free.app`,
they belong to the account whose authtoken you supply, and they are the
addresses the course code falls back to — written in
`tools/04-building-the-graph/factory/embeddings.py` and in the three other files
that call a model, not repeated here, because an address written twice diverges.
Serving on your own account means your own domain, and `NGROK_DOMAIN` plus the
`KGTP_EMBEDDINGS_BASE_URL` / `KGTP_LLM_BASE_URL` environment variables are how
the two ends are told about it.

**The keys in `API_KEYS` are examples.** One key per person, because the name
beside it is what shows up in the proxy's logs; `teacher-key` is the default the
course code uses when nothing else is set. Replace the dict with your own before
you hand the address to anybody.

## What each one costs

`llm.ipynb` says it in its own text: `Qwen3-Coder-30B-A3B-Instruct-FP8` is about
31 GB of weights on a 40 GB A100, and the notebook checks the GPU first on
purpose — the wrong one fails there, cheaply, instead of after the launch
arguments. It is not a free-tier notebook.

`embeddings.ipynb` serves `Qwen3-Embedding-0.6B`, which is two orders of
magnitude smaller, and is the one worth trying if you only have one GPU to
spend. Its model and revision are pinned to a commit rather than a branch: a
Hugging Face repo can be updated under the same name, and the vector a model
produces is not stable across versions, so an index built from one revision
cannot be compared with one built from another and nothing in the numbers would
say so.

## Why this is not simply a dependency of the labs

The vectors in the published graph were computed once, by the instructor,
against the pinned revision above. Module 4 never reads them. Module 5 does, and
the honest version of that arrangement is written in
`tools/04-building-the-graph/README.md`: the dump carries vectors for 92,439 of
its 279,017 pages, because `embed` last ran before the corpus grew. Closing that
gap is a run of this notebook plus a run of `build.py corpus --only embed`, and
it is work, not a setting.
