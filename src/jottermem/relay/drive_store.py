"""Same flat-file memory model as `jottermem.portable.PortableStore`
(see `jottermem.portable.format` for the shared file format), backed by
Google Drive files instead of the local filesystem — this is what lets
jottermem-relay expose a user's Drive-backed memory folder over MCP without
storing memory content itself.
"""

from __future__ import annotations

import io
import json

from ..portable.format import INDEX_FILENAME, INDEX_VERSION, append_fact, fact_texts, new_file, now, slugify

MIME_FOLDER = "application/vnd.google-apps.folder"
MEMORY_FOLDER_NAME = "jottermem"


def _credentials(refresh_token: str, client_id: str, client_secret: str):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = Credentials(
        None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/drive.file"],
    )
    creds.refresh(Request())
    return creds


def _build_service(refresh_token: str, client_id: str, client_secret: str):
    from googleapiclient.discovery import build

    return build("drive", "v3", credentials=_credentials(refresh_token, client_id, client_secret))


class DriveStore:
    def __init__(self, refresh_token: str, folder_id: str, client_id: str, client_secret: str):
        self._service = _build_service(refresh_token, client_id, client_secret)
        self.folder_id = folder_id

    @classmethod
    def get_or_create_folder(cls, refresh_token: str, client_id: str, client_secret: str) -> str:
        """Find (or create) the single "jottermem" folder this refresh
        token can see — called once, right after OAuth completes, to
        establish the Drive folder id a `TokenStore` record points at."""
        service = _build_service(refresh_token, client_id, client_secret)
        query = f"name = '{MEMORY_FOLDER_NAME}' and mimeType = '{MIME_FOLDER}' and trashed = false"
        results = service.files().list(q=query, spaces="drive", fields="files(id)").execute()
        files = results.get("files", [])
        if files:
            return files[0]["id"]
        folder = (
            service.files()
            .create(body={"name": MEMORY_FOLDER_NAME, "mimeType": MIME_FOLDER}, fields="id")
            .execute()
        )
        return folder["id"]

    def _find_file(self, name: str) -> str | None:
        query = f"name = '{name}' and '{self.folder_id}' in parents and trashed = false"
        results = self._service.files().list(q=query, spaces="drive", fields="files(id)").execute()
        files = results.get("files", [])
        return files[0]["id"] if files else None

    def _read_text(self, file_id: str) -> str:
        content = self._service.files().get_media(fileId=file_id).execute()
        return content.decode() if isinstance(content, bytes) else content

    def _write_text(self, name: str, content: str, existing_id: str | None) -> None:
        from googleapiclient.http import MediaIoBaseUpload

        media = MediaIoBaseUpload(io.BytesIO(content.encode()), mimetype="text/markdown", resumable=False)
        if existing_id:
            self._service.files().update(fileId=existing_id, media_body=media).execute()
        else:
            self._service.files().create(
                body={"name": name, "parents": [self.folder_id]}, media_body=media
            ).execute()

    def _read_index(self) -> dict:
        file_id = self._find_file(INDEX_FILENAME)
        if not file_id:
            return {"version": INDEX_VERSION, "topics": {}}
        try:
            return json.loads(self._read_text(file_id))
        except json.JSONDecodeError:
            return {"version": INDEX_VERSION, "topics": {}}

    def _write_index(self, index: dict) -> None:
        file_id = self._find_file(INDEX_FILENAME)
        self._write_text(INDEX_FILENAME, json.dumps(index, indent=2, sort_keys=True) + "\n", file_id)

    def write(self, topic: str, text: str) -> bool:
        text = text.strip()
        if not text:
            raise ValueError("text must not be empty")

        slug = slugify(topic)
        filename = f"{slug}.md"
        file_id = self._find_file(filename)
        existing = self._read_text(file_id) if file_id else new_file(topic)

        if text.lower() in (f.lower() for f in fact_texts(existing)):
            return False

        timestamp = now()
        self._write_text(filename, append_fact(existing, text, timestamp), file_id)

        index = self._read_index()
        topics = index.setdefault("topics", {})
        count = topics.get(slug, {}).get("count", 0) + 1
        topics[slug] = {"file": filename, "topic": topic, "updated": timestamp, "count": count}
        self._write_index(index)
        return True

    def read(self, topic: str) -> str | None:
        file_id = self._find_file(f"{slugify(topic)}.md")
        return self._read_text(file_id) if file_id else None

    def list_topics(self) -> list[dict]:
        index = self._read_index()
        return [
            {
                "topic": info.get("topic", slug),
                "file": info["file"],
                "updated": info["updated"],
                "count": info.get("count", 0),
            }
            for slug, info in sorted(index.get("topics", {}).items())
        ]

    def search(self, query: str, topic: str | None = None) -> list[dict]:
        query_lower = query.strip().lower()
        if not query_lower:
            return []

        slugs = [slugify(topic)] if topic else [t["file"][:-3] for t in self.list_topics()]
        hits = []
        for slug in slugs:
            file_id = self._find_file(f"{slug}.md")
            if not file_id:
                continue
            for line in self._read_text(file_id).splitlines():
                stripped = line.strip()
                if stripped.startswith("-") and query_lower in stripped.lower():
                    hits.append({"topic": slug, "line": stripped})
        return hits
