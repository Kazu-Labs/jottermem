import sys

import pytest

from jottermem.relay.config import RelayConfig

_REQUIRED_ENV = {
    "GOOGLE_CLIENT_ID": "test-client-id",
    "GOOGLE_CLIENT_SECRET": "test-client-secret",
    "RELAY_BASE_URL": "https://relay.example.com",
    "RELAY_SECRET_KEY": "test-secret-key",
}


def _set_env(monkeypatch, **overrides):
    values = {**_REQUIRED_ENV, **overrides}
    for key, value in values.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


def test_config_from_env_reads_all_values(monkeypatch, tmp_path):
    db_path = str(tmp_path / "relay.db")
    _set_env(monkeypatch)
    monkeypatch.setenv("RELAY_DB_PATH", db_path)

    config = RelayConfig.from_env()
    assert config.google_client_id == "test-client-id"
    assert config.base_url == "https://relay.example.com"
    assert config.db_path == db_path


def test_config_strips_trailing_slash_from_base_url(monkeypatch):
    _set_env(monkeypatch, RELAY_BASE_URL="https://relay.example.com/")
    assert RelayConfig.from_env().base_url == "https://relay.example.com"


def test_config_defaults_db_path(monkeypatch):
    _set_env(monkeypatch)
    monkeypatch.delenv("RELAY_DB_PATH", raising=False)
    assert RelayConfig.from_env().db_path == "jottermem-relay.db"


@pytest.mark.parametrize("missing", sorted(_REQUIRED_ENV))
def test_config_raises_on_missing_required_var(monkeypatch, missing):
    _set_env(monkeypatch, **{missing: None})
    with pytest.raises(RuntimeError, match=missing):
        RelayConfig.from_env()


cryptography = pytest.importorskip("cryptography", reason="requires the optional 'relay' extra")


def test_token_store_roundtrip(tmp_path):
    from jottermem.relay.tokens import TokenStore

    store = TokenStore(tmp_path / "tokens.db", secret_key="a-secret")
    access_token = store.create(refresh_token="google-refresh-token", folder_id="folder-123", email="a@b.com")

    refresh_token, folder_id = store.get(access_token)
    assert refresh_token == "google-refresh-token"
    assert folder_id == "folder-123"


def test_token_store_unknown_token_returns_none(tmp_path):
    from jottermem.relay.tokens import TokenStore

    store = TokenStore(tmp_path / "tokens.db", secret_key="a-secret")
    assert store.get("does-not-exist") is None


def test_token_store_encrypts_refresh_token_at_rest(tmp_path):
    from jottermem.relay.tokens import TokenStore

    db_path = tmp_path / "tokens.db"
    store = TokenStore(db_path, secret_key="a-secret")
    store.create(refresh_token="super-secret-refresh-token", folder_id="folder-123", email=None)

    raw = db_path.read_bytes()
    assert b"super-secret-refresh-token" not in raw


@pytest.mark.skipif(sys.version_info < (3, 10), reason="mcp requires Python >=3.10")
def test_app_boots_and_gates_mcp_endpoint(monkeypatch, tmp_path):
    pytest.importorskip("fastapi", reason="requires the optional 'relay' extra")
    pytest.importorskip("mcp", reason="requires the optional 'relay' extra")

    _set_env(monkeypatch)
    monkeypatch.setenv("RELAY_DB_PATH", str(tmp_path / "relay.db"))

    from fastapi.testclient import TestClient

    from jottermem.relay.app import app

    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

        login = client.get("/oauth/login", follow_redirects=False)
        assert login.status_code == 307
        assert "accounts.google.com" in login.headers["location"]

        unauthenticated = client.get("/mcp")
        assert unauthenticated.status_code == 401
