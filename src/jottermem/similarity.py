from __future__ import annotations

import math


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def l2_distance_to_cosine(distance: float) -> float:
    """Convert a Euclidean distance between two unit vectors to their cosine
    similarity: for ||a||=||b||=1, ||a-b||^2 = 2 - 2*cos_sim(a, b)."""
    return 1.0 - (distance * distance) / 2.0
