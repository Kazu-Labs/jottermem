from jottermem.storage.sqlite_store import SQLiteStore, pack_embedding, unpack_embedding


def test_pack_unpack_roundtrip():
    vec = [0.1, -0.5, 2.0, 0.0]
    unpacked = unpack_embedding(pack_embedding(vec))
    assert all(abs(a - b) < 1e-6 for a, b in zip(vec, unpacked))


def test_insert_and_get():
    store = SQLiteStore(":memory:")
    record = store.insert(
        id="a", text="likes tea", embedding=[1.0, 0.0], metadata={"source": "chat"}
    )
    fetched = store.get("a")
    assert fetched is not None
    assert fetched.text == "likes tea"
    assert fetched.metadata == {"source": "chat"}
    assert fetched.status == "active"
    assert record.id == fetched.id


def test_delete():
    store = SQLiteStore(":memory:")
    store.insert(id="a", text="x", embedding=[1.0])
    assert store.delete("a") is True
    assert store.get("a") is None
    assert store.delete("a") is False


def test_supersede_marks_old_and_links_new():
    store = SQLiteStore(":memory:")
    store.insert(id="old", text="works at Acme", embedding=[1.0], key="employer")
    store.supersede("old", superseded_by="new")
    old = store.get("old")
    assert old.status == "superseded"
    assert old.superseded_by == "new"


def test_find_active_by_key_ignores_superseded():
    store = SQLiteStore(":memory:")
    store.insert(id="old", text="works at Acme", embedding=[1.0], key="employer")
    store.supersede("old", superseded_by="new")
    store.insert(id="new", text="works at Globex", embedding=[1.0], key="employer")
    found = store.find_active_by_key("default", "employer")
    assert found.id == "new"


def test_list_filters_by_namespace_and_metadata():
    store = SQLiteStore(":memory:")
    store.insert(id="a", text="x", embedding=[1.0], namespace="alice", metadata={"topic": "work"})
    store.insert(id="b", text="y", embedding=[1.0], namespace="alice", metadata={"topic": "food"})
    store.insert(id="c", text="z", embedding=[1.0], namespace="bob", metadata={"topic": "work"})

    alice_records = store.list_records("alice")
    assert {r.id for r in alice_records} == {"a", "b"}

    work_records = store.list_records("alice", metadata_filter={"topic": "work"})
    assert {r.id for r in work_records} == {"a"}
