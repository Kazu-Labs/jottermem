from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Extractor(Protocol):
    """Turns raw input text into a list of atomic fact strings."""

    def extract(self, text: str) -> list[str]: ...
