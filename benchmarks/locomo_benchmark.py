"""Retrieval-quality benchmark on the LoCoMo long-term-memory dataset's
single-hop QA subset: does recall() surface the ground-truth evidence
turn in its top-k results, compared to a naive top-K baseline using the
*same* embedder?

Paper: Maharana et al., "Evaluating Very Long-Term Conversational Memory
of LLM Agents" (2024), https://arxiv.org/abs/2402.17753
Dataset: https://github.com/snap-research/locomo (data/locomo10.json)

Not vendored: that repo carries no asserted open-source license, so this
script downloads the dataset at run time into benchmarks/data/ (gitignored)
on first run, rather than redistributing a copy in this repo. Requires
network access the first time you run it.

This measures *retrieval*, not answer generation. jottermem's recall()
returns memories, not generated answers, so the metric is Recall@k over
the paper's single-hop category (questions with exactly one ground-truth
evidence turn): does that evidence turn appear in the top-k results? This
isolates the same thing BENCHMARKS.md's staleness benchmark isolates —
memory-layer retrieval quality — rather than an LLM's answer-generation
quality, which jottermem itself doesn't attempt.

Run: python benchmarks/locomo_benchmark.py
"""

from __future__ import annotations

import json
import urllib.request
from collections import defaultdict
from pathlib import Path

from jottermem import Memory
from jottermem.embeddings import HashingEmbedder
from jottermem.similarity import cosine

DATA_URL = "https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json"
CACHE_PATH = Path(__file__).parent / "data" / "locomo10.json"
K_VALUES = [1, 3, 5, 10]
SINGLE_HOP_CATEGORY = 4


def load_dataset() -> list[dict]:
    if not CACHE_PATH.exists():
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        print(f"Downloading LoCoMo dataset to {CACHE_PATH} ...")
        urllib.request.urlretrieve(DATA_URL, CACHE_PATH)
    with open(CACHE_PATH) as f:
        return json.load(f)


def conversation_turns(conversation: dict) -> list[dict]:
    session_keys = sorted(
        (
            k
            for k in conversation
            if k.startswith("session_") and not k.endswith("date_time")
        ),
        key=lambda k: int(k.split("_")[1]),
    )
    turns = []
    for key in session_keys:
        turns.extend(conversation[key])
    return turns


def single_hop_questions(qa: list[dict]) -> list[dict]:
    return [
        q
        for q in qa
        if q.get("category") == SINGLE_HOP_CATEGORY and len(q.get("evidence", [])) == 1
    ]


def run_naive(
    turns: list[dict], questions: list[dict], embedder: HashingEmbedder
) -> dict[int, int]:
    """Every turn stored as its own memory, plain cosine top-k, no dedup."""
    rows = [(turn["dia_id"], embedder([turn["text"]])[0]) for turn in turns]
    hits: dict[int, int] = defaultdict(int)
    for q in questions:
        evidence = q["evidence"][0]
        qvec = embedder([q["question"]])[0]
        ranked_ids = [
            dia_id
            for dia_id, _ in sorted(rows, key=lambda r: cosine(qvec, r[1]), reverse=True)
        ]
        for k in K_VALUES:
            if evidence in ranked_ids[:k]:
                hits[k] += 1
    return hits


def run_jottermem(
    turns: list[dict], questions: list[dict], embedder: HashingEmbedder
) -> dict[int, int]:
    with Memory(":memory:", embedder=embedder) as mem:
        # remember() can extract multiple atomic facts from one turn, or
        # dedup a turn against an earlier near-identical one, so a single
        # stored record can correspond to more than one source dia_id.
        record_dia_ids: dict[str, set] = defaultdict(set)
        for turn in turns:
            for record in mem.remember(turn["text"], metadata={"speaker": turn["speaker"]}):
                record_dia_ids[record.id].add(turn["dia_id"])

        hits: dict[int, int] = defaultdict(int)
        max_k = max(K_VALUES)
        for q in questions:
            evidence = q["evidence"][0]
            results = mem.recall(q["question"], k=max_k)
            for k in K_VALUES:
                if any(evidence in record_dia_ids[r.memory.id] for r in results[:k]):
                    hits[k] += 1
    return hits


def main() -> None:
    dataset = load_dataset()
    embedder = HashingEmbedder()

    naive_hits: dict[int, int] = defaultdict(int)
    jotter_hits: dict[int, int] = defaultdict(int)
    total_questions = 0

    for conversation in dataset:
        turns = conversation_turns(conversation["conversation"])
        questions = single_hop_questions(conversation["qa"])
        turn_ids = {t["dia_id"] for t in turns}
        questions = [q for q in questions if q["evidence"][0] in turn_ids]
        total_questions += len(questions)

        n_hits = run_naive(turns, questions, embedder)
        j_hits = run_jottermem(turns, questions, embedder)
        for k in K_VALUES:
            naive_hits[k] += n_hits[k]
            jotter_hits[k] += j_hits[k]

        print(
            f"{conversation['sample_id']}: {len(turns)} turns, "
            f"{len(questions)} single-hop questions"
        )

    print(f"\n{total_questions} single-hop questions across {len(dataset)} conversations\n")
    print(f"{'k':>4}  {'naive Recall@k':>15}  {'jottermem Recall@k':>19}")
    for k in K_VALUES:
        naive_r = naive_hits[k] / total_questions
        jotter_r = jotter_hits[k] / total_questions
        print(f"{k:>4}  {naive_r:>14.1%}  {jotter_r:>18.1%}")


if __name__ == "__main__":
    main()
