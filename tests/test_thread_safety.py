import threading

from jottermem import Memory

# Genuinely distinct sentences, not a templated string differing by one short
# token — HashingEmbedder is only 256-dim by default, and short near-identical
# templated strings (e.g. f"Fact number {i}.") have a real chance of two
# different numbers hashing into the same bucket, making them indistinguishable
# from each other and triggering *correct* dedup rather than a race.
_DISTINCT_FACTS = [
    "The user's favorite color is blue.",
    "The user works as a software engineer in Boston.",
    "The user has a dog named Max.",
    "The user prefers tea over coffee in the morning.",
    "The user is learning to play the violin.",
    "The user's favorite cuisine is Thai food.",
    "The user recently moved to a new apartment.",
    "The user is training for a half marathon.",
    "The user collects vintage vinyl records.",
    "The user volunteers at an animal shelter on weekends.",
    "The user is fluent in Spanish and Portuguese.",
    "The user grows tomatoes in a small garden.",
    "The user works remotely four days a week.",
    "The user is reading a biography about Marie Curie.",
    "The user plays chess competitively.",
    "The user's sibling just started college.",
    "The user is renovating their kitchen this summer.",
    "The user commutes by bicycle when the weather allows.",
    "The user recently adopted a rescue cat.",
    "The user is planning a trip to Japan next spring.",
]


def test_concurrent_remember_from_multiple_threads():
    """Regression test: sqlite3 connections aren't usable across threads by
    default (`check_same_thread=True`), which surfaces immediately in any
    framework that runs request/tool handlers in a thread pool — the MCP
    SDK does exactly this for sync tool functions via
    anyio.to_thread.run_sync. SQLiteStore opens with
    check_same_thread=False and locks every operation, so this must not
    raise regardless of which thread each call lands on."""
    mem = Memory(":memory:")
    errors = []

    def worker(text: str) -> None:
        try:
            mem.remember(text)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(text,)) for text in _DISTINCT_FACTS]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(mem.list_memories()) == len(_DISTINCT_FACTS)


def test_concurrent_recall_from_multiple_threads():
    mem = Memory(":memory:")
    mem.remember("The user's favorite color is blue.")
    mem.remember("The user works as a software engineer.")
    errors = []
    results = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            r = mem.recall("What color does the user like?", k=1)
            with lock:
                results.append(r[0].memory.text)
        except Exception as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert all("blue" in r.lower() for r in results)
