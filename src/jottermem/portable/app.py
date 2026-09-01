"""A local, zero-dependency web viewer/editor for a jottermem memory folder.

The PRD's MVP scope calls for "a simple desktop/web app to view and
hand-edit memory files" — this is that, kept intentionally minimal: plain
stdlib `http.server`, no framework, since it only ever needs to run on your
own machine for as long as you're looking at it. Run with `jottermem-app`
(optionally `--path` / `--port`), or `python -m jottermem.portable.app`.
Binds to 127.0.0.1 only — it is not meant to be reachable from anywhere
else, unlike `jottermem-relay`.
"""

from __future__ import annotations

import argparse
import html
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .mcp_server import DEFAULT_PATH, PATH_ENV
from .store import PortableStore

DEFAULT_PORT = 8765

_STYLE = """
<style>
  body { font-family: -apple-system, system-ui, sans-serif; max-width: 720px;
         margin: 40px auto; padding: 0 16px; color: #1a1a1a; }
  header h1 { font-size: 1.25rem; }
  header h1 a { color: inherit; text-decoration: none; }
  table { width: 100%; border-collapse: collapse; margin: 16px 0; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #e5e5e5; }
  input, textarea, button { font: inherit; }
  input[type=text] { padding: 6px; border: 1px solid #ccc; border-radius: 4px; }
  textarea { padding: 8px; border: 1px solid #ccc; border-radius: 4px; }
  button { padding: 6px 14px; border: 1px solid #333; border-radius: 4px;
           background: #1a1a1a; color: white; cursor: pointer; }
  .path { color: #666; font-size: 0.85rem; word-break: break-all; }
  form.add-form { display: flex; gap: 8px; margin-top: 8px; }
  form.add-form input[name=text] { flex: 1; }
</style>
"""


def _layout(title: str, body: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title>{_STYLE}</head>"
        f"<body><header><h1><a href='/'>jottermem</a></h1></header>"
        f"<main>{body}</main></body></html>"
    )


def _not_found() -> str:
    return _layout("Not found", "<p>Not found. <a href='/'>Back</a></p>")


def make_handler(store: PortableStore, csrf_token: str) -> type[BaseHTTPRequestHandler]:
    """`csrf_token` is a per-run secret embedded in every form this page
    renders and required on every POST. Without it, any other website open
    in the same browser while this server is running could silently write
    into the memory folder by submitting a hidden form to it — this server
    has no other auth, since it's meant to be a zero-setup local tool."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass  # quiet by default -- this is a local viewer, not a service

        def _send_html(self, body: str, status: int = 200) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _redirect(self, location: str) -> None:
            self.send_response(303)
            self.send_header("Location", location)
            self.end_headers()

        def _read_form(self) -> dict[str, str]:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            parsed = parse_qs(raw)
            return {k: v[0] for k, v in parsed.items()}

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/":
                self._send_html(self._render_index())
            elif path.startswith("/topic/"):
                self._send_html(self._render_topic(path[len("/topic/") :]))
            else:
                self._send_html(_not_found(), status=404)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            fields = self._read_form()
            if not secrets.compare_digest(fields.get("csrf_token", ""), csrf_token):
                self._send_html(
                    _layout("Forbidden", "<p>Missing or invalid CSRF token. Reload the page and try again.</p>"),
                    status=403,
                )
                return

            if path == "/add":
                topic, text = fields.get("topic", "").strip(), fields.get("text", "").strip()
                if topic and text:
                    store.write(topic, text)
                self._redirect("/")
            elif path.startswith("/topic/") and path.endswith("/save"):
                slug = path[len("/topic/") : -len("/save")]
                store.overwrite(slug, fields.get("content", ""))
                self._redirect(f"/topic/{slug}")
            elif path.startswith("/topic/") and path.endswith("/delete"):
                slug = path[len("/topic/") : -len("/delete")]
                store.delete_topic(slug)
                self._redirect("/")
            else:
                self._send_html(_not_found(), status=404)

        def _render_index(self) -> str:
            topics = store.list_topics()
            if topics:
                rows = "".join(
                    f"<tr><td><a href='/topic/{html.escape(t.slug)}'>{html.escape(t.topic)}</a></td>"
                    f"<td>{t.count}</td><td>{html.escape(t.updated)}</td></tr>"
                    for t in topics
                )
                table = (
                    "<table><thead><tr><th>Topic</th><th>Facts</th>"
                    f"<th>Updated</th></tr></thead><tbody>{rows}</tbody></table>"
                )
            else:
                table = "<p>No memories yet — add one below.</p>"

            body = (
                f"<p class='path'>{html.escape(str(store.root))}</p>"
                f"{table}"
                "<h2>Add a fact</h2>"
                "<form class='add-form' method='post' action='/add'>"
                f"<input type='hidden' name='csrf_token' value='{csrf_token}'>"
                "<input type='text' name='topic' placeholder='topic (e.g. work)' required>"
                "<input type='text' name='text' placeholder='fact' required>"
                "<button type='submit'>Save</button>"
                "</form>"
            )
            return _layout("jottermem", body)

        def _render_topic(self, slug: str) -> str:
            content = store.read(slug) or ""
            body = (
                f"<h2>{html.escape(slug)}</h2>"
                f"<form method='post' action='/topic/{html.escape(slug)}/save'>"
                f"<input type='hidden' name='csrf_token' value='{csrf_token}'>"
                f"<textarea name='content' rows='20' style='width:100%; font-family: monospace;'>"
                f"{html.escape(content)}</textarea><br><br>"
                "<button type='submit'>Save</button>"
                "</form>"
                f"<form method='post' action='/topic/{html.escape(slug)}/delete' "
                f"onsubmit=\"return confirm('Delete the {html.escape(slug)} topic entirely?')\" "
                "style='margin-top: 24px;'>"
                f"<input type='hidden' name='csrf_token' value='{csrf_token}'>"
                "<button type='submit' style='background: #b3261e; border-color: #b3261e;'>"
                "Delete this topic</button>"
                "</form>"
                "<p><a href='/'>&larr; back</a></p>"
            )
            return _layout(slug, body)

    return Handler


class Server(ThreadingHTTPServer):
    """`ThreadingHTTPServer` with the per-run CSRF token attached, mainly
    so callers (tests included) can read it without scraping rendered
    HTML."""

    csrf_token: str


def serve(path: str, port: int = DEFAULT_PORT, *, open_browser: bool = True) -> Server:
    store = PortableStore(path)
    csrf_token = secrets.token_urlsafe(16)
    server = Server(("127.0.0.1", port), make_handler(store, csrf_token))
    server.csrf_token = csrf_token
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"jottermem-app: browsing {store.root}")
    print(f"  -> {url}  (Ctrl+C to stop)")

    if open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()

    return server


def main() -> None:
    import os

    parser = argparse.ArgumentParser(description="Browse and edit a jottermem memory folder.")
    parser.add_argument("--path", default=os.environ.get(PATH_ENV, DEFAULT_PATH))
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    server = serve(args.path, port=args.port, open_browser=not args.no_browser)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
