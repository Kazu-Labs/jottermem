"""Interactive setup wizard for a jottermem memory folder.

Run with `jottermem-setup` after installing (`pip install jottermem[mcp]`
gets you the MCP server this wizard wires up). Walks through choosing a
backend (a local folder, or a folder inside your own Google Drive),
creates the folder, and writes ready-to-use connection config for Claude
Desktop, Claude Code, and any other MCP-aware assistant — plus an explainer
for ChatGPT, which needs the separate `jottermem-relay` service (see
`jottermem/relay/README.md`) since it can't reach a local server directly.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from .store import PortableStore


def _prompt(question: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{question}{suffix}: ").strip()
    return answer or (default or "")


def _find_drive_folders() -> list[Path]:
    """Google Drive for Desktop's mount points on this machine, if any."""
    candidates = []
    cloud_storage = Path.home() / "Library" / "CloudStorage"
    if cloud_storage.is_dir():
        for entry in sorted(cloud_storage.iterdir()):
            if entry.name.startswith("GoogleDrive-"):
                my_drive = entry / "My Drive"
                candidates.append(my_drive if my_drive.is_dir() else entry)
    legacy = Path.home() / "Google Drive"
    if legacy.is_dir():
        candidates.append(legacy)
    return candidates


def _resolve_command(name: str) -> str:
    return shutil.which(name) or name


def _mcp_config_snippet(store_path: Path) -> dict:
    return {
        "mcpServers": {
            "jottermem": {
                "command": _resolve_command("jottermem-portable-mcp"),
                "env": {"JOTTERMEM_PORTABLE_PATH": str(store_path)},
            }
        }
    }


def _connect_markdown(store_path: Path, backend: str) -> str:
    command = _resolve_command("jottermem-portable-mcp")
    lines = [
        "# Connect your AI assistants to this memory folder",
        "",
        f"Memory folder: `{store_path}`",
        f"Backend: {'Google Drive (synced folder)' if backend == 'drive' else 'local folder'}",
        "",
        "Every file in this folder is plain markdown — open, read, or hand-edit",
        "any of them at any time. `index.json` just lists what topics exist so",
        "an assistant doesn't have to read every file to see what's there.",
        "",
        "## Claude Desktop",
        "",
        "1. Open Claude Desktop -> Settings -> Developer -> Edit Config.",
        "2. Merge the contents of `connect/claude_desktop_config.json` into",
        "   that file, under `mcpServers` (alongside any servers you already have).",
        "3. Restart Claude Desktop.",
        "",
        "## Claude Code",
        "",
        "Copy `connect/mcp.json` to `.mcp.json` in a project (or merge it into",
        "an existing one), or run:",
        "",
        "```",
        f"claude mcp add jottermem {command} -e JOTTERMEM_PORTABLE_PATH={store_path}",
        "```",
        "",
        "## ChatGPT",
        "",
    ]
    if backend == "drive":
        lines += [
            "ChatGPT's custom connectors only accept a remote HTTPS server, not a",
            "local command — so this local config won't work for ChatGPT directly,",
            "even though the folder itself is in Drive.",
            "",
            "Deploy `jottermem-relay` once (see `src/jottermem/relay/README.md` —",
            "it needs a Google Cloud OAuth app and somewhere to host the process),",
            "then in ChatGPT go to Settings -> Connectors -> Advanced -> Add custom",
            "connector, and paste in the relay's URL and access token.",
        ]
    else:
        lines += [
            "Not supported yet for a local folder — ChatGPT's custom connectors",
            "require a remote HTTPS server, and this folder only lives on this",
            "machine. If you want ChatGPT to share this memory, switch to the",
            "Google Drive backend (`jottermem-setup --backend drive`) and deploy",
            "`jottermem-relay` — see `src/jottermem/relay/README.md`.",
        ]
    lines += [
        "",
        "## Any other MCP-aware assistant",
        "",
        "Point it at the same command and env var as the Claude Code snippet",
        "above — any MCP client that supports local (stdio) servers can read",
        "and write this same folder.",
        "",
    ]
    return "\n".join(lines)


def _write_connect_files(store: PortableStore, backend: str) -> Path:
    connect_dir = store.root / "connect"
    connect_dir.mkdir(exist_ok=True)
    snippet = _mcp_config_snippet(store.root)

    (connect_dir / "mcp.json").write_text(json.dumps(snippet, indent=2) + "\n")
    (connect_dir / "claude_desktop_config.json").write_text(json.dumps(snippet, indent=2) + "\n")
    (connect_dir / "CONNECT.md").write_text(_connect_markdown(store.root, backend))
    return connect_dir


def _choose_backend() -> str:
    drive_folders = _find_drive_folders()
    print("Where should your memory folder live?")
    print("  1) A local folder on this computer")
    if drive_folders:
        print(f"  2) A folder inside your Google Drive (found {len(drive_folders)} on this Mac)")
    else:
        print("  2) A folder inside your Google Drive (you'll enter the path)")
    choice = _prompt("Choose 1 or 2", default="1")
    return "drive" if choice.strip() == "2" else "local"


def _choose_path(backend: str) -> Path:
    if backend == "drive":
        drive_folders = _find_drive_folders()
        if drive_folders:
            print("\nFound Google Drive folder(s):")
            for i, folder in enumerate(drive_folders, 1):
                print(f"  {i}) {folder}")
            print(f"  {len(drive_folders) + 1}) Enter a different path")
            idx = _prompt("Choose one", default="1")
            try:
                choice_num = int(idx)
                if choice_num == len(drive_folders) + 1:
                    raise ValueError
                selected = drive_folders[choice_num - 1]
            except (ValueError, IndexError):
                selected = Path(_prompt("Path to your Google Drive folder")).expanduser()
        else:
            selected = Path(
                _prompt(
                    "Path to your Google Drive folder (e.g. "
                    "~/Library/CloudStorage/GoogleDrive-you@gmail.com/My Drive)"
                )
            ).expanduser()
        default_path = selected / "jottermem"
    else:
        default_path = Path.home() / "jottermem"

    return Path(_prompt("Folder to store your memory in", default=str(default_path))).expanduser()


def run_wizard(*, backend: str | None = None, path: str | None = None) -> Path:
    print("jottermem setup")
    print("================\n")
    print("This sets up a memory folder that any MCP-aware AI assistant can")
    print("read from and write to. Files stay on your disk (or your own")
    print("Google Drive) the whole time — nothing is uploaded to us.\n")

    if backend is None:
        backend = _choose_backend()

    store_path = Path(path).expanduser() if path else _choose_path(backend)
    store = PortableStore(store_path)
    print(f"\nMemory folder ready at: {store.root}")

    connect_dir = _write_connect_files(store, backend)
    print(f"Connection instructions written to: {connect_dir / 'CONNECT.md'}\n")
    print(_connect_markdown(store.root, backend))
    print("Tip: run `jottermem-app` any time to browse or hand-edit these files in your browser.\n")

    return store.root


def main() -> None:
    parser = argparse.ArgumentParser(description="Set up a jottermem memory folder.")
    parser.add_argument("--backend", choices=["local", "drive"], default=None)
    parser.add_argument("--path", default=None)
    args = parser.parse_args()
    run_wizard(backend=args.backend, path=args.path)


if __name__ == "__main__":
    main()
