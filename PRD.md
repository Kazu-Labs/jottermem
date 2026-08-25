# PRD: jottermem — A Dead-Simple, Embeddable Memory Layer for AI Apps
*(single file, zero infra, zero account — the SQLite of agent memory)*

**Status:** Draft v1
**Owner:** TBD
**Last updated:** 2026-08-24

---

## 1. Research Summary — What Already Exists

Before scoping this, it's worth being precise about which layer of the stack is already solved, because two very different things get called "RAG/memory" and they have different levels of maturity.

### 1.1 The storage layer is solved and commoditized
Embeddable vector search is no longer a gap. `sqlite-vec` gives local vector search with zero infrastructure in the same file as structured data. LanceDB offers disk-based, larger-than-RAM embedded vector storage with no server required. ChromaDB is simple, in-memory-first, and the default for prototyping. All three run in-process, all three are mature, all three are free. **Building "yet another embeddable vector store" is not a real opportunity** — that race is over and the incumbents are good.

### 1.2 The memory layer (above storage) is where the real gap is
A "memory" system is more than a vector index: it has to decide what to store, deduplicate and update facts over time, resolve conflicts when new information contradicts old, and retrieve the *right* thing, not just the *semantically closest* thing. This is where the actual product opportunity lives, and it splits into two problems the market has not solved together:

**A. The unsolved technical problems** (true across every existing tool, including the well-funded ones):
- **Semantic drift** — top-K cosine similarity doesn't reliably match intent; a query like "do the usual thing" retrieves memories containing the literal word "usual" rather than the behavioral pattern it implies.
- **Chunk boundary problems** — raw conversational chunks pull in large blocks of irrelevant surrounding context; you retrieve 3,000 tokens to surface one relevant sentence.
- **Memory staleness / conflicting facts** — a fact like "works at Company X" is correct until it isn't, and naive memory systems retrieve stale facts with the same confidence as current ones, with no error signal.
- **No coherent abstraction** — engineers are still hand-wiring storage, chunking, and embedding logic themselves because there's no clean primitive that owns "add a memory" and "get the right memories back" as a unit.

**B. The unsolved packaging problem** (this is the part specific to indie devs / small teams, and it's the actual wedge):
Purpose-built memory frameworks exist — **Mem0**, **Cognee**, **Zep**, **Letta** — and they're good at (A). But every one of them assumes you're either paying for a hosted platform or standing up real infrastructure:
- Mem0's self-hosted server orchestrates **Postgres + a vector store + optionally Neo4j**, ships with **no authentication by default** (`allow_origins=["*"]`), and requires a reverse proxy to be safe on a network — independent analysis rates it "moderate complexity," with **two stateful backends to back up, version, and keep available**.
- Mem0's default *cloud* path is the one-`pip install` experience; the genuinely local path is the one that requires Docker Compose and infra ops.
- Cognee is graph-native and enterprise-positioned — a good fit for teams already running graph infrastructure, overkill for a solo dev's side project.
- Zep and Letta both lean toward production agent infrastructure, not a "drop this into a script" experience.
- Smaller/newer entrants (e.g., MemoClaw) trade one problem for another — cloud-only, no self-hosting at all, and in at least one case a crypto-wallet payment requirement.

**The conclusion:** nobody has shipped the memory-layer equivalent of `sqlite-vec` — something that treats "add a memory, get the right memory back, keep it correct over time" as a single embeddable, single-file, zero-infra library. The storage primitive got this treatment (SQLite itself, then sqlite-vec). The memory primitive has not.

---

## 2. Problem Statement

An indie developer or small team building an AI app that needs to remember things across sessions (user preferences, prior conversation facts, project context) faces a forced choice today:

1. **Hand-roll it** on top of a vector store — solving chunking, dedup, and staleness themselves, badly, because these are genuinely hard problems that well-funded teams are still actively researching.
2. **Adopt a memory framework** (Mem0, Cognee, Zep) — which solves the hard problems, but drags in a hosted account, a Postgres+vector+graph stack, Docker, and ops burden disproportionate to a project that might have a handful of users.

There is no third option: a library that behaves like SQLite — `pip install`, one file on disk, no server, no account, no Docker — but internally does the things that make a memory system actually good (atomic fact extraction, dedup, conflict/staleness handling, retrieval that resists semantic drift) rather than just wrapping a vector index and calling it memory.

---

## 3. Goal

Ship an open-source, embeddable memory library that:

- Runs entirely on-device: **one file, no server, no account, no Docker**, in the spirit of SQLite/sqlite-vec
- Solves the memory-quality problems that naive "vector store + top-K" setups don't — atomic fact extraction, deduplication, conflict/staleness resolution — without requiring Postgres, Neo4j, or a hosted platform
- Gives a developer a working `remember()` / `recall()` API in minutes, with sensible defaults, and room to swap components (embedding model, LLM extractor) later
- Is honest about trade-offs: this is not a replacement for graph-native enterprise memory (Cognee) or multi-tenant hosted infra (Mem0 Platform) at scale — it's the right-sized tool for the 90% of projects that will never need those

**North star metric:** time from `pip install` to a working `remember()`/`recall()` loop with zero infrastructure decisions, and recall quality that measurably beats naive top-K vector search on the same data.

---

## 4. Target Users

| Persona | Need | Why existing options fall short |
|---|---|---|
| **Indie hacker** building a personal assistant / companion app | Wants the app to remember user facts across sessions without running infra | Mem0 self-hosted needs Postgres+vector+optionally Neo4j; cloud Mem0 means an account and usage billing for a hobby project |
| **Small startup (2–10 eng)** shipping a personalized AI feature | Wants memory quality (dedup, staleness handling) without committing to a stateful ops burden this early | Same infra tax, paid before it's justified by scale |
| **Solo dev prototyping an agent** | Wants to validate whether memory improves their product before investing in infrastructure | Hand-rolling naive RAG hits semantic drift and chunk-boundary problems immediately; adopting a full framework is premature commitment |
| **OSS agent-framework maintainer** | Wants a default memory backend to recommend that doesn't force their users into an account or a stack | No current option is both good and zero-infra |

Non-goal for v1: teams that need multi-tenant, distributed, or graph-scale memory (millions of users, complex entity graphs) — that's Mem0 Platform / Cognee territory, and that's fine; this tool should say so clearly rather than pretend to compete there.

---

## 5. Scope — v1 (MVP)

### 5.1 Core storage
- Single SQLite file (leveraging `sqlite-vec` for the vector index) holding both structured metadata and embeddings — no separate services
- No required external dependency beyond the embedding model itself (local model by default, e.g. a small sentence-transformer, with the option to bring your own/API-based embeddings)

### 5.2 The memory API (this is the actual product, not the storage)
- `remember(text, metadata={})` — extracts atomic, normalized facts from raw input rather than storing raw chunks verbatim (directly targets the chunk-boundary problem)
- `recall(query, k=5)` — hybrid retrieval (semantic + keyword/metadata filtering) to reduce pure-cosine semantic drift, not just nearest-neighbor search
- **Deduplication on write** — new facts are checked against existing memories before insertion; near-duplicates are merged rather than piling up
- **Conflict/staleness handling** — when a new fact contradicts an existing one (e.g., updated employer, updated preference), the system marks the old fact superseded rather than retrieving both with equal confidence
- `forget(id)` / `list_memories(filter)` for explicit management

### 5.3 Pluggable components, sane defaults
- Default local embedding model, swappable for any embedding function
- Default lightweight extraction (rule-based + optional small local LLM) for atomic fact extraction, swappable for a call to any LLM API if the developer wants higher-quality extraction
- Everything works with zero configuration; every default is overridable

### 5.4 Packaging & DX
- `pip install jottermem`
- Quickstart: `remember()` a few facts, `recall()` them, in under 5 minutes, no infra setup screen at any point
- Ships as a genuinely single-file-storage library — no Postgres, no Neo4j, no Docker Compose, no account

---

## 6. Explicitly Out of Scope for v1

- Graph-native reasoning / multi-hop entity graphs (Cognee's territory) — a possible v2 extension once the core primitive is solid, not a v1 requirement
- Multi-tenant / distributed deployment (Mem0 Platform's territory)
- Hosted/cloud version
- Non-Python bindings (v2 candidate given adoption patterns in this space)
- Building a new embedding model or vector index algorithm — reuse proven primitives (`sqlite-vec`) rather than reinventing the storage layer, which is explicitly not the gap

---

## 7. Success Metrics

- **Adoption:** GitHub stars, PyPI weekly downloads, agent-framework integrations
- **Quality proof point:** published benchmark showing recall/precision improvement over naive top-K vector search on a standard long-term-memory benchmark (e.g., LoCoMo-style eval), since "we handle staleness and dedup" needs to be demonstrated, not just claimed
- **Activation:** % of installs reaching a working `remember()`/`recall()` call with zero non-Python setup steps
- **Community health:** external PRs, especially around extraction-quality tuning and additional embedding-model integrations

---

## 8. Risks & Open Questions

| Risk | Mitigation |
|---|---|
| Fact extraction quality is genuinely hard (this is the same problem Mem0's research team is actively iterating on) | Ship a solid rule-based/lightweight default, make LLM-based extraction a one-line opt-in for developers who want it, and be transparent in docs about the trade-off rather than overclaiming default quality |
| "Just use Mem0 OSS" objection | Lead with *actually zero infra* — no Postgres, no Neo4j, no Docker, no reverse proxy needed for a safe default — a genuinely different operational tradeoff, not a feature race |
| Scope creep toward graph memory / enterprise features | Hold the v1 line; the wedge is being the *simple* option, not the *most powerful* one |
| Recall quality claims without evidence | Publish benchmark numbers against naive top-K RAG before/alongside launch, not just in marketing copy |
| Single-file SQLite doesn't scale past a certain size | Be explicit in docs about the scale ceiling and point users to Mem0/Cognee/graph options when they outgrow this tool — honesty here builds trust for the use cases it's actually right for |

---

## 9. Rough Milestones

1. **Week 1–2:** Core storage on `sqlite-vec`, basic `remember()`/`recall()` with naive top-K (baseline to improve against)
2. **Week 3–4:** Atomic fact extraction on write, deduplication logic
3. **Week 5–6:** Conflict/staleness resolution, hybrid retrieval to address semantic drift
4. **Week 7:** Benchmark against naive RAG on a standard long-term memory eval; publish results
5. **Week 8:** Docs, quickstart, launch (Show HN / r/LocalLLaMA / relevant agent-framework Discords) — lead with "zero infra, and here's the benchmark proving the memory quality"
6. **Post-launch:** framework integrations (LangChain, LlamaIndex, common agent frameworks) based on early adopter requests

---

## 10. Open Decisions

- License (MIT vs Apache 2.0 — Apache 2.0 likely safer for company adoption, and matches Mem0's own choice, easing any future contribution crossover)
- Default extraction approach: pure rule-based (zero LLM dependency, faster, lower quality) vs. requiring a small local LLM by default (better quality, heavier default install) — needs a decision before Week 3
- Whether v1 should support pluggable storage backends (e.g., Postgres for teams that outgrow SQLite) or stay deliberately single-file to protect the "zero infra" positioning
