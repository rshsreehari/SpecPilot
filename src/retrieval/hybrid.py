from __future__ import annotations

from src.retrieval.base import RetrievedChunk, Retriever
from src.retrieval.rrf import reciprocal_rank_fusion


class HybridRetriever:
    """Reciprocal rank fusion of a vector retriever and BM25 - see rrf.py for why RRF
    (rank fusion) is used instead of normalizing and summing raw scores. Provider scoping
    is inherited from whichever `vector`/`bm25` retrievers this is constructed with; this
    class never touches provider_id itself."""

    def __init__(
        self,
        vector: Retriever,
        bm25: Retriever,
        k: int = 60,
        candidate_pool: int = 20,
    ) -> None:
        self._vector = vector
        self._bm25 = bm25
        self._k = k
        self._candidate_pool = candidate_pool

    async def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        pool = max(top_k, self._candidate_pool)
        vector_results = await self._vector.search(query, pool)
        bm25_results = await self._bm25.search(query, pool)
        return reciprocal_rank_fusion([vector_results, bm25_results], self._k, top_k)
