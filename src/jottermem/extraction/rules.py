from __future__ import annotations

import re

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_WHITESPACE_RE = re.compile(r"\s+")


class SentenceExtractor:
    """Default rule-based extractor: splits input into sentence-level facts.

    This is a zero-LLM-dependency default, not true atomic-fact extraction
    (it won't split "I live in Boston and work at Acme" into two facts).
    It solves the chunk-boundary problem at the sentence granularity, which
    is a real improvement over storing whole multi-sentence messages
    verbatim. Swap in an LLM-backed `Extractor` (any callable/object with an
    `extract(text) -> list[str]` method) for finer-grained atomic facts.
    """

    def __init__(self, min_length: int = 3):
        self.min_length = min_length

    def extract(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []
        sentences = _SENTENCE_SPLIT_RE.split(text)
        facts = []
        for sentence in sentences:
            normalized = _WHITESPACE_RE.sub(" ", sentence).strip()
            if len(normalized) >= self.min_length:
                facts.append(normalized)
        return facts
