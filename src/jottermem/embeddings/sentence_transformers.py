from __future__ import annotations


class SentenceTransformerEmbedder:
    """Semantic embedder backed by `sentence-transformers`.

    Optional — requires `pip install jottermem[sentence-transformers]`.
    Swap this in when the default `HashingEmbedder`'s lexical matching
    isn't good enough (e.g. you need paraphrases to match).
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "SentenceTransformerEmbedder requires the 'sentence-transformers' "
                "extra: pip install jottermem[sentence-transformers]"
            ) from exc

        self._model = SentenceTransformer(model_name)
        self.dim = self._model.get_sentence_embedding_dimension()

    def __call__(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, normalize_embeddings=True).tolist()
