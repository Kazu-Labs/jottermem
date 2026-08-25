from __future__ import annotations

from dataclasses import dataclass, field


class MemoryStatus:
    ACTIVE = "active"
    SUPERSEDED = "superseded"


@dataclass
class MemoryRecord:
    """A single stored fact."""

    id: str
    text: str
    namespace: str = "default"
    key: str | None = None
    metadata: dict = field(default_factory=dict)
    status: str = MemoryStatus.ACTIVE
    superseded_by: str | None = None
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class RecallResult:
    """A memory returned from `recall()`, with its similarity score."""

    memory: MemoryRecord
    score: float
