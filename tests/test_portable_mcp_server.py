import asyncio
import sys

import pytest

if sys.version_info < (3, 10):
    pytest.skip("mcp requires Python >=3.10", allow_module_level=True)

mcp = pytest.importorskip("mcp", reason="requires the optional 'mcp' extra")

from jottermem.portable import PortableStore  # noqa: E402
from jottermem.portable.mcp_server import create_server  # noqa: E402


def _call(server, name, arguments):
    return asyncio.run(server.call_tool(name, arguments)).structured_content


@pytest.fixture
def store(tmp_path):
    return PortableStore(tmp_path / "mem")


def test_lists_all_four_tools(store):
    server = create_server(store)
    tools = asyncio.run(server.list_tools())
    assert {t.name for t in tools} == {"read_memory", "write_memory", "search_memory", "list_memory"}


def test_write_and_read_roundtrip(store):
    server = create_server(store)
    result = _call(server, "write_memory", {"topic": "work", "text": "Works at Acme Corp."})
    assert result == {"topic": "work", "added": True}

    content = _call(server, "read_memory", {"topic": "work"})["result"]
    assert "Works at Acme Corp." in content


def test_write_dedupes_through_mcp(store):
    server = create_server(store)
    _call(server, "write_memory", {"topic": "work", "text": "Likes tea."})
    result = _call(server, "write_memory", {"topic": "work", "text": "Likes tea."})
    assert result == {"topic": "work", "added": False}


def test_search_memory_via_mcp(store):
    server = create_server(store)
    _call(server, "write_memory", {"topic": "work", "text": "Works at Acme Corp."})

    hits = _call(server, "search_memory", {"query": "Acme"})["result"]
    assert len(hits) == 1
    assert hits[0]["topic"] == "work"


def test_list_memory_via_mcp(store):
    server = create_server(store)
    _call(server, "write_memory", {"topic": "work", "text": "Fact one."})
    _call(server, "write_memory", {"topic": "preferences", "text": "Fact two."})

    topics = {t["topic"] for t in _call(server, "list_memory", {})["result"]}
    assert topics == {"work", "preferences"}


def test_uses_default_path_env_var(tmp_path, monkeypatch):
    folder = tmp_path / "env-mem"
    monkeypatch.setenv("JOTTERMEM_PORTABLE_PATH", str(folder))
    server = create_server()
    _call(server, "write_memory", {"topic": "work", "text": "Persisted via env var config."})
    assert folder.exists()
