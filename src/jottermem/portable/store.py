from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .format import INDEX_FILENAME, INDEX_VERSION, append_fact, fact_texts, new_file, now, slugify


@dataclass
class TopicInfo:
    topic: str
    slug: str
    file: str
    updated: str
    count: int


@dataclass
class SearchHit:
    topic: str
    line: str


class PortableStore:
    """A memory folder: one plain-markdown file per topic, plus an index.

    Every file is human-readable and hand-editable — open `<root>/work.md`
    in any text editor and it's just a bulleted list of facts. This is the
    consumer-facing storage for the setup wizard (local folder or a
    Google-Drive-synced folder); it's a separate, simpler model from the
    SQLite-backed `jottermem.Memory` engine and doesn't do vector search,
    dedup-by-similarity, or key-based staleness — see the top-level README
    for which one fits a given use case.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)
        self._index_path = self.root / INDEX_FILENAME
        if not self._index_path.exists():
            self._write_index({"version": INDEX_VERSION, "topics": {}})

    def _read_index(self) -> dict:
        try:
            return json.loads(self._index_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {"version": INDEX_VERSION, "topics": {}}

    def _write_index(self, index: dict) -> None:
        self._index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")

    def _topic_path(self, topic: str) -> Path:
        return self.root / f"{slugify(topic)}.md"

    def write(self, topic: str, text: str) -> bool:
        """Append `text` as a new fact under `topic`.

        Returns False without writing anything if an identical fact is
        already recorded under this topic, True if a new line was added.
        """
        text = text.strip()
        if not text:
            raise ValueError("text must not be empty")

        slug = slugify(topic)
        path = self._topic_path(topic)
        existing = path.read_text() if path.exists() else new_file(topic)

        if text.lower() in (f.lower() for f in fact_texts(existing)):
            return False

        timestamp = now()
        path.write_text(append_fact(existing, text, timestamp))

        index = self._read_index()
        topics = index.setdefault("topics", {})
        count = topics.get(slug, {}).get("count", 0) + 1
        topics[slug] = {"file": path.name, "topic": topic, "updated": timestamp, "count": count}
        self._write_index(index)
        return True

    def read(self, topic: str) -> str | None:
        path = self._topic_path(topic)
        return path.read_text() if path.exists() else None

    def list_topics(self) -> list[TopicInfo]:
        index = self._read_index()
        return [
            TopicInfo(
                topic=info.get("topic", slug),
                slug=slug,
                file=info["file"],
                updated=info["updated"],
                count=info.get("count", 0),
            )
            for slug, info in sorted(index.get("topics", {}).items())
        ]

    def search(self, query: str, topic: str | None = None) -> list[SearchHit]:
        query_lower = query.strip().lower()
        if not query_lower:
            return []

        slugs = [slugify(topic)] if topic else [t.slug for t in self.list_topics()]
        hits: list[SearchHit] = []
        for slug in slugs:
            path = self.root / f"{slug}.md"
            if not path.exists():
                continue
            for line in path.read_text().splitlines():
                stripped = line.strip()
                if stripped.startswith("-") and query_lower in stripped.lower():
                    hits.append(SearchHit(topic=slug, line=stripped))
        return hits

    def overwrite(self, topic: str, content: str) -> None:
        """Replace a topic file's full markdown content verbatim — e.g.
        after hand-editing in `jottermem-app` — and refresh its index entry
        (fact count, updated time) to match what the new content holds."""
        slug = slugify(topic)
        path = self.root / f"{slug}.md"
        if not content.endswith("\n"):
            content += "\n"
        path.write_text(content)

        index = self._read_index()
        topics = index.setdefault("topics", {})
        existing_name = topics.get(slug, {}).get("topic", topic)
        topics[slug] = {
            "file": path.name,
            "topic": existing_name,
            "updated": now(),
            "count": len(fact_texts(content)),
        }
        self._write_index(index)

    def delete_topic(self, topic: str) -> bool:
        """Remove a topic entirely: its markdown file and its index entry.
        Returns False if the topic didn't exist."""
        slug = slugify(topic)
        path = self.root / f"{slug}.md"
        index = self._read_index()
        topics = index.get("topics", {})

        if not path.exists() and slug not in topics:
            return False

        path.unlink(missing_ok=True)
        topics.pop(slug, None)
        self._write_index(index)
        return True
