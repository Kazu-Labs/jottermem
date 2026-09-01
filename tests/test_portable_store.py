import pytest

from jottermem.portable import PortableStore


@pytest.fixture
def store(tmp_path):
    return PortableStore(tmp_path / "mem")


def test_creates_root_and_index(tmp_path):
    root = tmp_path / "mem"
    PortableStore(root)
    assert root.is_dir()
    assert (root / "index.json").exists()


def test_write_creates_readable_markdown_file(store):
    store.write("work", "Started as PM at Acme Corp.")
    content = store.read("work")
    assert content is not None
    assert "Started as PM at Acme Corp." in content
    assert (store.root / "work.md").exists()


def test_write_dedupes_identical_fact(store):
    assert store.write("work", "Likes tea.") is True
    assert store.write("work", "Likes tea.") is False
    assert store.read("work").count("Likes tea.") == 1


def test_write_dedupe_is_case_insensitive(store):
    store.write("work", "Likes tea.")
    assert store.write("work", "LIKES TEA.") is False


def test_write_rejects_empty_text(store):
    with pytest.raises(ValueError):
        store.write("work", "   ")


def test_read_missing_topic_returns_none(store):
    assert store.read("nonexistent") is None


def test_list_topics_reflects_writes(store):
    store.write("work", "Fact one.")
    store.write("preferences", "Fact two.")
    store.write("work", "Fact three.")

    topics = {t.topic: t.count for t in store.list_topics()}
    assert topics == {"work": 2, "preferences": 1}


def test_search_finds_matching_lines(store):
    store.write("work", "Works at Acme Corp.")
    store.write("preferences", "Prefers async communication.")

    hits = store.search("Acme")
    assert len(hits) == 1
    assert hits[0].topic == "work"
    assert "Acme" in hits[0].line


def test_search_can_scope_to_one_topic(store):
    store.write("work", "Shared word: launch.")
    store.write("preferences", "Shared word: launch.")

    hits = store.search("launch", topic="work")
    assert len(hits) == 1
    assert hits[0].topic == "work"


def test_search_empty_query_returns_nothing(store):
    store.write("work", "Some fact.")
    assert store.search("") == []


def test_topic_slugification_is_filesystem_safe(store):
    store.write("Work / Projects!", "A fact.")
    assert (store.root / "work-projects.md").exists()


def test_reopening_store_sees_prior_writes(tmp_path):
    root = tmp_path / "mem"
    PortableStore(root).write("work", "Persisted fact.")
    reopened = PortableStore(root)
    assert "Persisted fact." in reopened.read("work")


def test_overwrite_replaces_content_and_reindexes(store):
    store.write("work", "Original fact.")
    store.overwrite("work", "# work\n\n- [2026-01-01T00:00:00Z] Edited fact.\n")

    assert "Edited fact." in store.read("work")
    assert "Original fact." not in store.read("work")
    assert store.list_topics()[0].count == 1


def test_delete_topic_removes_file_and_index_entry(store):
    store.write("work", "A fact.")
    assert (store.root / "work.md").exists()

    assert store.delete_topic("work") is True
    assert not (store.root / "work.md").exists()
    assert store.list_topics() == []
    assert store.read("work") is None


def test_delete_topic_returns_false_when_missing(store):
    assert store.delete_topic("nonexistent") is False


def test_delete_topic_does_not_affect_other_topics(store):
    store.write("work", "Fact one.")
    store.write("preferences", "Fact two.")

    store.delete_topic("work")

    assert {t.topic for t in store.list_topics()} == {"preferences"}
