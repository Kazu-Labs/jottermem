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
