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


def test_token_store_list_accounts(tmp_path):
    from jottermem.relay.tokens import TokenStore

    store = TokenStore(tmp_path / "tokens.db", secret_key="a-secret")
    store.create(refresh_token="r1", folder_id="folder-1", email="a@example.com")
    store.create(refresh_token="r2", folder_id="folder-2", email=None)

    accounts = store.list_accounts()
    assert len(accounts) == 2
    assert accounts[0]["folder_id"] == "folder-1"
    assert accounts[0]["email"] == "a@example.com"
    assert accounts[1]["email"] is None


def test_token_store_revoke(tmp_path):
    from jottermem.relay.tokens import TokenStore

    store = TokenStore(tmp_path / "tokens.db", secret_key="a-secret")
    access_token = store.create(refresh_token="r1", folder_id="folder-1", email=None)

    assert store.revoke(access_token) is True
    assert store.get(access_token) is None
    assert store.revoke(access_token) is False


def test_admin_cli_list_and_revoke(tmp_path, monkeypatch, capsys):
    from jottermem.relay.admin import main
    from jottermem.relay.tokens import TokenStore

    db_path = tmp_path / "tokens.db"
    monkeypatch.setenv("RELAY_DB_PATH", str(db_path))
    monkeypatch.setenv("RELAY_SECRET_KEY", "a-secret")

    store = TokenStore(db_path, "a-secret")
    access_token = store.create(refresh_token="r1", folder_id="folder-1", email="a@example.com")

    monkeypatch.setattr("sys.argv", ["jottermem-relay-admin", "list"])
    main()
    out = capsys.readouterr().out
    assert access_token in out
    assert "a@example.com" in out

    monkeypatch.setattr("sys.argv", ["jottermem-relay-admin", "revoke", access_token])
    main()
    assert "Revoked." in capsys.readouterr().out
    assert store.get(access_token) is None


def test_admin_cli_requires_secret_key(tmp_path, monkeypatch):
    monkeypatch.delenv("RELAY_SECRET_KEY", raising=False)
    monkeypatch.setattr("sys.argv", ["jottermem-relay-admin", "list"])

    from jottermem.relay.admin import main

    with pytest.raises(SystemExit):
        main()


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
