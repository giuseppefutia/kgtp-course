"""The embedding model module 5 searches with, handed to the memory store.

    from memory.embedder import CourseEmbedder
    store = await connect(settings, embedder=CourseEmbedder())

The library cannot be pointed at the model this course serves. Its
`EmbeddingConfig` carries `provider`, `model`, `dimensions` and `api_key` and no
base URL, so its `openai` provider resolves to OpenAI's endpoint rather than to
the one in `config.ini`. What it does accept is an embedder of your own, passed
to `connect`, and that is this class.

Using module 5's model rather than a second one is not only convenience. It puts
the conversation's messages and the contracts' document pages in the **same
vector space**, so "this question resembles that past turn" and "this question
resembles that page" are numbers that can be compared. Two models would make
them two scales with one name.

Measured 11/11/2026 against `Qwen/Qwen3-Embedding-0.6B`: 1024 dimensions, and
the vectors come back with norm 1.0, so cosine similarity is the dot product and
nothing here needs to normalise.

The failure mode to know about: `DIMENSIONS` is declared, not derived. The
library creates its vector index from this number on first write, and an index
built at one width does not accept vectors of another. Change the served model
and the store has to be rebuilt, not just reconfigured -- which is why the
number is checked on construction rather than trusted.
"""

from __future__ import annotations

import asyncio

from pipelines.config import setting
from pipelines.search import vector

DIMENSIONS = 1024


class CourseEmbedder:
    """Embed with the course's served model, one text or a batch.

    `pipelines.search.vector` is synchronous and the library awaits its
    embedder, so each call is handed to a worker thread. Without that the
    notebook's event loop blocks on an HTTPS round trip and the agent's own
    calls queue behind it.
    """

    def __init__(self, dimensions: int = DIMENSIONS) -> None:
        self._dimensions = dimensions
        self.model = setting("embeddings", "model")

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, text: str) -> list[float]:
        embedding = await asyncio.to_thread(vector, text)
        if len(embedding) != self._dimensions:
            raise ValueError(
                f"{self.model} returned {len(embedding)} dimensions, not "
                f"{self._dimensions}. A vector index already built at the "
                f"declared width will reject these: rebuild the memory store "
                f"rather than changing this number alone.")
        return embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(text) for text in texts]
