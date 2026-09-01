import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

from jottermem.portable.app import serve


@pytest.fixture
def server(tmp_path):
    srv = serve(str(tmp_path / "mem"), port=0, open_browser=False)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        yield base_url
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def _get(url: str) -> tuple[int, str]:
    with urllib.request.urlopen(url) as resp:
        return resp.status, resp.read().decode()


def _post(url: str, fields: dict[str, str]) -> tuple[int, str]:
    data = urllib.parse.urlencode(fields).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST")) as resp:
        return resp.status, resp.read().decode()


def test_index_with_no_memories(server):
    status, body = _get(server + "/")
    assert status == 200
    assert "No memories yet" in body


def test_add_fact_creates_topic_and_redirects_to_index(server):
    status, body = _post(server + "/add", {"topic": "work", "text": "Works at Acme Corp."})
    assert status == 200
    assert "work" in body
    assert "1" in body  # fact count


def test_topic_page_shows_saved_content(server):
    _post(server + "/add", {"topic": "work", "text": "Works at Acme Corp."})
    status, body = _get(server + "/topic/work")
    assert status == 200
    assert "Works at Acme Corp." in body


def test_editing_topic_content_updates_file_and_reindexes(server, tmp_path):
    _post(server + "/add", {"topic": "work", "text": "Original fact."})
    new_content = "# work\n\n- [2026-01-01T00:00:00Z] Edited fact one.\n- [2026-01-01T00:00:00Z] Edited fact two.\n"

    status, body = _post(server + "/topic/work/save", {"content": new_content})
    assert status == 200
    assert "Edited fact one." in body

    index_status, index_body = _get(server + "/")
    assert "2" in index_body  # reindexed fact count


def test_unknown_path_returns_404(server):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _get(server + "/nonexistent")
    assert exc_info.value.code == 404


def test_html_in_memory_content_is_escaped(server):
    _post(server + "/add", {"topic": "work", "text": "<script>alert(1)</script>"})
    status, body = _get(server + "/topic/work")
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body
