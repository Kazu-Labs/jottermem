# Benchmarks

## Staleness benchmark

**What it tests:** the specific failure mode section 1.2 of the [PRD](PRD.md) calls out — "a fact like 'works at Company X' is correct until it isn't, and naive memory systems retrieve stale facts with the same confidence as current ones."

**What it is not:** the LoCoMo dataset, or any other external long-term-memory benchmark. It's a small, self-contained, fully reproducible synthetic scenario (`benchmarks/staleness_benchmark.py`) built to exercise that one failure mode directly, and it's pinned by a regression test (`tests/test_benchmark.py`) so the numbers below can't silently drift. A LoCoMo-style external benchmark is still on the roadmap (see PRD milestone 4) — this is the first, narrower proof point.

**Setup:** an 8-line synthetic conversation where three facts evolve over time (employer changes twice, city changes once, favorite drink changes once) and one line is a verbatim repeat. Both sides use jottermem's own `HashingEmbedder`, so the comparison isolates the memory-layer logic — dedup, key-based staleness, hybrid recall — from embedding quality.

- **Naive top-K:** every line stored as its own memory, plain cosine top-1 at query time. This is the "vector store + top-K" baseline the PRD frames as the status quo.
- **jottermem:** `remember()` with a stable `key` per evolving fact (`employer`, `city`, `drink`), `recall()` with default dedup + supersession + keyword-boosted hybrid scoring.

**Result** (`python benchmarks/staleness_benchmark.py`):

| | naive top-K | jottermem |
|---|---|---|
| lines written | 8 | 8 |
| memories stored | 8 | 7 (1 verbatim repeat deduped) |
| memories visible to `recall()` | 8 | 3 (4 superseded facts + the dedup hidden) |
| current-fact query accuracy | **0 / 3** | **3 / 3** |

Naive top-1 picks a stale fact for every query — same-subject restatements (`"works at Initech"` / `"...Acme Corp"` / `"...Globex"`) are close enough in cosine similarity that whichever one the index happens to rank first wins, with no signal that two of the three are outdated. jottermem's `recall()` only has the current fact to return for each subject, because the superseded ones were excluded by construction — not by winning a closer ranking.

Run it yourself:

```bash
python benchmarks/staleness_benchmark.py
```

## LoCoMo retrieval benchmark

**What it tests:** whether jottermem's memory-layer logic — atomic fact extraction plus hybrid keyword-boosted recall — actually improves retrieval on real conversational data, not just the synthetic scenario above. Uses [LoCoMo](https://github.com/snap-research/locomo) (Maharana et al., *"Evaluating Very Long-Term Conversational Memory of LLM Agents,"* 2024), a published benchmark of 10 long-term multi-session conversations (5,882 turns total) with human-annotated QA pairs.

**What it is not:** an answer-generation benchmark. jottermem's `recall()` returns memories, not generated answers, so this measures *retrieval* — Recall@k over the paper's single-hop QA category (795 questions, each with exactly one ground-truth evidence turn): does that turn appear in the top-k results? It's also not using a semantic embedder — both sides use jottermem's own dependency-free `HashingEmbedder`, isolating the memory-layer logic from embedding quality, same as the staleness benchmark above.

**Not vendored:** the dataset's source repo carries no asserted open-source license, so `benchmarks/locomo_benchmark.py` downloads it at run time into `benchmarks/data/` (gitignored) rather than redistributing a copy here.

- **Naive top-K:** every conversation turn stored as its own memory, plain cosine ranking at query time.
- **jottermem:** `remember()` per turn (splits multi-sentence turns into atomic facts, dedups near-identical restatements), `recall()` with hybrid keyword-boosted scoring.

**Result** (`python benchmarks/locomo_benchmark.py`, ~6 minutes, 795 single-hop questions across 10 conversations):

| k | naive Recall@k | jottermem Recall@k |
|---|---|---|
| 1 | 8.8% | **17.2%** |
| 3 | 15.7% | **27.4%** |
| 5 | 18.9% | **31.7%** |
| 10 | 24.9% | **37.7%** |

jottermem roughly **doubles** naive top-K's Recall@k at every k on real conversational data. The absolute numbers are modest by design — `HashingEmbedder` is lexical, not semantic, so this isn't state-of-the-art retrieval — but the *relative* improvement is the point: splitting turns into atomic facts (directly addressing the chunk-boundary problem from [PRD §1.2](PRD.md)) plus hybrid keyword scoring measurably improves what gets retrieved, using the exact same embedder on both sides. Swapping in `SentenceTransformerEmbedder` would likely raise the absolute numbers further on both sides; that comparison isn't run here yet.

**Acceleration speedup, same data:** brute-force cosine scanning is the bottleneck at this scale — on `conv-26` (419 turns, 69 questions), `remember()` + `recall()` for the whole conversation took **14.8s** brute-force versus **0.39s** with `sqlite-vec` acceleration (`use_sqlite_vec=True`), a **~38x** speedup with identical results. This is what the [sqlite-vec acceleration](README.md#accelerating-search-with-sqlite-vec) is for.

Run it yourself (downloads ~2.7MB on first run):

```bash
python benchmarks/locomo_benchmark.py
```
