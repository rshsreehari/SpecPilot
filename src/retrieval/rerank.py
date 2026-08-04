from __future__ import annotations

from functools import lru_cache

from sentence_transformers import CrossEncoder

from src.retrieval.base import RetrievedChunk, Retriever


@lru_cache(maxsize=1)
def _get_cross_encoder(model_name: str) -> CrossEncoder:
    return CrossEncoder(model_name)


class RerankedRetriever:
    """Hybrid retrieval, then a local cross-encoder reranks the candidate pool down to
    top_k. The cross-encoder scores (query, passage) pairs jointly - unlike the bi-encoder
    used for vector search, which embeds query and passage independently, it can attend
    across both texts at once, so it's more accurate but too slow to run over the whole
    corpus. Hybrid retrieval narrows the field first; the cross-encoder only has to
    re-score a small candidate pool."""

    def __init__(
        self,
        hybrid: Retriever,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        candidate_pool: int = 20,
    ) -> None:
        self._hybrid = hybrid
        self._model_name = model_name
        self._candidate_pool = candidate_pool

    async def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        pool = max(top_k, self._candidate_pool)
        candidates = await self._hybrid.search(query, pool)
        if not candidates:
            return []

        model = _get_cross_encoder(self._model_name)
        pairs = [(query, chunk.text) for chunk in candidates]
        scores = model.predict(pairs)

        reranked = sorted(zip(candidates, scores, strict=True), key=lambda cs: cs[1], reverse=True)
        return [
            chunk.model_copy(update={"score": float(score)})
            for chunk, score in reranked[:top_k]
        ]
