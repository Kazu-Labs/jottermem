from __future__ import annotations

import json
import sqlite3
import time
import warnings
from array import array
from pathlib import Path

from ..models import MemoryRecord, MemoryStatus
from ..similarity import l2_distance_to_cosine

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

_VEC_TABLE = "vec_index"


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


def _try_load_sqlite_vec(conn: sqlite3.Connection):
    """Return the sqlite_vec module if it could be loaded into `conn`, else None.

    Two independent things have to be true: this Python's sqlite3 build has
    to support loadable extensions at all (Apple's system Python does not;
    python.org and Homebrew builds do), and the `sqlite-vec` package has to
    be installed. Either being false means "not available," not an error —
    the caller decides whether that's fatal.
    """
    if not hasattr(conn, "enable_load_extension"):
        return None
    try:
        import sqlite_vec
    except ImportError:
        return None
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    except Exception:
        return None
    return sqlite_vec


class SQLiteStore:
    """Single-file SQLite storage for memories and their embeddings.

    By default, vector search is a brute-force cosine scan in Python over
    unpacked embeddings — plenty fast at the single-file, thousands-of-
    memories scale this library targets, and it never depends on a C
    extension being loadable.

    When `dim` is given and the `sqlite-vec` package is installed on a
    Python whose sqlite3 build supports loadable extensions, a `vec0`
    virtual table accelerates nearest-neighbor search instead. This is
    opt-in-by-availability (`use_sqlite_vec="auto"`, the default): it's used
    silently when possible and never breaks a plain `pip install jottermem`
    install when it isn't.
    """

    def __init__(
        self,
        path: str | Path = "jottermem.db",
        dim: int | None = None,
        use_sqlite_vec: bool | str = "auto",
    ):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

        self._vec_enabled = False
        self._sqlite_vec = None
        if use_sqlite_vec and dim is not None:
            sqlite_vec = _try_load_sqlite_vec(self._conn)
            if sqlite_vec is None:
                if use_sqlite_vec is True:
                    raise RuntimeError(
                        "use_sqlite_vec=True but the sqlite-vec extension "
                        "could not be loaded — either the 'sqlite-vec' "
                        "package isn't installed (pip install "
                        "jottermem[sqlite-vec]) or this Python's sqlite3 "
                        "build doesn't support loadable extensions (true of "
                        "Apple's system Python on macOS). Pass "
                        "use_sqlite_vec='auto' or False to fall back to the "
                        "brute-force scan instead."
                    )
            else:
                self._sqlite_vec = sqlite_vec
                self._init_vec_index(dim)

    def _init_vec_index(self, dim: int) -> None:
        try:
            self._conn.execute(
                f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS {_VEC_TABLE} USING vec0(
                    namespace TEXT PARTITION KEY,
                    status TEXT,
                    embedding FLOAT[{int(dim)}]
                )
                """
            )
            self._conn.commit()
            self._vec_enabled = True
        except sqlite3.OperationalError:
            self._vec_enabled = False

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
        cur = self._conn.execute(
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
        if self._vec_enabled:
            self._vec_insert(cur.lastrowid, record, embedding)
        return record

    def _vec_insert(self, rowid: int, record: MemoryRecord, embedding: list[float]) -> None:
        try:
            self._conn.execute(
                f"INSERT INTO {_VEC_TABLE}(rowid, namespace, status, embedding) "
                "VALUES (?, ?, ?, ?)",
                (
                    rowid,
                    record.namespace,
                    record.status,
                    self._sqlite_vec.serialize_float32(embedding),
                ),
            )
            self._conn.commit()
        except sqlite3.OperationalError:
            warnings.warn(
                "sqlite-vec insert failed (likely an embedding dimension "
                "mismatch with an existing index in this file); falling "
                "back to the brute-force scan for the rest of this session.",
                RuntimeWarning,
                stacklevel=3,
            )
            self._vec_enabled = False

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
        if self._vec_enabled:
            self._conn.execute(
                f"UPDATE {_VEC_TABLE} SET status = ? WHERE rowid = "
                "(SELECT rowid FROM memories WHERE id = ?)",
                (MemoryStatus.SUPERSEDED, id),
            )
            self._conn.commit()

    def delete(self, id: str) -> bool:
        rowid = None
        if self._vec_enabled:
            row = self._conn.execute(
                "SELECT rowid FROM memories WHERE id = ?", (id,)
            ).fetchone()
            rowid = row[0] if row else None

        cur = self._conn.execute("DELETE FROM memories WHERE id = ?", (id,))
        self._conn.commit()
        deleted = cur.rowcount > 0

        if deleted and self._vec_enabled and rowid is not None:
            self._conn.execute(f"DELETE FROM {_VEC_TABLE} WHERE rowid = ?", (rowid,))
            self._conn.commit()
        return deleted

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

    def vec_search(
        self,
        namespace: str,
        embedding: list[float],
        k: int,
        include_superseded: bool = False,
    ) -> list[tuple[MemoryRecord, float]] | None:
        """Top-k (MemoryRecord, cosine_similarity) via the sqlite-vec index,
        or None if acceleration isn't available (caller should fall back to
        `iter_candidates`). `embedding` must already be unit-normalized —
        the cosine similarity is derived from vec0's Euclidean distance
        under that assumption.
        """
        if not self._vec_enabled:
            return None
        if k <= 0:
            return []

        query = self._sqlite_vec.serialize_float32(embedding)
        if include_superseded:
            sql = (
                f"SELECT rowid, distance FROM {_VEC_TABLE} "
                "WHERE embedding MATCH ? AND k = ? AND namespace = ? "
                "ORDER BY distance"
            )
            params = (query, k, namespace)
        else:
            sql = (
                f"SELECT rowid, distance FROM {_VEC_TABLE} "
                "WHERE embedding MATCH ? AND k = ? AND namespace = ? "
                "AND status = ? ORDER BY distance"
            )
            params = (query, k, namespace, MemoryStatus.ACTIVE)

        try:
            rows = self._conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            self._vec_enabled = False
            return None

        results = []
        for rowid, distance in rows:
            record_row = self._conn.execute(
                "SELECT * FROM memories WHERE rowid = ?", (rowid,)
            ).fetchone()
            if record_row is None:
                continue
            results.append((_row_to_record(record_row), l2_distance_to_cosine(distance)))
        return results


def _matches(metadata: dict, filter_: dict) -> bool:
    return all(metadata.get(k) == v for k, v in filter_.items())
