import sqlite3

import pytest

from jottermem import Memory
from jottermem.embeddings import HashingEmbedder
from jottermem.storage import SQLiteStore

_extension_loading_supported = hasattr(sqlite3.Connection, "enable_load_extension")

try:
    import sqlite_vec  # noqa: F401

    _sqlite_vec_installed = True
except ImportError:
    _sqlite_vec_installed = False

requires_vec = pytest.mark.skipif(
    not (_extension_loading_supported and _sqlite_vec_installed),
    reason="requires a Python build with loadable-extension support and the sqlite-vec package",
)


@requires_vec
def test_vec_index_is_enabled_when_available():
    store = SQLiteStore(":memory:", dim=8, use_sqlite_vec=True)
    assert store._vec_enabled is True


@requires_vec
def test_accelerated_recall_matches_brute_force():
    facts = [
        "The user's favorite color is blue.",
        "The user works as a software engineer.",
        "The user lives in Boston.",
        "The user enjoys hiking on weekends.",
    ]
    with Memory(
        ":memory:", embedder=HashingEmbedder(dim=64), use_sqlite_vec=True
    ) as accel, Memory(
        ":memory:", embedder=HashingEmbedder(dim=64), use_sqlite_vec=False
    ) as brute:
        for mem in (accel, brute):
            for fact in facts:
                mem.remember(fact)

        for query in ["Where does the user live?", "What does the user do for work?"]:
            # Compared as sets, not lists: exact score ties (two candidates
            # at the same cosine similarity) can break in a different order
            # between vec0's internal candidate order and iter_candidates'
            # SQL row order — recall() doesn't promise a stable tie-break,
            # so that's expected, not a correctness bug.
            accel_texts = {r.memory.text for r in accel.recall(query, k=3)}
            brute_texts = {r.memory.text for r in brute.recall(query, k=3)}
            assert accel_texts == brute_texts


@requires_vec
def test_accelerated_dedup_still_works():
    with Memory(":memory:", use_sqlite_vec=True) as mem:
        first = mem.remember("The user likes tea.")
        second = mem.remember("The user likes tea.")
        assert first[0].id == second[0].id
        assert len(mem.list_memories()) == 1


@requires_vec
def test_accelerated_staleness_still_works():
    with Memory(":memory:", use_sqlite_vec=True) as mem:
        mem.remember("Works at Acme Corp.", key="employer")
        mem.remember("Works at Globex.", key="employer")

        active = mem.list_memories()
        assert len(active) == 1
        assert "Globex" in active[0].text

        results = mem.recall("Where does the user work?", k=5)
        texts = [r.memory.text for r in results]
        assert not any("Acme" in t for t in texts)


@requires_vec
def test_dimension_mismatch_falls_back_with_a_warning():
    store = SQLiteStore(":memory:", dim=4, use_sqlite_vec=True)
    assert store._vec_enabled is True
    with pytest.warns(RuntimeWarning, match="dimension mismatch"):
        store.insert(id="a", text="wrong dim", embedding=[0.1] * 8)
    assert store._vec_enabled is False


@requires_vec
def test_forget_removes_from_vec_index():
    with Memory(":memory:", use_sqlite_vec=True) as mem:
        [record] = mem.remember("A fact to forget.")
        assert mem.forget(record.id) is True
        assert mem.recall("A fact to forget.", k=5) == []


@requires_vec
def test_namespaces_stay_isolated_when_accelerated():
    with Memory(":memory:", use_sqlite_vec=True) as mem:
        mem.remember("Alice's fact.", namespace="alice")
        mem.remember("Bob's fact.", namespace="bob")
        alice_results = mem.recall("fact", namespace="alice", k=5)
        assert all(r.memory.namespace == "alice" for r in alice_results)


@requires_vec
def test_metadata_filter_falls_back_to_brute_force_even_when_accelerated():
    with Memory(":memory:", use_sqlite_vec=True) as mem:
        mem.remember("Fact about work.", metadata={"topic": "work"})
        mem.remember("Fact about food.", metadata={"topic": "food"})
        results = mem.recall("fact", filter={"topic": "work"}, k=5)
        assert len(results) == 1
        assert results[0].memory.metadata["topic"] == "work"


@pytest.mark.skipif(
    _extension_loading_supported,
    reason="only meaningful on a Python build that cannot load extensions",
)
def test_strict_mode_raises_when_extension_loading_unsupported():
    with pytest.raises(RuntimeError):
        SQLiteStore(":memory:", dim=8, use_sqlite_vec=True)


def test_use_sqlite_vec_false_never_enables_acceleration():
    store = SQLiteStore(":memory:", dim=8, use_sqlite_vec=False)
    assert store._vec_enabled is False


def test_auto_mode_never_raises_regardless_of_platform():
    store = SQLiteStore(":memory:", dim=8, use_sqlite_vec="auto")
    assert store._vec_enabled in (True, False)


def test_no_dim_never_enables_acceleration():
    # Backward-compatible default: callers that don't pass `dim` (as the
    # existing low-level SQLiteStore tests don't) never get acceleration,
    # regardless of use_sqlite_vec.
    store = SQLiteStore(":memory:")
    assert store._vec_enabled is False
