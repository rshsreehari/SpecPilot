from __future__ import annotations

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from src.config import settings


@lru_cache(maxsize=1)
def get_embedder() -> SentenceTransformer:
    return SentenceTransformer(settings.embedding_model)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = get_embedder()
    vectors = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    return [vector.tolist() for vector in vectors]
