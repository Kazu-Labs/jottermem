"""jottermem-relay: exposes a Google-Drive-backed jottermem memory folder as
a remote, HTTPS MCP endpoint — the piece that makes ChatGPT (whose custom
connectors can only reach a remote server, never a local one) able to share
the same memory folder as Claude.

This does not run anywhere by default. To actually use it you need your own
Google Cloud OAuth app and somewhere to host this process behind HTTPS —
see README.md in this directory for the one-time setup. The process refuses
to start unless every required env var is set (see `RelayConfig`):

  GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET   from your Google Cloud OAuth app
  RELAY_BASE_URL                            the public HTTPS URL this runs behind
  RELAY_SECRET_KEY                          random string; encrypts stored refresh tokens
  RELAY_DB_PATH                             optional, default "jottermem-relay.db"

Run with: uvicorn jottermem.relay.app:app
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .config import RelayConfig
from .drive_store import DriveStore
from .oauth import build_flow
from .tokens import TokenStore

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

config = RelayConfig.from_env()
token_store = TokenStore(config.db_path, config.secret_key)


def _store_for_token(token: str) -> DriveStore:
    account = token_store.get(token)
    if account is None:
        raise HTTPException(401, "Unknown or revoked access token")
    refresh_token, folder_id = account
    return DriveStore(refresh_token, folder_id, config.google_client_id, config.google_client_secret)


def _build_mcp_server() -> "MCPServer":
    from mcp.server.auth.middleware.auth_context import get_access_token
    from mcp.server.auth.provider import AccessToken
    from mcp.server.auth.settings import AuthSettings
    from mcp.server.mcpserver import MCPServer
    from pydantic import AnyHttpUrl

    class _RelayTokenVerifier:
        """Verifies the opaque bearer token `jottermem-relay` itself issued
        at the end of the Google OAuth callback (see `oauth_callback`
        below) — not a full OAuth 2.1 authorization server with dynamic
        client registration. Good enough for a client that lets you paste
        in a bearer token by hand; if a target client insists on driving
        the whole OAuth handshake itself, this needs a real
        `OAuthAuthorizationServerProvider` in front of it instead."""

        async def verify_token(self, token: str) -> AccessToken | None:
            if token_store.get(token) is None:
                return None
            return AccessToken(token=token, client_id="jottermem-relay", scopes=["memory"], subject=token)

    server = MCPServer(
        name="jottermem-relay",
        instructions=(
            "Persistent memory for this user, stored as plain markdown files "
            "in their own Google Drive. Use write_memory(topic, text) to save "
            "a fact worth keeping across sessions. Use search_memory(query) "
            "or read_memory(topic) before answering questions that might "
            "depend on something remembered in a different session or a "
            "different AI assistant sharing this same folder."
        ),
        token_verifier=_RelayTokenVerifier(),
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(config.base_url),
            resource_server_url=AnyHttpUrl(f"{config.base_url}/mcp"),
            required_scopes=["memory"],
        ),
    )

    def _current_store() -> DriveStore:
        principal = get_access_token()
        if principal is None:
            raise HTTPException(401, "Missing or invalid access token")
        return _store_for_token(principal.token)

    @server.tool()
    def write_memory(topic: str, text: str) -> dict[str, Any]:
        """Save `text` under `topic`. Skips writing if an identical fact is
        already stored under that topic. Returns whether it was added."""
        added = _current_store().write(topic, text)
        return {"topic": topic, "added": added}

    @server.tool()
    def read_memory(topic: str) -> str:
        """Return the full markdown contents stored under `topic`."""
        return _current_store().read(topic) or ""

    @server.tool()
    def search_memory(query: str, topic: str | None = None) -> list[dict[str, Any]]:
        """Keyword-search stored memories, optionally restricted to `topic`."""
        return _current_store().search(query, topic=topic)

    @server.tool()
    def list_memory() -> list[dict[str, Any]]:
        """List every topic in this memory folder."""
        return _current_store().list_topics()

    return server


_mcp_server = _build_mcp_server()
_mcp_app = _mcp_server.streamable_http_app()

app = FastAPI(title="jottermem-relay", lifespan=_mcp_app.router.lifespan_context)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/oauth/login")
def oauth_login() -> RedirectResponse:
    flow = build_flow(config.google_client_id, config.google_client_secret, f"{config.base_url}/oauth/callback")
    auth_url, _state = flow.authorization_url(
        access_type="offline", prompt="consent", include_granted_scopes="true"
    )
    return RedirectResponse(auth_url)


@app.get("/oauth/callback", response_class=HTMLResponse)
def oauth_callback(request: Request) -> str:
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(400, "Missing authorization code")

    flow = build_flow(config.google_client_id, config.google_client_secret, f"{config.base_url}/oauth/callback")
    flow.fetch_token(code=code)
    credentials = flow.credentials
    if not credentials.refresh_token:
        raise HTTPException(
            400,
            "Google didn't return a refresh token — if you've connected this app "
            "before, revoke access at myaccount.google.com/permissions and try again.",
        )

    folder_id = DriveStore.get_or_create_folder(
        credentials.refresh_token, config.google_client_id, config.google_client_secret
    )
    email = DriveStore.get_account_email(
        credentials.refresh_token, config.google_client_id, config.google_client_secret
    )
    access_token = token_store.create(credentials.refresh_token, folder_id, email=email)

    return f"""
    <html><body style="font-family: sans-serif; max-width: 640px; margin: 40px auto;">
      <h1>jottermem connected</h1>
      <p>Your memory now lives in a "jottermem" folder in your Google Drive.</p>
      <p>To connect an AI assistant, give it this MCP server URL and access token:</p>
      <p><strong>URL:</strong> <code>{config.base_url}/mcp</code></p>
      <p><strong>Access token:</strong> <code>{access_token}</code></p>
      <p>Keep this token private — anyone with it can read and write your memory.
      It's shown only this once; re-run this login flow if you lose it.</p>
    </body></html>
    """


app.mount("/", _mcp_app)
