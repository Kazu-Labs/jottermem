import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benchmarks"))

from staleness_benchmark import run_jottermem, run_naive  # noqa: E402
from jottermem.embeddings import HashingEmbedder  # noqa: E402


def test_naive_baseline_fails_on_stale_facts():
    """Regression guard for the benchmark's headline claim: with the same
    embedder and no dedup/staleness handling, naive top-1 does not
    reliably surface the current fact when it's been restated over time."""
    report = run_naive(HashingEmbedder())
    assert report.correct < report.total
    assert report.surfaced_count == report.stored_count == 8


def test_jottermem_beats_naive_on_current_fact_accuracy():
    naive = run_naive(HashingEmbedder())
    jotter = run_jottermem()

    assert jotter.correct > naive.correct
    assert jotter.correct == jotter.total  # gets every current-fact query right

    # Dedup (1 verbatim repeat) + supersession (3 evolving facts) mean fewer
    # memories compete for attention at recall time than raw naive storage.
    assert jotter.surfaced_count < naive.surfaced_count
