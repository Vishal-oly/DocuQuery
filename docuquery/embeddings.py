"""Small embedding adapters used for retrieval.

The default hashing backend is intentionally lightweight and works offline. For
stronger semantic retrieval, install requirements-embeddings.txt and select the
Sentence Transformers backend in .env.
"""

import hashlib
import math
import re
from typing import Iterable


class EmbeddingError(RuntimeError):
    pass


class HashingEmbedder:
    """Deterministic 384-dimensional feature hashing; no model download required."""

    dimension = 384
    _word_re = re.compile(r"[^\W_]+", flags=re.UNICODE)

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        return [self._embed_one(text or "") for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        tokens = self._word_re.findall(text.lower())[:3000]
        vector = [0.0] * self.dimension
        features: list[tuple[str, float]] = [(token, 1.0) for token in tokens]
        features.extend(
            (f"{left}_{right}", 0.42)
            for left, right in zip(tokens, tokens[1:])
        )
        for feature, weight in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest, "little") % self.dimension
            sign = 1.0 if digest[0] & 1 else -1.0
            vector[index] += weight * sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector


class SentenceTransformerEmbedder:
    """Optional local MiniLM embeddings; outputs 384-dimension vectors."""

    dimension = 384

    def __init__(self, model_name: str):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingError(
                "Sentence Transformers backend is selected but not installed. "
                "Install requirements-embeddings.txt or set EMBEDDING_BACKEND=hashing."
            ) from exc
        try:
            self.model = SentenceTransformer(model_name)
        except Exception as exc:
            raise EmbeddingError(
                f"Could not load embedding model '{model_name}': {exc}"
            ) from exc

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        values = list(texts)
        if not values:
            return []
        encoded = self.model.encode(values, normalize_embeddings=True)
        return [[float(item) for item in row] for row in encoded]


def make_embedder(backend: str, model_name: str):
    if backend == "hashing":
        return HashingEmbedder()
    if backend in {"sentence-transformers", "sentence_transformers", "minilm"}:
        return SentenceTransformerEmbedder(model_name)
    raise EmbeddingError(
        f"Unknown EMBEDDING_BACKEND '{backend}'. Use 'hashing' or 'sentence-transformers'."
    )
