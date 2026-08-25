from __future__ import annotations

import hashlib
import math
import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class HashingEmbedder:
    """Deterministic, dependency-free bag-of-words embedder.

    Uses the hashing trick (each token hashes to a dimension index and a
    +1/-1 sign) so it needs no vocabulary, no training, and no third-party
    package — jottermem works out of the box with `pip install jottermem`
    and nothing else.

    This is a lexical embedding, not a semantic one: it captures shared
    words, not shared meaning, so it won't match paraphrases the way a
    sentence-transformer would. It's the right default for a zero-dependency
    quickstart; swap in `jottermem.embeddings.SentenceTransformerEmbedder`
    (`pip install jottermem[sentence-transformers]`) or your own
    `EmbeddingFunction` for real semantic recall.
    """

    def __init__(self, dim: int = 256):
        self.dim = dim

    def __call__(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in _TOKEN_RE.findall(text.lower()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[index] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec
