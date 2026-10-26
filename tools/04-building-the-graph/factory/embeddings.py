"""Page vectors, computed by the served embedding model and written to the graph.

The retrieval half of module 5. With the vectors here, a question can be
answered from the documents, from the structure, or from both, and the three are
comparable because they run against the same database.

The model is served rather than run locally: 1.2 GB of weights and a working
PyTorch on twenty different laptops is the prerequisite that fails on the first
day, and the endpoint is needed anyway for the agentic scenarios. See decision
19 and the amendment that followed it.

The vectors are derived, not authored, so they are never committed. What is
committed is the recipe -- the text, the pinned model revision, and this file --
which only stays true while the endpoint actually serves the pinned revision.
That is why the dimension of the first batch is checked instead of assumed.
"""

# The only module-level import here: every other one is inside the function that
# uses it, and the reason is just below.
import os


# At module level, unlike the rest of this file, because build.py reads both to
# probe the endpoint in its preflight. Duplicating the URL there would give two
# addresses that disagree the first time the tunnel is restarted.
#
# Overridable, under the name descriptions.py already uses for the same endpoint.
# It was a literal until 26/10/2026, and it was the only one of the six places
# that call a model with no way to repoint it -- which made it the one phase
# somebody serving the model on their own account had to edit the source to run.
# The preflight reads this same value, so an override moves the probe with it.
DEFAULT_URL = os.environ.get("KGTP_EMBEDDINGS_BASE_URL",
                             "https://kgtp-embed.ngrok-free.app/v1")


def ssl_context():
    """A verifying context that works on a python.org install.

    That build ships without a CA bundle wired up, so urlopen on https fails
    with CERTIFICATE_VERIFY_FAILED while curl on the same URL succeeds.
    """
    import ssl
    from pathlib import Path
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        cafile = "/etc/ssl/cert.pem"
        return ssl.create_default_context(
            cafile=cafile if Path(cafile).exists() else None)


def chi_embeddings_factory(base_importer_cls, backend: str):
    import json
    import logging
    import time
    import urllib.error
    import urllib.request

    MODEL = "Qwen/Qwen3-Embedding-0.6B"
    # The same revision the endpoint serves. Pinned here too because this is
    # where the index is written: the two have to name the same weights or the
    # vectors in the graph belong to a model nobody recorded.
    REVISION = "97b0c614be4d"
    DIMENSIONS = 1024

    # Truncation is by characters and the limit is by tokens, so this has to be
    # conservative: dense text -- tables, figures, degraded OCR -- tokenises at
    # well under three characters per token, and a page that fits on average
    # overflows here. A batch that overflows is rejected whole, taking the
    # sixty-three pages sent with it.
    MAX_CHARS = 6_000

    SSL = ssl_context()

    # Pages read per round trip. Large enough that the round trips are
    # negligible against the embedding calls, small enough that no single
    # read is long-lived.
    BLOCK = 5000

    # Retries per batch, and the first wait in seconds. Generous because
    # the cost of giving up is the rest of the pass, and the endpoint is a
    # hosted runtime that comes back within a minute when it blips.
    ATTEMPTS = 7
    BACKOFF = 5

    class ChicagoEmbeddingsImporter(base_importer_cls):
        def __init__(self):
            super().__init__()
            self.backend = backend
            self.base_url = DEFAULT_URL
            # Same story as DEFAULT_URL above, and the same variable name
            # descriptions.py reads: an endpoint you serve yourself has its own
            # keys, and `teacher-key` is only the default this course happens to
            # hand out.
            self.api_key = os.environ.get("KGTP_EMBEDDINGS_API_KEY", "teacher-key")
            self._prefix = None

        def query_prefix(self):
            """The prefix this model wants in front of a question, if any.

            Read from the model rather than written here. Some models are trained
            asymmetrically -- documents embedded as they are, questions behind a
            task instruction -- and each declares its own wording. Hardcoding one
            makes it wrong the moment the model changes, and a wrong prefix costs
            relevance with nothing to show that it did.

            Empty for a model that declares nothing, which is most of them.
            """
            if self._prefix is None:
                url = (f"https://huggingface.co/{MODEL}/raw/{REVISION}/"
                       "config_sentence_transformers.json")
                try:
                    with urllib.request.urlopen(url, timeout=20, context=SSL) as r:
                        self._prefix = json.loads(r.read()).get("prompts", {}).get("query", "")
                except Exception:
                    self._prefix = ""
            return self._prefix

        def embed_query(self, question):
            """Embed a question the way this model expects to receive one."""
            prefix = self.query_prefix()
            return self.embed([f"{prefix} {question}" if prefix else question])[0]

        def count_pending(self):
            query = ("MATCH (p:Page) WHERE p.text IS NOT NULL AND p.embedding IS NULL "
                     "RETURN count(p) AS rows")
            with self._driver.session(database=self._database) as session:
                return session.run(query).single()["rows"]

        def get_pending(self):
            """Pages still to embed, shallowest first.

            Ordered by page number so the index grows in breadth before depth:
            page 1 of every document before page 2 of any. A pass stopped early
            then covers the whole corpus thinly rather than a few documents
            completely, and thin coverage of everything is what makes a
            retrieval comparison possible at all.
            """
            # Read in blocks rather than from one cursor held open for the
            # whole pass. A pass over ninety thousand pages takes half an hour
            # at roughly a batch a second, and on 15/9/2026 the connection was
            # dropped at 14%: the vectors already written survived, the pass did
            # not.
            #
            # In two queries, not one. `ORDER BY` has to materialise every
            # matching row before it can apply a `LIMIT`, and a row here carries
            # the page text -- ordering eighty thousand of those exhausted the
            # heap on the same day. The first query sorts identifiers, which are
            # small; the second fetches the text of one block, unordered.
            keys = ("MATCH (p:Page) WHERE p.text IS NOT NULL AND p.embedding IS NULL "
                    "AND ($after IS NULL OR [p.page, p.id] > $after) "
                    "RETURN p.id AS id, p.page AS page "
                    "ORDER BY p.page, p.id LIMIT $block")
            texts = ("MATCH (p:Page) WHERE p.id IN $ids "
                     "RETURN p.id AS id, p.text AS text")
            after = None
            while True:
                with self._driver.session(database=self._database) as session:
                    block = [dict(r) for r in session.run(keys, after=after, block=BLOCK)]
                    if not block:
                        return
                    by_id = {r["id"]: r["text"] for r
                             in session.run(texts, ids=[r["id"] for r in block])}
                after = [block[-1]["page"], block[-1]["id"]]
                for record in block:
                    text = by_id.get(record["id"])
                    if text:
                        yield {"id": record["id"], "text": text}

        def set_constraints(self):
            query = f"""
                CREATE VECTOR INDEX page_embedding IF NOT EXISTS
                FOR (p:Page) ON (p.embedding)
                OPTIONS {{indexConfig: {{
                    `vector.dimensions`: {DIMENSIONS},
                    `vector.similarity_function`: 'cosine'}}}}
            """
            with self._driver.session(database=self._database) as session:
                session.run(query)

        def embed(self, texts, timeout=180):
            """Ask the endpoint for one batch of vectors.

            Sorted by the index the server reports, not by arrival order: if the
            two ever diverge, every vector lands on the wrong page in silence.

            A 429 is waited out rather than failing the run, because an indexing
            pass will meet the limit. So is a 5xx: the endpoint is a Colab
            runtime behind a tunnel, and on 15/9/2026 a single `502: Error
            reaching vLLM` ended a pass at 32% -- the vectors written survived,
            the remaining hour did not.
            """
            payload = json.dumps({"model": MODEL, "input": texts}).encode()
            request = urllib.request.Request(
                self.base_url.rstrip("/") + "/embeddings", data=payload,
                headers={"content-type": "application/json",
                         "authorization": f"Bearer {self.api_key}",
                         "ngrok-skip-browser-warning": "1"},
                method="POST")
            for attempt in range(ATTEMPTS):
                try:
                    with urllib.request.urlopen(request, timeout=timeout, context=SSL) as r:
                        body = json.loads(r.read())
                    return [d["embedding"] for d in sorted(body["data"],
                                                           key=lambda d: d["index"])]
                except urllib.error.HTTPError as e:
                    detail = e.read().decode(errors="replace")[:300]
                    if e.code == 429 and attempt < 3:
                        logging.info("rate limited, waiting 20s")
                        time.sleep(20)
                        continue
                    # A page still over the window after truncation: halve it and
                    # try once more rather than lose the batch. A page cut in
                    # half is a worse vector; a batch lost is ninety thousand
                    # pages that have to start again.
                    if e.code == 400 and "context length" in detail and attempt < 3:
                        texts = [t[:len(t) // 2] for t in texts]
                        logging.info("a page overflowed the window, halving the batch")
                        payload = json.dumps({"model": MODEL, "input": texts}).encode()
                        request = urllib.request.Request(
                            self.base_url.rstrip("/") + "/embeddings", data=payload,
                            headers={"content-type": "application/json",
                                     "authorization": f"Bearer {self.api_key}",
                                     "ngrok-skip-browser-warning": "1"},
                            method="POST")
                        continue
                    if 500 <= e.code < 600 and attempt < ATTEMPTS - 1:
                        wait = BACKOFF * 2 ** attempt
                        logging.info("endpoint returned %d, waiting %ds", e.code, wait)
                        time.sleep(wait)
                        continue
                    raise RuntimeError(f"HTTP {e.code}: {detail}") from None
                except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                    # The tunnel drops without an HTTP status of its own.
                    if attempt < ATTEMPTS - 1:
                        wait = BACKOFF * 2 ** attempt
                        logging.info("endpoint unreachable (%s), waiting %ds",
                                     type(e).__name__, wait)
                        time.sleep(wait)
                        continue
                    raise
            raise RuntimeError(f"gave up after {ATTEMPTS} attempts")

        def embedded_rows(self, size):
            """Yield rows carrying their vector, a batch of calls at a time.

            Written as a generator so that batch_store keeps its progress bar and
            its per-batch failure handling: a run over ninety thousand pages that
            dies on one bad batch should lose that batch, not the pass.
            """
            batch, first = [], True
            for row in self.get_pending():
                batch.append(row)
                if len(batch) < size:
                    continue
                vectors = self.embed([r["text"][:MAX_CHARS] for r in batch])
                if first:
                    self.check_dimensions(vectors)
                    first = False
                yield from ({"id": r["id"], "embedding": v}
                            for r, v in zip(batch, vectors))
                batch = []
            if batch:
                vectors = self.embed([r["text"][:MAX_CHARS] for r in batch])
                if first:
                    self.check_dimensions(vectors)
                yield from ({"id": r["id"], "embedding": v}
                            for r, v in zip(batch, vectors))

        def check_dimensions(self, vectors):
            """Stop if the endpoint is not serving the model we pinned.

            An index built with a different model is not comparable with any
            other, and nothing downstream would say so.
            """
            if not vectors or len(vectors[0]) != DIMENSIONS:
                got = len(vectors[0]) if vectors else 0
                raise RuntimeError(
                    f"the endpoint returned {got} dimensions, not {DIMENSIONS}: "
                    f"it is not serving {MODEL}")

        def apply_updates(self, batch_size=64):
            logging.info("Creating the vector index...")
            self.set_constraints()

            pending = self.count_pending()
            logging.info(f"Pages to embed: {pending}")
            if not pending:
                logging.info("Nothing to do: every page with text already has a vector.")
                return

            query = """
                UNWIND $batch AS row
                MATCH (p:Page {id: row.id})
                SET p.embedding = row.embedding
            """
            # Write as often as the endpoint is asked, not every thousand rows:
            # the default buffer meant a single failed call discarded everything
            # embedded before it, and resuming had nothing to resume from.
            self.batch_size = batch_size
            self.batch_store(query, self.embedded_rows(batch_size), pending)

    return ChicagoEmbeddingsImporter


if __name__ == '__main__':
    from util.cli_entry import run_backend_importer

    run_backend_importer(
        chi_embeddings_factory,
        description="Embed the corpus pages through the served model and index them.",
        file_help="No file needed.",
        default_base_path="./data/",
        require_file=False
    )
