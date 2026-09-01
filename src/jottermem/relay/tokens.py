from __future__ import annotations

import base64
import hashlib
import secrets
import sqlite3
from pathlib import Path


def _fernet(secret_key: str):
    from cryptography.fernet import Fernet

    key = base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode()).digest())
    return Fernet(key)


class TokenStore:
    """Persists each connected user's Google OAuth refresh token (encrypted
    at rest with `RELAY_SECRET_KEY`) and their memory folder's Drive file
    id, keyed by an opaque access token handed back to them once, at the
    end of the OAuth callback.

    This is a minimal scaffold suitable for one operator running their own
    relay for personal/small-scale use — a single SQLite file, no admin UI,
    no token expiry/rotation. Before a public multi-user launch, swap this
    for a real database and consider a full `OAuthAuthorizationServerProvider`
    (see README) instead of a self-issued opaque bearer token.
    """

    def __init__(self, path: str | Path, secret_key: str):
        self._fernet = _fernet(secret_key)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                access_token TEXT PRIMARY KEY,
                refresh_token_enc BLOB NOT NULL,
                folder_id TEXT NOT NULL,
                email TEXT
            )
            """
        )
        self._conn.commit()

    def create(self, refresh_token: str, folder_id: str, email: str | None) -> str:
        access_token = secrets.token_urlsafe(32)
        enc = self._fernet.encrypt(refresh_token.encode())
        self._conn.execute(
            "INSERT INTO accounts (access_token, refresh_token_enc, folder_id, email) "
            "VALUES (?, ?, ?, ?)",
            (access_token, enc, folder_id, email),
        )
        self._conn.commit()
        return access_token

    def get(self, access_token: str) -> tuple[str, str] | None:
        """Returns (refresh_token, folder_id) for a valid access token, else None."""
        row = self._conn.execute(
            "SELECT refresh_token_enc, folder_id FROM accounts WHERE access_token = ?",
            (access_token,),
        ).fetchone()
        if row is None:
            return None
        refresh_token = self._fernet.decrypt(row[0]).decode()
        return refresh_token, row[1]
