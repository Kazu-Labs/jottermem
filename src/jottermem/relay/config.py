from __future__ import annotations

import os
from dataclasses import dataclass

_REQUIRED = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "RELAY_BASE_URL", "RELAY_SECRET_KEY")


@dataclass(frozen=True)
class RelayConfig:
    google_client_id: str
    google_client_secret: str
    base_url: str
    secret_key: str
    db_path: str

    @classmethod
    def from_env(cls) -> "RelayConfig":
        missing = [name for name in _REQUIRED if not os.environ.get(name)]
        if missing:
            raise RuntimeError(
                "jottermem-relay is missing required env var(s): "
                + ", ".join(missing)
                + ". See src/jottermem/relay/README.md for how to obtain and set these."
            )
        return cls(
            google_client_id=os.environ["GOOGLE_CLIENT_ID"],
            google_client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
            base_url=os.environ["RELAY_BASE_URL"].rstrip("/"),
            secret_key=os.environ["RELAY_SECRET_KEY"],
            db_path=os.environ.get("RELAY_DB_PATH", "jottermem-relay.db"),
        )
