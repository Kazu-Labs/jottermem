import math

from jottermem.embeddings import HashingEmbedder


def test_dimension_and_determinism():
    embedder = HashingEmbedder(dim=64)
    a = embedder(["The quick brown fox"])[0]
    b = embedder(["The quick brown fox"])[0]
    assert len(a) == 64
    assert a == b


def test_normalized():
    embedder = HashingEmbedder(dim=64)
    vec = embedder(["hello world foo bar baz"])[0]
    norm = math.sqrt(sum(v * v for v in vec))
    assert math.isclose(norm, 1.0, abs_tol=1e-6)


def test_empty_text_is_zero_vector():
    embedder = HashingEmbedder(dim=32)
    vec = embedder([""])[0]
    assert vec == [0.0] * 32


def test_similar_text_more_similar_than_unrelated():
    from jottermem.similarity import cosine

    embedder = HashingEmbedder(dim=128)
    a, b, c = embedder(
        [
            "I love hiking in the mountains",
            "I love hiking in the hills",
            "The stock market crashed today",
        ]
    )
    assert cosine(a, b) > cosine(a, c)
