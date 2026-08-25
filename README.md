# jottermem

[![CI](https://github.com/Kazu-Labs/jottermem/actions/workflows/ci.yml/badge.svg)](https://github.com/Kazu-Labs/jottermem/actions/workflows/ci.yml)

A dead-simple, embeddable memory layer for AI apps — single file, zero infra, zero account. The SQLite of agent memory.

```python
from jottermem import Memory

mem = Memory("agent.db")

mem.remember("The user's favorite color is blue.")
mem.remember("The user works as a software engineer.")

for result in mem.recall("What color does the user like?", k=3):
    print(result.score, result.memory.text)
```

No server, no Postgres, no Neo4j, no Docker Compose, no account. `pip install jottermem`, one file on disk, done. See [examples/quickstart.py](examples/quickstart.py) for a longer runnable tour (dedup, key-based staleness, forget).

## Why

Vector search itself is a solved, commoditized problem (`sqlite-vec`, LanceDB, ChromaDB). The hard part of "memory" is everything above the vector index: deciding what to store, deduplicating facts over time, resolving conflicts when new information contradicts old, and retrieving the *right* thing instead of just the *nearest* thing.

Existing memory frameworks (Mem0, Cognee, Zep, Letta) solve that layer well but assume you're standing up real infrastructure — Postgres, a vector store, optionally Neo4j, Docker Compose — or paying for a hosted platform. jottermem is the missing zero-infra option: everything above lives in one SQLite file, with no required dependency beyond Python itself.

## Install

```bash
pip install jottermem
```

That's it — the default embedder and extractor are pure Python with no third-party dependencies. Want real semantic embeddings instead of the lexical default? `pip install jottermem[sentence-transformers]`.

## The API

```python
from jottermem import Memory

mem = Memory("agent.db")  # one file; ":memory:" for ephemeral/in-process use

# remember() splits input into atomic facts and stores each one
mem.remember("I live in Boston. I work at Acme Corp.")

# recall() does hybrid semantic + keyword search
results = mem.recall("Where does the user live?", k=5)

# forget() and list_memories() for explicit management
mem.forget(results[0].memory.id)
mem.list_memories(filter={"topic": "work"})
```

### Deduplication on write

A new fact whose embedding is nearly identical to an existing active memory is treated as a repeat instead of piling up as a duplicate row:

```python
mem.remember("The user likes tea.")
mem.remember("The user likes tea.")  # no-op: touches the existing memory, doesn't duplicate it
```

### Staleness / conflict handling via keys

Facts that change over time (an employer, a preference, a status) should be written with a stable `key`. Writing a new fact under an existing key marks the old one `superseded` instead of leaving both active with equal confidence:

```python
mem.remember("Works at Acme Corp.", key="employer")
mem.remember("Works at Globex.", key="employer")

mem.list_memories()                       # -> just "Works at Globex."
mem.list_memories(include_superseded=True)  # -> both, with the old one marked superseded
```

This is an explicit, honest mechanism, not free-text contradiction detection — inferring conflicts from unstructured text alone is a genuinely unsolved research problem (see the [PRD](PRD.md)). Tag facts that evolve with a `key` and jottermem keeps recall pointed at the current value.

### Namespaces

Pass `namespace=` to `remember()`/`recall()`/`list_memories()` (or set one on the `Memory` instance) to scope memories per user, session, or agent within the same file.

### Swapping components

```python
from jottermem import Memory
from jottermem.embeddings import SentenceTransformerEmbedder

mem = Memory("agent.db", embedder=SentenceTransformerEmbedder())
```

Any object with a `dim` attribute and a `__call__(texts: list[str]) -> list[list[float]]` method works as an embedder. Any object with an `extract(text: str) -> list[str]` method works as an extractor.

For finer-grained atomic facts than the default rule-based sentence splitter, use `LLMExtractor` — it's provider-agnostic (you supply a `complete(prompt) -> str` callable), so it adds no dependency and works with any LLM API:

```python
from jottermem import Memory
from jottermem.extraction import LLMExtractor

def complete(prompt: str) -> str:
    msg = anthropic_client.messages.create(
        model="claude-sonnet-5",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text

mem = Memory("agent.db", extractor=LLMExtractor(complete))
mem.remember("I live in Boston and work at Acme Corp.")
# -> two atomic facts instead of one compound sentence
```

### Accelerating search with sqlite-vec

The default vector search is a brute-force cosine scan in Python — no C extension, works everywhere. Once that stops being fast enough, `pip install jottermem[sqlite-vec]` accelerates it with a `sqlite-vec` `vec0` index transparently:

```python
mem = Memory("agent.db")  # use_sqlite_vec="auto" by default
```

`"auto"` uses the index when it's available and silently falls back to brute-force when it isn't — nothing to configure, and a plain `pip install jottermem` still works with zero extra dependencies either way. Two things have to be true for acceleration to actually kick in: the `sqlite-vec` package is installed, and the running Python's `sqlite3` module supports loadable extensions (true of python.org and Homebrew builds; **not** true of Apple's system Python on macOS). Pass `use_sqlite_vec=True` to raise instead of silently falling back if you need to know acceleration is actually active, or `False` to disable it outright.

One tradeoff worth knowing: when accelerated, `recall()`'s keyword-overlap boost re-ranks within the nearest ~50 (or `10 × k`, whichever is larger) vector matches rather than every stored memory — an inherent ANN-then-rerank tradeoff. A memory with heavy keyword overlap but a poor vector-similarity rank outside that window won't surface, where the (slower) brute-force path would still find it via the keyword score alone. Dedup and staleness supersession are unaffected — those only need the single nearest match, which the index finds exactly.

## Status

Early / pre-alpha. Working today:

- Single-file SQLite storage (structured metadata + packed embeddings, no separate services)
- `remember()` / `recall()` / `forget()` / `list_memories()`
- Dependency-free default embedder (deterministic hashing-trick bag-of-words) and default rule-based sentence extractor
- Deduplication on write, key-based staleness/supersession
- Hybrid recall (cosine similarity + keyword overlap boost)
- `LLMExtractor` for provider-agnostic, LLM-backed atomic fact extraction
- A [staleness benchmark](BENCHMARKS.md) showing 3/3 vs. 0/3 current-fact accuracy against a naive top-K baseline on a synthetic evolving-facts scenario, using the same embedder on both sides
- Optional `sqlite-vec` acceleration (`pip install jottermem[sqlite-vec]`), used automatically when available and never required

Roadmap: a broader published benchmark against naive top-K RAG on a standard long-term-memory dataset (LoCoMo-style — the synthetic staleness benchmark above is a narrower first proof point, not a replacement for that). See [PRD.md](PRD.md) for the full plan and explicit non-goals (this is not trying to be Cognee's graph memory or Mem0 Platform's multi-tenant infra).

## Design notes / trade-offs

- **Vector search is brute-force cosine in Python by default**, accelerated by an optional `sqlite-vec` index (see above) — the brute-force path keeps a plain `pip install jottermem` genuinely dependency-free (no C extension wheels that might not exist for your platform, and no dependency on `sqlite3` being built with loadable-extension support, which Apple's system Python on macOS isn't), and is plenty fast at the single-file, thousands-of-memories scale this library targets on its own.
- **The default embedder is lexical, not semantic** — it won't match paraphrases. It's there so `pip install jottermem` works standalone in under 5 minutes with zero infra decisions; swap in `SentenceTransformerEmbedder` or your own API-backed embedder when recall quality matters more than zero dependencies.
- **Staleness resolution is key-based, not inferred** — see above.
- **All stored embeddings are unit-normalized**, regardless of what a custom embedder returns — this keeps the sqlite-vec acceleration's Euclidean-to-cosine distance conversion exact for every embedder, not just the bundled ones.

## Releasing

Not yet published to PyPI. `.github/workflows/publish.yml` builds and publishes on every GitHub Release via [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (no stored API token) — to cut a release, register this repo as a trusted publisher for the `jottermem` project on PyPI (environment name `pypi`, workflow `publish.yml`), then create a GitHub Release.

## License

Apache-2.0
