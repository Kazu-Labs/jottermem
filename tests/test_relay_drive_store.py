"""Exercises DriveStore's read/write/index logic against an in-memory fake
of the Google Drive API, so it gets the same scrutiny as PortableStore
without needing real Google credentials or network access. The fake only
needs to understand the two query shapes DriveStore actually issues (find
a named file inside a folder; find-or-create the "jottermem" folder
itself) — see FakeDriveService._list.
"""

from __future__ import annotations

import re

import pytest

pytest.importorskip("googleapiclient", reason="requires the optional 'relay' extra")

from jottermem.relay.drive_store import MIME_FOLDER, DriveStore  # noqa: E402

_NAME_RE = re.compile(r"name = '([^']*)'")
_PARENT_RE = re.compile(r"'([^']*)' in parents")


class _Exec:
    def __init__(self, result: object):
        self._result = result

    def execute(self) -> object:
        return self._result


class _FakeFiles:
    def __init__(self, drive: "FakeDriveService"):
        self._drive = drive

    def list(self, q: str, spaces: str, fields: str) -> _Exec:
        return _Exec(self._drive._list(q))

    def get_media(self, fileId: str) -> _Exec:  # noqa: N803
        return _Exec(self._drive._files[fileId]["content"])

    def create(self, body: dict, fields: str | None = None, media_body: object = None) -> _Exec:
        return _Exec(self._drive._create(body, media_body))

    def update(self, fileId: str, media_body: object = None) -> _Exec:  # noqa: N803
        return _Exec(self._drive._update(fileId, media_body))


class _FakeAbout:
    def __init__(self, drive: "FakeDriveService"):
        self._drive = drive

    def get(self, fields: str) -> _Exec:
        return _Exec({"user": {"emailAddress": self._drive.email}})


class FakeDriveService:
    def __init__(self, email: str | None = "me@example.com") -> None:
        self._files: dict[str, dict] = {}
        self._next_id = 1
        self.email = email

    def files(self) -> _FakeFiles:
        return _FakeFiles(self)

    def about(self) -> _FakeAbout:
        return _FakeAbout(self)

    def _list(self, q: str) -> dict:
        name_match = _NAME_RE.search(q)
        name = name_match.group(1) if name_match else None
        wants_folder = "mimeType" in q
        parent_match = _PARENT_RE.search(q)
        parent = parent_match.group(1) if parent_match else None

        matches = []
        for file_id, meta in self._files.items():
            if name is not None and meta["name"] != name:
                continue
            if wants_folder and meta.get("mimeType") != MIME_FOLDER:
                continue
            if parent is not None and parent not in meta.get("parents", []):
                continue
            matches.append({"id": file_id})
        return {"files": matches}

    def _create(self, body: dict, media_body: object) -> dict:
        file_id = f"file-{self._next_id}"
        self._next_id += 1
        content = media_body.getbytes(0, media_body.size()) if media_body else b""
        self._files[file_id] = {
            "name": body["name"],
            "mimeType": body.get("mimeType"),
            "parents": body.get("parents", []),
            "content": content,
        }
        return {"id": file_id}

    def _update(self, file_id: str, media_body: object) -> dict:
        content = media_body.getbytes(0, media_body.size()) if media_body else b""
        self._files[file_id]["content"] = content
        return {"id": file_id}


@pytest.fixture
def fake_service(monkeypatch):
    service = FakeDriveService()
    monkeypatch.setattr("jottermem.relay.drive_store._build_service", lambda *a, **k: service)
    return service


@pytest.fixture
def drive_store(fake_service):
    folder_id = DriveStore.get_or_create_folder("refresh", "client-id", "client-secret")
    return DriveStore("refresh", folder_id, "client-id", "client-secret")


def test_get_account_email_returns_connected_address(fake_service):
    assert DriveStore.get_account_email("refresh", "id", "secret") == "me@example.com"


def test_get_account_email_returns_none_on_failure(monkeypatch):
    def _broken_service(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr("jottermem.relay.drive_store._build_service", _broken_service)
    assert DriveStore.get_account_email("refresh", "id", "secret") is None


def test_get_or_create_folder_is_idempotent(fake_service):
    first = DriveStore.get_or_create_folder("refresh", "id", "secret")
    second = DriveStore.get_or_create_folder("refresh", "id", "secret")
    assert first == second


def test_write_and_read_roundtrip(drive_store):
    assert drive_store.write("work", "Works at Acme Corp.") is True
    content = drive_store.read("work")
    assert content is not None
    assert "Works at Acme Corp." in content


def test_write_dedupes_identical_fact(drive_store):
    assert drive_store.write("work", "Likes tea.") is True
    assert drive_store.write("work", "Likes tea.") is False


def test_write_rejects_empty_text(drive_store):
    with pytest.raises(ValueError):
        drive_store.write("work", "   ")


def test_read_missing_topic_returns_none(drive_store):
    assert drive_store.read("nonexistent") is None


def test_list_topics_reflects_writes(drive_store):
    drive_store.write("work", "Fact one.")
    drive_store.write("preferences", "Fact two.")
    drive_store.write("work", "Fact three.")

    topics = {t["topic"]: t["count"] for t in drive_store.list_topics()}
    assert topics == {"work": 2, "preferences": 1}


def test_search_finds_matching_lines(drive_store):
    drive_store.write("work", "Works at Acme Corp.")
    drive_store.write("preferences", "Prefers async communication.")

    hits = drive_store.search("Acme")
    assert len(hits) == 1
    assert hits[0]["topic"] == "work"


def test_search_can_scope_to_one_topic(drive_store):
    drive_store.write("work", "Shared word: launch.")
    drive_store.write("preferences", "Shared word: launch.")

    hits = drive_store.search("launch", topic="work")
    assert len(hits) == 1
    assert hits[0]["topic"] == "work"


def test_writes_are_scoped_to_this_store_folder(fake_service):
    store_a = DriveStore("refresh", DriveStore.get_or_create_folder("r", "id", "s"), "id", "s")
    store_a.write("work", "Store A's fact.")

    other_folder_id = fake_service._create({"name": "other-folder", "mimeType": MIME_FOLDER}, None)["id"]
    store_b = DriveStore("refresh", other_folder_id, "id", "s")

    assert store_b.read("work") is None
    assert store_b.list_topics() == []
