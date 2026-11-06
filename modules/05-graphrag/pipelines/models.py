"""The served models, built from `pipelines/config.py`.

One place, so that pointing the whole module at a different endpoint is one
environment variable and not a search through six files. The student points it
at the small model running on their own machine; the instructor points it at
the served 30B, and nothing else changes.
"""

from __future__ import annotations

import re
import time

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from pipelines.config import setting


# Qwen3.8 reasons before it answers, and the reasoning is spent from the same
# `max_tokens` as the reply. Measured 5/11/2026 on one Cypher question: 539
# completion tokens with thinking, 38 without, for the same query. The caps in
# `prompt.py` were written for a model that does not think -- at 400 tokens the
# reasoning alone exhausts them and the content comes back **empty**, which
# reaches the pipeline as a query that will not compile and as a relevance
# check that silently fails open.
#
# So it is off, in one place, for every call. Turn it back on for one call with
# `chat_model(extra_body={"chat_template_kwargs": {"enable_thinking": True}})`,
# and raise that call's `max_tokens` to at least 1,200 when you do.
#
# Writing `/no_think` into the system prompt does the opposite of what it looks
# like: it is read as text, the model thinks about it, and the reply is empty.
NO_THINKING = {"chat_template_kwargs": {"enable_thinking": False}}


def chat_model(**kwargs) -> ChatOpenAI:
    # max_retries is not defensive padding. The proxy in front of the served
    # model rate-limits per key -- 10 requests a minute on 1/9/2026 -- and one
    # run of the lesson makes more calls than that. Without the retries the
    # notebook dies halfway through on a 429, which reads to a student as "the
    # code is broken" rather than "wait forty seconds".
    return ChatOpenAI(
        base_url=setting("llm", "base_url"),
        api_key=setting("llm", "api_key"),
        model=setting("llm", "model"),
        temperature=0,
        timeout=180,
        max_retries=8,
        **{"extra_body": NO_THINKING, **kwargs})


def embedding_model() -> OpenAIEmbeddings:
    # check_embedding_ctx_length is off because the served endpoint is vLLM,
    # not OpenAI: the client would otherwise try to tokenise with tiktoken for
    # a model tiktoken has never heard of.
    return OpenAIEmbeddings(
        base_url=setting("embeddings", "base_url"),
        api_key=setting("embeddings", "api_key"),
        model=setting("embeddings", "model"),
        check_embedding_ctx_length=False)


def invoke(model, messages, attempts: int = 6):
    """Call the model, waiting out the proxy's rate limit instead of dying on it.

    The proxy in front of the served model allows 10 requests a minute per key
    and says how long to wait in the body of the 429. The OpenAI client retries
    too, but with its own backoff, which is shorter than the wait the proxy
    asks for -- so one run of the lesson still dies halfway through, and to a
    student that reads as broken code rather than as a queue.

    Honouring the number the proxy sends is the difference. It also makes the
    limit visible while it happens, which is the honest thing to show: a class
    of twenty sharing one endpoint is going to meet it.
    """
    for attempt in range(attempts):
        try:
            return model.invoke(messages)
        except Exception as e:
            wait = re.search(r"Retry in (\d+)", str(e))
            if not wait or attempt == attempts - 1:
                raise
            seconds = int(wait.group(1)) + 1
            print(f"   rate limited, waiting {seconds}s")
            time.sleep(seconds)
