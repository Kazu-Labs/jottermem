"""Synthetic long-term-memory benchmark: jottermem vs. naive top-K RAG.

Not the LoCoMo dataset — a small, self-contained, reproducible scenario
built to exercise exactly the failure mode the PRD calls out: a fact that
changes over the course of a conversation (employer, city, favorite drink),
each restated multiple times, plus one verbatim repeat.

Both sides use the *same* embedder (jottermem's HashingEmbedder), so the
comparison isolates the memory-layer logic (dedup + key-based staleness +
keyword-boosted hybrid recall) from embedding quality.

Run: python benchmarks/staleness_benchmark.py
"""

from __future__ import annotations

from dataclasses import dataclass

from jottermem import Memory
from jottermem.embeddings import HashingEmbedder
from jottermem.similarity import cosine

# (text, key). key=None means "no evolving identity" (e.g. the verbatim repeat
# still shares the prior fact's key so it exercises dedup, not supersession).
CONVERSATION = [
    ("The user works at Initech.", "employer"),
    ("The user's favorite drink is coffee.", "drink"),
    ("The user works at Acme Corp now.", "employer"),
    ("The user lives in Seattle.", "city"),
    ("The user's favorite drink is now green tea.", "drink"),
    ("The user works at Acme Corp now.", "employer"),  # verbatim repeat -> dedup
    ("The user moved to Portland.", "city"),
    ("The user works at Globex Corporation.", "employer"),
]

QUERIES = [
    ("Where does the user currently work?", "Globex"),
    ("What city does the user live in?", "Portland"),
    ("What is the user's favorite drink?", "green tea"),
]


@dataclass
class Report:
    label: str
    stored_count: int
    surfaced_count: int
    correct: int
    total: int
    top1_by_query: list[tuple[str, str]]


def run_naive(embedder: HashingEmbedder) -> Report:
    """Baseline: every line is its own memory, plain cosine top-1, no dedup
    or staleness handling — the standard "chunk it and embed it" approach."""
    rows: list[tuple[str, list[float]]] = []
    for text, _key in CONVERSATION:
        rows.append((text, embedder([text])[0]))

    top1 = []
    correct = 0
    for query, expected_substr in QUERIES:
        qvec = embedder([query])[0]
        best_text, _ = max(rows, key=lambda r: cosine(qvec, r[1]))
        top1.append((query, best_text))
        if expected_substr.lower() in best_text.lower():
            correct += 1

    return Report(
        label="naive top-K (no dedup, no staleness handling)",
        stored_count=len(rows),
        surfaced_count=len(rows),
        correct=correct,
        total=len(QUERIES),
        top1_by_query=top1,
    )


def run_jottermem() -> Report:
    with Memory(":memory:", embedder=HashingEmbedder()) as mem:
        for text, key in CONVERSATION:
            mem.remember(text, key=key)

        top1 = []
        correct = 0
        for query, expected_substr in QUERIES:
            results = mem.recall(query, k=1)
            best_text = results[0].memory.text if results else ""
            top1.append((query, best_text))
            if expected_substr.lower() in best_text.lower():
                correct += 1

        stored_count = len(mem.list_memories(include_superseded=True))
        surfaced_count = len(mem.list_memories())

        return Report(
            label="jottermem (dedup + key-based staleness + hybrid recall)",
            stored_count=stored_count,
            surfaced_count=surfaced_count,
            correct=correct,
            total=len(QUERIES),
            top1_by_query=top1,
        )


def print_report(report: Report) -> None:
    print(f"\n{report.label}")
    print("-" * len(report.label))
    print(f"  lines written:           {len(CONVERSATION)}")
    print(f"  memories stored:         {report.stored_count}")
    print(f"  memories visible to recall(): {report.surfaced_count}")
    print(f"  current-fact accuracy:   {report.correct}/{report.total}")
    for query, answer in report.top1_by_query:
        print(f"    Q: {query}\n    A: {answer!r}")


def main() -> None:
    embedder = HashingEmbedder()
    naive = run_naive(embedder)
    jotter = run_jottermem()

    print_report(naive)
    print_report(jotter)

    print("\nSummary")
    print("-------")
    print(f"  naive accuracy:     {naive.correct}/{naive.total}")
    print(f"  jottermem accuracy: {jotter.correct}/{jotter.total}")
    print(
        f"  memories surfaced to recall(): naive={naive.surfaced_count}, "
        f"jottermem={jotter.surfaced_count} "
        f"({naive.surfaced_count - jotter.surfaced_count} fewer stale/duplicate "
        "facts competing with the current ones)"
    )


if __name__ == "__main__":
    main()
