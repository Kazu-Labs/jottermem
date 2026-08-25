from __future__ import annotations

import json
import sqlite3
import time
from array import array
from pathlib import Path

from ..models import MemoryRecord, MemoryStatus

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    namespace TEXT NOT NULL DEFAULT 'default',
    key TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    embedding BLOB NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    superseded_by TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_namespace_status
    ON memories (namespace, status);
CREATE INDEX IF NOT EXISTS idx_memories_namespace_key_status
    ON memories (namespace, key, status);
"""


def pack_embedding(vector: list[float]) -> bytes:
    return array("f", vector).tobytes()


def unpack_embedding(blob: bytes) -> list[float]:
    vec = array("f")
    vec.frombytes(blob)
    return list(vec)


def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
    return MemoryRecord(
        id=row["id"],
        text=row["text"],
        namespace=row["namespace"],
        key=row["key"],
        metadata=json.loads(row["metadata"]),
        status=row["status"],
        superseded_by=row["superseded_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SQLiteStore:
    """Single-file SQLite storage for memories and their embeddings.

    Vector search is a brute-force cosine scan in Python over unpacked
    embeddings. That's the right tradeoff for the single-file/zero-infra
    scale this library targets (thousands, not millions, of memories per
    file); an optional sqlite-vec-backed index is a natural v1.1 accelerator
    behind this same interface once that's the bottleneck.
    """

    def __init__(self, path: str | Path = "jottermem.db"):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "SQLiteStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def insert(
        self,
        id: str,
        text: str,
        embedding: list[float],
        namespace: str = "default",
        key: str | None = None,
        metadata: dict | None = None,
    ) -> MemoryRecord:
        now = time.time()
        record = MemoryRecord(
            id=id,
            text=text,
            namespace=namespace,
            key=key,
            metadata=metadata or {},
            status=MemoryStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        self._conn.execute(
            """
            INSERT INTO memories
                (id, text, namespace, key, metadata, embedding, status,
                 superseded_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.text,
                record.namespace,
                record.key,
                json.dumps(record.metadata),
                pack_embedding(embedding),
                record.status,
                record.superseded_by,
                record.created_at,
                record.updated_at,
            ),
        )
        self._conn.commit()
        return record

    def get(self, id: str) -> MemoryRecord | None:
        row = self._conn.execute(
            "SELECT * FROM memories WHERE id = ?", (id,)
        ).fetchone()
        return _row_to_record(row) if row else None

    def touch(self, id: str) -> None:
        self._conn.execute(
            "UPDATE memories SET updated_at = ? WHERE id = ?", (time.time(), id)
        )
        self._conn.commit()

    def set_key(self, id: str, key: str) -> None:
        self._conn.execute(
            "UPDATE memories SET key = ?, updated_at = ? WHERE id = ?",
            (key, time.time(), id),
        )
        self._conn.commit()

    def supersede(self, id: str, superseded_by: str) -> None:
        self._conn.execute(
            """
            UPDATE memories
            SET status = ?, superseded_by = ?, updated_at = ?
            WHERE id = ?
            """,
            (MemoryStatus.SUPERSEDED, superseded_by, time.time(), id),
        )
        self._conn.commit()

    def delete(self, id: str) -> bool:
        cur = self._conn.execute("DELETE FROM memories WHERE id = ?", (id,))
        self._conn.commit()
        return cur.rowcount > 0

    def find_active_by_key(self, namespace: str, key: str) -> MemoryRecord | None:
        row = self._conn.execute(
            """
            SELECT * FROM memories
            WHERE namespace = ? AND key = ? AND status = ?
            """,
            (namespace, key, MemoryStatus.ACTIVE),
        ).fetchone()
        return _row_to_record(row) if row else None

    def iter_candidates(
        self,
        namespace: str,
        include_superseded: bool = False,
        metadata_filter: dict | None = None,
    ):
        """Yield (MemoryRecord, embedding) pairs matching the scope filters."""
        if include_superseded:
            rows = self._conn.execute(
                "SELECT * FROM memories WHERE namespace = ?", (namespace,)
            )
        else:
            rows = self._conn.execute(
                "SELECT * FROM memories WHERE namespace = ? AND status = ?",
                (namespace, MemoryStatus.ACTIVE),
            )
        for row in rows:
            record = _row_to_record(row)
            if metadata_filter and not _matches(record.metadata, metadata_filter):
                continue
            yield record, unpack_embedding(row["embedding"])

    def list(
        self,
        namespace: str,
        include_superseded: bool = False,
        metadata_filter: dict | None = None,
    ) -> list[MemoryRecord]:
        return [
            record
            for record, _ in self.iter_candidates(
                namespace, include_superseded, metadata_filter
            )
        ]


def _matches(metadata: dict, filter_: dict) -> bool:
    return all(metadata.get(k) == v for k, v in filter_.items())
