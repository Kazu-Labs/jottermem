import json

import pytest

from jottermem.portable.setup import (
    _find_drive_folders,
    _looks_drive_synced,
    _mcp_config_snippet,
    main,
    run_wizard,
)


def test_run_wizard_local_backend_creates_folder_and_connect_files(tmp_path):
    target = tmp_path / "mem"
    root = run_wizard(backend="local", path=str(target))

    assert root == target
    assert (root / "index.json").exists()

    connect_dir = root / "connect"
    assert (connect_dir / "mcp.json").exists()
    assert (connect_dir / "claude_desktop_config.json").exists()
    assert (connect_dir / "CONNECT.md").exists()


def test_run_wizard_mcp_json_points_at_the_chosen_folder(tmp_path):
    target = tmp_path / "mem"
    root = run_wizard(backend="local", path=str(target))

    snippet = json.loads((root / "connect" / "mcp.json").read_text())
    env = snippet["mcpServers"]["jottermem"]["env"]
    assert env["JOTTERMEM_PORTABLE_PATH"] == str(root)


def test_run_wizard_local_backend_connect_md_says_chatgpt_unsupported(tmp_path):
    root = run_wizard(backend="local", path=str(tmp_path / "mem"))
    connect_md = (root / "connect" / "CONNECT.md").read_text()
    assert "Not supported yet for a local folder" in connect_md


def test_run_wizard_drive_backend_connect_md_points_at_relay(tmp_path):
    root = run_wizard(backend="drive", path=str(tmp_path / "mem"))
    connect_md = (root / "connect" / "CONNECT.md").read_text()
    assert "jottermem-relay" in connect_md
    assert "Not supported yet for a local folder" not in connect_md


def test_run_wizard_is_idempotent_on_existing_folder(tmp_path):
    target = tmp_path / "mem"
    run_wizard(backend="local", path=str(target))
    (target / "work.md").write_text("# work\n\n- [2026-01-01T00:00:00Z] Existing fact.\n")

    run_wizard(backend="local", path=str(target))

    assert "Existing fact." in (target / "work.md").read_text()


def test_mcp_config_snippet_shape(tmp_path):
    snippet = _mcp_config_snippet(tmp_path / "mem")
    server = snippet["mcpServers"]["jottermem"]
    assert server["command"]
    assert server["env"]["JOTTERMEM_PORTABLE_PATH"] == str(tmp_path / "mem")


def test_find_drive_folders_detects_cloud_storage_mounts(tmp_path, monkeypatch):
    monkeypatch.setattr("jottermem.portable.setup.Path.home", lambda: tmp_path)
    drive_mount = tmp_path / "Library" / "CloudStorage" / "GoogleDrive-me@example.com" / "My Drive"
    drive_mount.mkdir(parents=True)

    found = _find_drive_folders()
    assert found == [drive_mount]


def test_find_drive_folders_empty_when_none_present(tmp_path, monkeypatch):
    monkeypatch.setattr("jottermem.portable.setup.Path.home", lambda: tmp_path)
    assert _find_drive_folders() == []


def test_main_wires_cli_flags_to_run_wizard(tmp_path, monkeypatch):
    target = tmp_path / "mem"
    monkeypatch.setattr("sys.argv", ["jottermem-setup", "--backend", "local", "--path", str(target)])

    main()

    assert (target / "index.json").exists()


def test_choose_backend_prompts_when_not_given_via_flag(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _prompt="": "1")
    target = tmp_path / "mem"

    root = run_wizard(path=str(target))

    out = capsys.readouterr().out
    assert "Where should your memory folder live?" in out
    assert root == target


def test_looks_drive_synced_true_for_detected_folder(tmp_path, monkeypatch):
    monkeypatch.setattr("jottermem.portable.setup.Path.home", lambda: tmp_path)
    drive_mount = tmp_path / "Library" / "CloudStorage" / "GoogleDrive-me@example.com" / "My Drive"
    drive_mount.mkdir(parents=True)

    assert _looks_drive_synced(drive_mount / "jottermem") is True


def test_looks_drive_synced_true_for_cloud_storage_marker_in_path(tmp_path, monkeypatch):
    monkeypatch.setattr("jottermem.portable.setup.Path.home", lambda: tmp_path)
    path = tmp_path / "Library" / "CloudStorage" / "GoogleDrive-someone-else@example.com" / "jottermem"

    assert _looks_drive_synced(path) is True


def test_looks_drive_synced_false_for_unrelated_local_path(tmp_path, monkeypatch):
    monkeypatch.setattr("jottermem.portable.setup.Path.home", lambda: tmp_path)
    assert _looks_drive_synced(tmp_path / "not-drive" / "jottermem") is False


def test_run_wizard_warns_when_drive_path_does_not_look_synced(tmp_path, capsys):
    run_wizard(backend="drive", path=str(tmp_path / "not-drive" / "mem"))
    out = capsys.readouterr().out
    assert "doesn't look like it's inside a Google Drive-synced" in out


def test_run_wizard_does_not_warn_for_local_backend(tmp_path, capsys):
    run_wizard(backend="local", path=str(tmp_path / "mem"))
    out = capsys.readouterr().out
    assert "doesn't look like it's inside a Google Drive-synced" not in out


def test_run_wizard_warns_when_mcp_server_not_installed(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    run_wizard(backend="local", path=str(tmp_path / "mem"))
    out = capsys.readouterr().out
    assert "isn't on your PATH yet" in out


def test_run_wizard_no_install_warning_when_mcp_server_found(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/jottermem-portable-mcp")
    run_wizard(backend="local", path=str(tmp_path / "mem"))
    out = capsys.readouterr().out
    assert "isn't on your PATH yet" not in out
