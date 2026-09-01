# jottermem-relay

The piece that makes ChatGPT able to read/write the same memory folder as
Claude. It exists because of one hard constraint: ChatGPT's custom
connectors only accept a remote HTTPS MCP server — they cannot reach a
process running only on your laptop. Claude can already talk to your local
memory folder directly via `jottermem-portable-mcp` (see `jottermem-setup`);
you only need this if you want ChatGPT (or another remote-only MCP client)
in the loop too.

**This is a working scaffold, not a deployed service.** It won't run until
you provide the pieces below — none of which this repo can create for you,
since they're your accounts and your hosting choice.

## What it does

1. You sign in with Google once, at `<your-relay-url>/oauth/login`.
2. The relay finds-or-creates a folder named `jottermem` in your Drive, and
   requests only the `drive.file` OAuth scope — it can see files it created
   itself, never the rest of your Drive.
3. It hands you back a one-time access token and an MCP URL
   (`<your-relay-url>/mcp`).
4. You paste both into ChatGPT (Settings → Connectors → Advanced → Add
   custom connector) or any other remote-MCP-capable client.
5. From then on, the same four tools as the local server —
   `read_memory` / `write_memory` / `search_memory` / `list_memory` — read
   and write files in your Drive folder, byte-for-byte compatible with the
   local flat-file format (see `jottermem.portable.format`).

Your refresh token is encrypted at rest (`RELAY_SECRET_KEY`) in a local
SQLite file; the relay never stores memory content itself, only passing it
through to/from Drive on each call.

## What you need to provide

### 1. A Google Cloud OAuth app

1. Create a project at [console.cloud.google.com](https://console.cloud.google.com).
2. Enable the **Google Drive API** for it.
3. Configure the **OAuth consent screen** (External is fine; you don't need
   Google's app-verification review as long as you keep the user list small
   under the "testing" publishing status, or add the `drive.file` scope
   under "sensitive scopes" if you want to publish it more broadly — Google
   treats `drive.file` far more leniently than broader Drive scopes here).
4. Create an **OAuth client ID** of type "Web application".
5. Add `<your-relay-url>/oauth/callback` as an authorized redirect URI.
6. Note the generated client ID and client secret.

### 2. Somewhere to host it, behind HTTPS

Any host that can run a long-lived Python/ASGI process behind TLS works —
Fly.io, Render, Railway, a VPS with Caddy/nginx in front, etc. This repo
doesn't pick one for you. Whatever you choose, you need a stable public
HTTPS URL before step 1 above, since the OAuth redirect URI has to match it
exactly.

### 3. Environment variables

```
GOOGLE_CLIENT_ID=...           # from your Google Cloud OAuth app
GOOGLE_CLIENT_SECRET=...       # from your Google Cloud OAuth app
RELAY_BASE_URL=https://...     # the public HTTPS URL this runs behind
RELAY_SECRET_KEY=...           # random string; generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
RELAY_DB_PATH=jottermem-relay.db   # optional, defaults shown
```

Set these via your host's secret/env config, or (for local testing) your
shell profile — never paste real credentials into a chat or commit them to
the repo.

### 4. Install and run

Either directly:

```bash
pip install "jottermem[relay]"
uvicorn jottermem.relay.app:app --host 0.0.0.0 --port 8000
```

or with the included `Dockerfile`, built from the repo root so it can see
`pyproject.toml`:

```bash
docker build -f src/jottermem/relay/Dockerfile -t jottermem-relay .
docker run -p 8000:8000 --env-file .env.relay jottermem-relay
```

(`.env.relay` holding the four variables above, in `KEY=value` lines —
don't commit that file.)

Either way, point your reverse proxy / hosting platform's HTTPS front door
at port 8000, matching `RELAY_BASE_URL`. The Dockerfile is written to work
as-is on any host that runs an arbitrary container behind HTTPS (Fly.io,
Render, Railway, Cloud Run, a VPS — nothing here assumes a specific one).

## Before a real (multi-user, public) launch

This scaffold makes deliberate simplifications worth revisiting once more
than you are relying on it:

- **Auth model**: the relay verifies a bearer token it issued itself
  (`_RelayTokenVerifier` in `app.py`), not a full OAuth 2.1 authorization
  server with dynamic client registration. That's enough for clients that
  let you paste in a token by hand; a client that insists on driving the
  whole OAuth handshake itself needs a real
  `mcp.server.auth.provider.OAuthAuthorizationServerProvider` in front —
  effectively the relay acting as its own OAuth AS, internally delegating
  identity to Google.
- **Token storage**: one SQLite file, no rotation or expiry, no admin UI to
  revoke access. Fine for personal use; swap for a real database before
  onboarding others.
- **Single point of trust**: anyone who obtains a user's access token can
  read/write their memory folder. Treat `RELAY_SECRET_KEY` and the SQLite
  file (or its replacement) with the same care as any credential store.

See the PRD's own risk list (`jottermem-prd.md`, section 10) for the
broader trust/security questions worth a real review before public launch.
