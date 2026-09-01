"""CLI to inspect and revoke jottermem-relay's connected accounts.

Run against the same `RELAY_DB_PATH` / `RELAY_SECRET_KEY` the relay
process itself uses (same shell profile / secret manager, not typed in):

  jottermem-relay-admin list
  jottermem-relay-admin revoke <access-token>

There's no web UI for this on purpose — it's meant for the one operator
who already holds `RELAY_SECRET_KEY`, which is enough to decrypt every
stored refresh token anyway (see tokens.py). A public multi-user launch
would want a real admin surface, not a CLI against the raw token store.
"""

from __future__ import annotations

import argparse
import os

from .tokens import TokenStore


def _token_store() -> TokenStore:
    db_path = os.environ.get("RELAY_DB_PATH", "jottermem-relay.db")
    secret_key = os.environ.get("RELAY_SECRET_KEY")
    if not secret_key:
        raise SystemExit("RELAY_SECRET_KEY must be set (the same value the relay process uses).")
    return TokenStore(db_path, secret_key)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage jottermem-relay connected accounts.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="List every connected account.")
    revoke_parser = subparsers.add_parser("revoke", help="Disconnect an account by its access token.")
    revoke_parser.add_argument("access_token")
    args = parser.parse_args()

    store = _token_store()

    if args.command == "list":
        accounts = store.list_accounts()
        if not accounts:
            print("No connected accounts.")
            return
        for account in accounts:
            email = account["email"] or "(email unknown)"
            print(f"{account['access_token']}  folder={account['folder_id']}  {email}")
    elif args.command == "revoke":
        if store.revoke(args.access_token):
            print("Revoked.")
        else:
            print("No account found with that access token.")


if __name__ == "__main__":
    main()
