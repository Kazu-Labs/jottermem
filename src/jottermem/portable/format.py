"""Shared flat-file memory format: one markdown file per topic, each fact a
timestamped bullet line, plus a JSON index. Used by both the local
`PortableStore` and the Drive-backed relay store (`jottermem.relay.drive_store`)
so the two backends read and write byte-for-byte compatible files.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

INDEX_FILENAME = "index.json"
INDEX_VERSION = 1

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_LINE_RE = re.compile(r"^- \[.*?\]\s*(.*)$")


def slugify(topic: str) -> str:
    slug = _SLUG_RE.sub("-", topic.strip().lower()).strip("-")
    return slug or "general"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fact_texts(content: str) -> list[str]:
    """Every fact already recorded in a topic file's markdown content."""
    facts = []
    for line in content.splitlines():
        m = _LINE_RE.match(line.strip())
        if m:
            facts.append(m.group(1))
    return facts


def append_fact(content: str, text: str, timestamp: str | None = None) -> str:
    if not content.endswith("\n"):
        content += "\n"
    return content + f"- [{timestamp or now()}] {text}\n"


def new_file(topic: str) -> str:
    return f"# {topic}\n\n"
