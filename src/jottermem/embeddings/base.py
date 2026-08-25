from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingFunction(Protocol):
    """Anything that turns text into fixed-dimension vectors.

    `dim` must be constant for a given instance — it's used to size the
    stored embedding blobs, so changing it after memories have been written
    to a store will make old vectors unreadable.
    """

    dim: int

    def __call__(self, texts: list[str]) -> list[list[float]]: ...
