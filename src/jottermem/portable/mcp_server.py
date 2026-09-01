"""MCP server exposing a jottermem memory folder (flat markdown files,
local or Google-Drive-synced) as tools: read_memory, write_memory,
search_memory, list_memory.

Optional — requires `pip install jottermem[mcp]` (needs Python >=3.10, the
`mcp` SDK's own requirement). Run with `jottermem-portable-mcp` after
installing, or `python -m jottermem.portable.mcp_server`.

Configure the backing folder with an environment variable:
  JOTTERMEM_PORTABLE_PATH   path to the memory folder (default: ~/jottermem)

`jottermem-setup` generates this config for you — see that command, or
`jottermem.portable.setup`, for the interactive wizard.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from .store import PortableStore

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

PATH_ENV = "JOTTERMEM_PORTABLE_PATH"
DEFAULT_PATH = "~/jottermem"

SERVER_INSTRUCTIONS = (
    "Persistent memory for this user, stored as plain markdown files in a "
    "folder they own (local disk, or their own Google Drive) rather than on "
    "any vendor's servers. Use write_memory(topic, text) to save a fact "
    'worth keeping across sessions, grouped under a short topic like "work" '
    'or "preferences". Use search_memory(query) or read_memory(topic) to '
    "check for relevant prior memories before answering questions that "
    "might depend on something remembered in a different session, or by a "
    "different AI assistant sharing this same folder. Use list_memory() to "
    "see what topics already exist before picking one for a new fact."
)


def _default_store() -> PortableStore:
    path = os.environ.get(PATH_ENV, DEFAULT_PATH)
    return PortableStore(path)


def create_server(store: PortableStore | None = None) -> "MCPServer":
    from mcp.server.mcpserver import MCPServer

    mem = store or _default_store()
    server = MCPServer(name="jottermem-portable", instructions=SERVER_INSTRUCTIONS)

    @server.tool()
    def write_memory(topic: str, text: str) -> dict[str, Any]:
        """Save `text` under `topic` (e.g. "work", "preferences", "health").

        Appends it as a new timestamped line in that topic's markdown file,
        creating the file if it doesn't exist yet. An identical fact already
        stored under this topic is skipped rather than duplicated. Returns
        whether a new line was actually written.
        """
        added = mem.write(topic, text)
        return {"topic": topic, "added": added}

    @server.tool()
    def read_memory(topic: str) -> str:
        """Return the full markdown contents stored under `topic`, or an
        empty string if that topic doesn't exist yet."""
        return mem.read(topic) or ""

    @server.tool()
    def search_memory(query: str, topic: str | None = None) -> list[dict[str, Any]]:
        """Keyword-search stored memories for lines containing `query`.

        Optionally restrict the search to a single `topic`. Returns matching
        lines along with the topic each one came from.
        """
        return [{"topic": hit.topic, "line": hit.line} for hit in mem.search(query, topic=topic)]

    @server.tool()
    def list_memory() -> list[dict[str, Any]]:
        """List every topic in this memory folder, with how many facts are
        stored under each and when it was last updated."""
        return [
            {"topic": t.topic, "file": t.file, "updated": t.updated, "count": t.count}
            for t in mem.list_topics()
        ]

    return server


def main() -> None:
    create_server().run()


if __name__ == "__main__":
    main()
