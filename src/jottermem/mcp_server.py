"""MCP server exposing jottermem as tools for MCP-aware agents (Claude Code
and others): remember, recall, forget, list_memories.

Optional — requires `pip install jottermem[mcp]` (needs Python 3.10+, the
`mcp` SDK's own requirement). Run with `jottermem-mcp` after installing, or
`python -m jottermem.mcp_server`.

Configure the backing store with environment variables:
  JOTTERMEM_DB_PATH   path to the SQLite file (default: jottermem.db)
  JOTTERMEM_NAMESPACE default namespace for tool calls (default: "default")
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from .memory import Memory
from .models import MemoryRecord

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

DB_PATH_ENV = "JOTTERMEM_DB_PATH"
NAMESPACE_ENV = "JOTTERMEM_NAMESPACE"

SERVER_INSTRUCTIONS = (
    "Persistent memory for this agent, backed by a local SQLite file. Use "
    "remember() to save facts worth keeping across sessions — user "
    "preferences, decisions, project context. Give a fact that can change "
    'over time a stable `key` (e.g. "employer", "current_task") so a later '
    "remember() call with the same key supersedes the old value instead of "
    "leaving both retrievable with equal confidence. Use recall() to check "
    "for relevant prior memories before answering questions that might "
    "depend on something remembered earlier in a different session."
)


def _default_memory() -> Memory:
    path = os.environ.get(DB_PATH_ENV, "jottermem.db")
    namespace = os.environ.get(NAMESPACE_ENV, "default")
    return Memory(path, namespace=namespace)


def _serialize(record: MemoryRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "text": record.text,
        "namespace": record.namespace,
        "key": record.key,
        "metadata": record.metadata,
        "status": record.status,
    }


def create_server(memory: Memory | None = None) -> MCPServer:
    from mcp.server.mcpserver import MCPServer

    mem = memory or _default_memory()
    server = MCPServer(name="jottermem", instructions=SERVER_INSTRUCTIONS)

    @server.tool()
    def remember(
        text: str, key: str | None = None, namespace: str | None = None
    ) -> list[dict[str, Any]]:
        """Extract atomic facts from `text` and store each one.

        Give `key` a stable identifier for a fact that can change over time
        (e.g. "employer", "current_task") — a later remember() call with the
        same key marks the previous value superseded, so recall() only
        surfaces the current one. A fact that's a near-duplicate of an
        existing memory is deduplicated automatically rather than stored
        again. Returns the stored (or touched, if deduplicated) memories.
        """
        return [_serialize(r) for r in mem.remember(text, key=key, namespace=namespace)]

    @server.tool()
    def recall(query: str, k: int = 5, namespace: str | None = None) -> list[dict[str, Any]]:
        """Search stored memories for ones relevant to `query`.

        Returns up to `k` memories, most relevant first, each with a
        similarity `score`. Superseded (stale) memories are excluded.
        """
        results = mem.recall(query, k=k, namespace=namespace)
        return [{**_serialize(r.memory), "score": r.score} for r in results]

    @server.tool()
    def forget(memory_id: str) -> bool:
        """Permanently delete a memory by its id. Returns false if it wasn't found."""
        return mem.forget(memory_id)

    @server.tool()
    def list_memories(
        namespace: str | None = None, include_superseded: bool = False
    ) -> list[dict[str, Any]]:
        """List stored memories in scope.

        Set `include_superseded=true` to also see facts that have been
        replaced by a newer value under the same key.
        """
        return [
            _serialize(r)
            for r in mem.list_memories(namespace=namespace, include_superseded=include_superseded)
        ]

    return server


def main() -> None:
    create_server().run()


if __name__ == "__main__":
    main()
