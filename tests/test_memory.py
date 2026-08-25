from jottermem import Memory


def test_remember_and_recall_roundtrip(memory):
    memory.remember("I live in Boston. I love hiking on weekends.")
    results = memory.recall("Where does the user live?", k=1)
    assert len(results) == 1
    assert "Boston" in results[0].memory.text


def test_recall_ranks_relevant_fact_higher(memory):
    memory.remember("The user's favorite color is blue.")
    memory.remember("The user works as a software engineer.")
    results = memory.recall("What is the user's favorite color?", k=2)
    assert "blue" in results[0].memory.text.lower()


def test_dedup_skips_near_duplicate(memory):
    first = memory.remember("The user likes tea.")
    second = memory.remember("The user likes tea.")
    assert len(first) == 1
    assert len(second) == 1
    assert first[0].id == second[0].id
    assert len(memory.list_memories()) == 1


def test_key_based_supersession(memory):
    memory.remember("Works at Acme Corp.", key="employer")
    memory.remember("Works at Globex.", key="employer")

    active = memory.list_memories()
    assert len(active) == 1
    assert "Globex" in active[0].text

    everything = memory.list_memories(include_superseded=True)
    assert len(everything) == 2
    superseded = [r for r in everything if r.status == "superseded"][0]
    assert "Acme" in superseded.text


def test_dedup_match_can_claim_a_key(memory):
    """A fact stored without a key, then re-remembered with a key, should
    have that key applied to the existing (deduped) record rather than
    silently dropping it — otherwise a later same-key update wouldn't know
    to supersede it."""
    memory.remember("The user's favorite drink is coffee.")
    memory.remember("The user's favorite drink is coffee.", key="drink")
    memory.remember("The user's favorite drink is green tea now.", key="drink")

    active = memory.list_memories()
    assert len(active) == 1
    assert "green tea" in active[0].text

    everything = memory.list_memories(include_superseded=True)
    assert len(everything) == 2
    superseded = [r for r in everything if r.status == "superseded"][0]
    assert "coffee" in superseded.text
    assert superseded.key == "drink"


def test_forget_removes_memory(memory):
    [record] = memory.remember("A one-off fact.")
    assert memory.forget(record.id) is True
    assert memory.list_memories() == []
    assert memory.forget(record.id) is False


def test_list_memories_filters_by_metadata(memory):
    memory.remember("Fact about work.", metadata={"topic": "work"})
    memory.remember("Fact about food.", metadata={"topic": "food"})
    work_facts = memory.list_memories(filter={"topic": "work"})
    assert len(work_facts) == 1
    assert work_facts[0].metadata["topic"] == "work"


def test_namespaces_are_isolated(memory):
    memory.remember("Alice's fact.", namespace="alice")
    memory.remember("Bob's fact.", namespace="bob")
    assert len(memory.list_memories(namespace="alice")) == 1
    assert len(memory.list_memories(namespace="bob")) == 1


def test_recall_excludes_superseded_by_default(memory):
    memory.remember("Works at Acme Corp.", key="employer")
    memory.remember("Works at Globex.", key="employer")
    results = memory.recall("Where does the user work?", k=5)
    texts = [r.memory.text for r in results]
    assert not any("Acme" in t for t in texts)
