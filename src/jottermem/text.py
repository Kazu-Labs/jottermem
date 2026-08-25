from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase, split into word tokens, and lightly stem plurals.

    Shared by HashingEmbedder and the keyword-overlap boost in recall() so
    "work" and "works" are treated as the same token everywhere jottermem
    does lexical matching, not just in one of the two places.
    """
    return [_stem(token) for token in _TOKEN_RE.findall(text.lower())]


def _stem(token: str) -> str:
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token
