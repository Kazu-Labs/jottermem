from __future__ import annotations

import uuid
from pathlib import Path

from .embeddings import EmbeddingFunction, HashingEmbedder
from .extraction import Extractor, SentenceExtractor
from .models import MemoryRecord, RecallResult
from .similarity import cosine
from .storage import SQLiteStore
from .text import tokenize

DEFAULT_DEDUP_THRESHOLD = 0.92
DEFAULT_KEYWORD_BOOST = 0.05


class Memory:
    """The main entry point: `remember()` facts, `recall()` them back.

    Zero-config usage stores everything in a single SQLite file next to
    your script, using a dependency-free embedder and a rule-based
    extractor. Every component is swappable via the constructor.
    """

    def __init__(
        self,
        path: str | Path = "jottermem.db",
        embedder: EmbeddingFunction | None = None,
        extractor: Extractor | None = None,
        namespace: str = "default",
        dedup_threshold: float = DEFAULT_DEDUP_THRESHOLD,
        keyword_boost: float = DEFAULT_KEYWORD_BOOST,
    ):
        self.store = SQLiteStore(path)
        self.embedder = embedder or HashingEmbedder()
        self.extractor = extractor or SentenceExtractor()
        self.namespace = namespace
        self.dedup_threshold = dedup_threshold
        self.keyword_boost = keyword_boost

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> "Memory":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def remember(
        self,
        text: str,
        metadata: dict | None = None,
        key: str | None = None,
        namespace: str | None = None,
    ) -> list[MemoryRecord]:
        """Extract atomic facts from `text` and store each one.

        Dedup: a fact whose cosine similarity to an existing active memory
        (in the same namespace) meets `dedup_threshold` is treated as a
        repeat — the existing record is touched and returned instead of
        inserting a near-duplicate.

        Staleness: if `key` is given, any existing active memory in this
        namespace with the same key is marked superseded before the new
        fact is inserted. Use a stable key (e.g. `"employer"`) for facts
        that change over time so recall() only surfaces the current value.
        """
        ns = namespace or self.namespace
        facts = self.extractor.extract(text)
        if not facts:
            return []

        results: list[MemoryRecord] = []
        for fact in facts:
            embedding = self.embedder([fact])[0]
            duplicate = self._find_duplicate(ns, embedding)
            if duplicate is not None:
                self.store.touch(duplicate.id)
                results.append(duplicate)
                continue

            new_id = uuid.uuid4().hex
            if key is not None:
                existing = self.store.find_active_by_key(ns, key)
                if existing is not None:
                    self.store.supersede(existing.id, new_id)

            record = self.store.insert(
                id=new_id,
                text=fact,
                embedding=embedding,
                namespace=ns,
                key=key,
                metadata=metadata,
            )
            results.append(record)

        return results

    def recall(
        self,
        query: str,
        k: int = 5,
        namespace: str | None = None,
        filter: dict | None = None,
        include_superseded: bool = False,
    ) -> list[RecallResult]:
        """Hybrid semantic + keyword-overlap search over stored memories."""
        ns = namespace or self.namespace
        query_vec = self.embedder([query])[0]
        query_tokens = set(tokenize(query))

        scored: list[RecallResult] = []
        for record, vec in self.store.iter_candidates(
            ns, include_superseded=include_superseded, metadata_filter=filter
        ):
            score = cosine(query_vec, vec)
            if self.keyword_boost and query_tokens:
                text_tokens = set(tokenize(record.text))
                overlap = len(query_tokens & text_tokens)
                score += self.keyword_boost * overlap
            scored.append(RecallResult(memory=record, score=score))

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:k]

    def forget(self, id: str) -> bool:
        """Permanently delete a memory by id. Returns False if not found."""
        return self.store.delete(id)

    def list_memories(
        self,
        namespace: str | None = None,
        filter: dict | None = None,
        include_superseded: bool = False,
    ) -> list[MemoryRecord]:
        ns = namespace or self.namespace
        return self.store.list(
            ns, include_superseded=include_superseded, metadata_filter=filter
        )

    def _find_duplicate(
        self, namespace: str, embedding: list[float]
    ) -> MemoryRecord | None:
        best_record: MemoryRecord | None = None
        best_score = 0.0
        for record, vec in self.store.iter_candidates(namespace):
            score = cosine(embedding, vec)
            if score > best_score:
                best_score = score
                best_record = record
        if best_record is not None and best_score >= self.dedup_threshold:
            return best_record
        return None
