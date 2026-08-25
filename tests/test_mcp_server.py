import asyncio
import sys

import pytest

if sys.version_info < (3, 10):
    pytest.skip("mcp requires Python >=3.10", allow_module_level=True)

mcp = pytest.importorskip("mcp", reason="requires the optional 'mcp' extra")

from jottermem import Memory  # noqa: E402
from jottermem.mcp_server import create_server  # noqa: E402


def _call(server, name, arguments):
    return asyncio.run(server.call_tool(name, arguments)).structured_content["result"]


def test_lists_all_four_tools():
    server = create_server(Memory(":memory:"))
    tools = asyncio.run(server.list_tools())
    assert {t.name for t in tools} == {"remember", "recall", "forget", "list_memories"}


def test_remember_and_recall_roundtrip():
    server = create_server(Memory(":memory:"))
    _call(server, "remember", {"text": "The user's favorite color is blue."})
    results = _call(server, "recall", {"query": "What color does the user like?", "k": 3})
    assert len(results) == 1
    assert "blue" in results[0]["text"].lower()
    assert "score" in results[0]


def test_key_based_staleness_through_mcp():
    server = create_server(Memory(":memory:"))
    _call(server, "remember", {"text": "Works at Acme Corp.", "key": "employer"})
    _call(server, "remember", {"text": "Works at Globex.", "key": "employer"})

    active = _call(server, "list_memories", {})
    assert len(active) == 1
    assert "Globex" in active[0]["text"]


def test_forget_via_mcp():
    server = create_server(Memory(":memory:"))
    [record] = _call(server, "remember", {"text": "A fact to forget."})

    assert _call(server, "forget", {"memory_id": record["id"]}) is True
    assert _call(server, "forget", {"memory_id": record["id"]}) is False
    assert _call(server, "recall", {"query": "A fact to forget.", "k": 5}) == []


def test_uses_default_memory_env_vars(tmp_path, monkeypatch):
    db_path = tmp_path / "agent.db"
    monkeypatch.setenv("JOTTERMEM_DB_PATH", str(db_path))
    server = create_server()
    _call(server, "remember", {"text": "Persisted via env var config."})
    assert db_path.exists()
