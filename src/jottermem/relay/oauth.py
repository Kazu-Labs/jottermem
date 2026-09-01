"""Google OAuth flow for jottermem-relay.

Requests the `drive.file` scope only — the relay (and anything it's
compromised by) can only see and edit files it created itself in the
user's Drive, never the rest of their Drive. This is the scope decision
that backs the "we never touch anything but this one folder" trust claim
in the PRD; don't broaden it to `drive` or `drive.readonly` without
revisiting that claim.
"""

from __future__ import annotations

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def build_flow(client_id: str, client_secret: str, redirect_uri: str):
    from google_auth_oauthlib.flow import Flow

    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    return Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
