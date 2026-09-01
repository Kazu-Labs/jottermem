import dataclasses
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

from jottermem.portable.app import serve


@dataclasses.dataclass
class _Server:
    url: str
    csrf: str


@pytest.fixture
def server(tmp_path):
    srv = serve(str(tmp_path / "mem"), port=0, open_browser=False)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        yield _Server(url=base_url, csrf=srv.csrf_token)
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
    status, body = _get(server.url + "/")
    assert status == 200
    assert "No memories yet" in body


def test_add_fact_creates_topic_and_redirects_to_index(server):
    status, body = _post(
        server.url + "/add", {"topic": "work", "text": "Works at Acme Corp.", "csrf_token": server.csrf}
    )
    assert status == 200
    assert "work" in body
    assert "1" in body  # fact count


def test_topic_page_shows_saved_content(server):
    _post(server.url + "/add", {"topic": "work", "text": "Works at Acme Corp.", "csrf_token": server.csrf})
    status, body = _get(server.url + "/topic/work")
    assert status == 200
    assert "Works at Acme Corp." in body


def test_editing_topic_content_updates_file_and_reindexes(server, tmp_path):
    _post(server.url + "/add", {"topic": "work", "text": "Original fact.", "csrf_token": server.csrf})
    new_content = "# work\n\n- [2026-01-01T00:00:00Z] Edited fact one.\n- [2026-01-01T00:00:00Z] Edited fact two.\n"

    status, body = _post(server.url + "/topic/work/save", {"content": new_content, "csrf_token": server.csrf})
    assert status == 200
    assert "Edited fact one." in body

    index_status, index_body = _get(server.url + "/")
    assert "2" in index_body  # reindexed fact count


def test_unknown_path_returns_404(server):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _get(server.url + "/nonexistent")
    assert exc_info.value.code == 404


def test_html_in_memory_content_is_escaped(server):
    _post(
        server.url + "/add",
        {"topic": "work", "text": "<script>alert(1)</script>", "csrf_token": server.csrf},
    )
    status, body = _get(server.url + "/topic/work")
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


def test_post_without_csrf_token_is_rejected(server, tmp_path):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _post(server.url + "/add", {"topic": "work", "text": "Injected via CSRF."})
    assert exc_info.value.code == 403

    # nothing should have been written
    status, body = _get(server.url + "/")
    assert "No memories yet" in body


def test_post_with_wrong_csrf_token_is_rejected(server):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _post(server.url + "/add", {"topic": "work", "text": "Injected.", "csrf_token": "wrong-token"})
    assert exc_info.value.code == 403


def test_index_page_embeds_csrf_token_in_add_form(server):
    _, body = _get(server.url + "/")
    assert f"value='{server.csrf}'" in body


def test_delete_topic_removes_it(server):
    _post(server.url + "/add", {"topic": "work", "text": "A fact.", "csrf_token": server.csrf})

    status, body = _post(server.url + "/topic/work/delete", {"csrf_token": server.csrf})
    assert status == 200
    assert "No memories yet" in body

    # topic page still renders (no crash) but is empty now
    status, body = _get(server.url + "/topic/work")
    assert status == 200
    assert "A fact." not in body


def test_delete_topic_without_csrf_token_is_rejected(server):
    _post(server.url + "/add", {"topic": "work", "text": "A fact.", "csrf_token": server.csrf})

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _post(server.url + "/topic/work/delete", {})
    assert exc_info.value.code == 403

    # topic should still exist
    status, body = _get(server.url + "/topic/work")
    assert "A fact." in body


def test_search_finds_matching_fact(server):
    _post(server.url + "/add", {"topic": "work", "text": "Works at Acme Corp.", "csrf_token": server.csrf})

    status, body = _get(server.url + "/search?" + urllib.parse.urlencode({"q": "Acme"}))
    assert status == 200
    assert "Acme Corp" in body
    assert "in work" in body


def test_search_with_no_matches(server):
    _post(server.url + "/add", {"topic": "work", "text": "Works at Acme Corp.", "csrf_token": server.csrf})

    status, body = _get(server.url + "/search?" + urllib.parse.urlencode({"q": "nonexistent"}))
    assert status == 200
    assert "No matches." in body


def test_search_with_empty_query(server):
    status, body = _get(server.url + "/search")
    assert status == 200
    assert "Enter a search term." in body


def test_rename_topic_moves_content_to_new_slug(server):
    _post(server.url + "/add", {"topic": "wrok", "text": "A fact.", "csrf_token": server.csrf})

    status, body = _post(
        server.url + "/topic/wrok/rename", {"new_name": "work", "csrf_token": server.csrf}
    )
    assert status == 200
    assert "A fact." in body  # landed on /topic/work, which shows it

    status, index_body = _get(server.url + "/")
    assert "wrok" not in index_body
    assert "work" in index_body


def test_rename_topic_without_csrf_token_is_rejected(server):
    _post(server.url + "/add", {"topic": "wrok", "text": "A fact.", "csrf_token": server.csrf})

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _post(server.url + "/topic/wrok/rename", {"new_name": "work"})
    assert exc_info.value.code == 403

    status, body = _get(server.url + "/topic/wrok")
    assert "A fact." in body


def test_rename_topic_onto_existing_topic_is_a_no_op(server):
    _post(server.url + "/add", {"topic": "work", "text": "Work fact.", "csrf_token": server.csrf})
    _post(server.url + "/add", {"topic": "preferences", "text": "Prefs fact.", "csrf_token": server.csrf})

    _post(server.url + "/topic/work/rename", {"new_name": "preferences", "csrf_token": server.csrf})

    status, body = _get(server.url + "/topic/work")
    assert "Work fact." in body
    status, body = _get(server.url + "/topic/preferences")
    assert "Prefs fact." in body
