# jottermem

[![CI](https://github.com/Kazu-Labs/jottermem/actions/workflows/ci.yml/badge.svg)](https://github.com/Kazu-Labs/jottermem/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/jottermem.svg)](https://pypi.org/project/jottermem/)

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

The default vector search is a brute-force cosine scan in Python — no C extension, works everywhere. Once that stops being fast enough, `pip install jottermem[sqlite-vec]` accelerates it with a `sqlite-vec` `vec0` index transparently. On a real 419-turn conversation from the [LoCoMo benchmark](BENCHMARKS.md#locomo-retrieval-benchmark), acceleration took the same `remember()` + `recall()` workload from 14.8s to 0.39s — about **38x**.

```python
mem = Memory("agent.db")  # use_sqlite_vec="auto" by default
```

`"auto"` uses the index when it's available and silently falls back to brute-force when it isn't — nothing to configure, and a plain `pip install jottermem` still works with zero extra dependencies either way. Two things have to be true for acceleration to actually kick in: the `sqlite-vec` package is installed, and the running Python's `sqlite3` module supports loadable extensions (true of python.org and Homebrew builds; **not** true of Apple's system Python on macOS). Pass `use_sqlite_vec=True` to raise instead of silently falling back if you need to know acceleration is actually active, or `False` to disable it outright.

One tradeoff worth knowing: when accelerated, `recall()`'s keyword-overlap boost re-ranks within the nearest ~50 (or `10 × k`, whichever is larger) vector matches rather than every stored memory — an inherent ANN-then-rerank tradeoff. A memory with heavy keyword overlap but a poor vector-similarity rank outside that window won't surface, where the (slower) brute-force path would still find it via the keyword score alone. Dedup and staleness supersession are unaffected — those only need the single nearest match, which the index finds exactly.

### MCP server

```bash
pip install jottermem[mcp]   # requires Python >=3.10, the mcp SDK's own requirement
jottermem-mcp
```

Exposes `remember`, `recall`, `forget`, and `list_memories` as MCP tools, so Claude Code and other MCP-aware agents can use jottermem as their own persistent memory directly — no generated Python required. Point the client at the `jottermem-mcp` command; configure the backing file with `JOTTERMEM_DB_PATH` (default `jottermem.db`) and the default namespace with `JOTTERMEM_NAMESPACE`.

Example client config (Claude Code, `.mcp.json` or similar):

```json
{
  "mcpServers": {
    "jottermem": {
      "command": "jottermem-mcp",
      "env": { "JOTTERMEM_DB_PATH": "/path/to/agent.db" }
    }
  }
}
```

The store is safe to call from multiple threads — MCP's SDK runs sync tool handlers in a worker-thread pool, so `SQLiteStore` opens with `check_same_thread=False` and serializes access with a lock rather than assuming single-threaded use.

## A portable memory folder for your AI assistants

Everything above is `jottermem` the embeddable library — a single SQLite
file, meant for a developer wiring memory into their own app. There's a
separate, simpler layer on top for a different use case: a memory folder
*you* set up once and point Claude, ChatGPT, and other AI assistants at, so
they share context instead of each starting from zero. It stores memory as
plain markdown files (one per topic) you can open and hand-edit — not the
SQLite/vector engine above.

```bash
pip install "jottermem[mcp]"
jottermem-setup
```

The wizard asks whether your memory folder should live locally or inside
your own Google Drive, creates it, and writes ready-to-use connection
config for Claude Desktop, Claude Code, and any other MCP-aware client —
plus instructions for ChatGPT, which needs the separate `jottermem-relay`
service (see [`src/jottermem/relay/README.md`](src/jottermem/relay/README.md))
since its custom connectors can only reach a remote HTTPS server, not a
local one.

Run `jottermem-app` any time afterward to open the folder in a local
browser view — see what's stored, hand-edit a topic, or add a fact without
touching a text editor. It's a plain stdlib web server bound to
`127.0.0.1`, no extra dependency beyond `jottermem` itself.

See [`jottermem-prd.md`](jottermem-prd.md) for the full product plan behind
this layer, including the ChatGPT/Drive architecture tradeoffs.

## Status

Early / pre-alpha. Working today:

- Single-file SQLite storage (structured metadata + packed embeddings, no separate services)
- `remember()` / `recall()` / `forget()` / `list_memories()`
- Dependency-free default embedder (deterministic hashing-trick bag-of-words) and default rule-based sentence extractor
- Deduplication on write, key-based staleness/supersession
- Hybrid recall (cosine similarity + keyword overlap boost)
- `LLMExtractor` for provider-agnostic, LLM-backed atomic fact extraction
- Optional `sqlite-vec` acceleration (`pip install jottermem[sqlite-vec]`), used automatically when available and never required
- Two [published benchmarks](BENCHMARKS.md): a synthetic staleness scenario (3/3 vs. 0/3 current-fact accuracy vs. naive top-K) and a real one on [LoCoMo](https://github.com/snap-research/locomo)'s single-hop QA set, where jottermem roughly **doubles** naive top-K's Recall@k (e.g. 17.2% vs. 8.8% at k=1) across 795 questions on real conversational data, using the same dependency-free embedder on both sides
- An [MCP server](#mcp-server) (`pip install jottermem[mcp]`) so agents can use jottermem as memory directly, not just as a library

Published on [PyPI](https://pypi.org/project/jottermem/). See [PRD.md](PRD.md) for the full plan and explicit non-goals (this is not trying to be Cognee's graph memory or Mem0 Platform's multi-tenant infra).

## Design notes / trade-offs

- **Vector search is brute-force cosine in Python by default**, accelerated by an optional `sqlite-vec` index (see above) — the brute-force path keeps a plain `pip install jottermem` genuinely dependency-free (no C extension wheels that might not exist for your platform, and no dependency on `sqlite3` being built with loadable-extension support, which Apple's system Python on macOS isn't). It's fine at hundreds of memories; measured at ~500 (see the LoCoMo benchmark above), it's already ~38x slower than the accelerated path — reach for `pip install jottermem[sqlite-vec]` well before "thousands."
- **The default embedder is lexical, not semantic** — it won't match paraphrases. It's there so `pip install jottermem` works standalone in under 5 minutes with zero infra decisions; swap in `SentenceTransformerEmbedder` or your own API-backed embedder when recall quality matters more than zero dependencies.
- **Staleness resolution is key-based, not inferred** — see above.
- **All stored embeddings are unit-normalized**, regardless of what a custom embedder returns — this keeps the sqlite-vec acceleration's Euclidean-to-cosine distance conversion exact for every embedder, not just the bundled ones.
- **`SQLiteStore` is thread-safe**, found the hard way: the MCP server runs sync tool calls in a worker-thread pool, and the default `sqlite3` connection isn't usable across threads. The connection opens with `check_same_thread=False` and every operation holds a lock.

## Releasing

`.github/workflows/publish.yml` builds and publishes on every GitHub Release via [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (no stored API token). To cut the next release: bump `version` in `pyproject.toml`, then create a GitHub Release with a matching tag.

## License

Apache-2.0
