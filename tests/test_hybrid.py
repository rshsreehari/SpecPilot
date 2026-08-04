from __future__ import annotations

from src.retrieval.base import RetrievedChunk
from src.retrieval.hybrid import HybridRetriever


def _chunk(chunk_id: int, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        endpoint_id=chunk_id,
        provider_id="stripe",
        text=f"chunk {chunk_id}",
        method="GET",
        path=f"/v1/thing/{chunk_id}",
        operation_id=None,
        score=score,
    )


class _FakeRetriever:
    def __init__(self, ordered_chunk_ids: list[int]) -> None:
        self._order = ordered_chunk_ids

    async def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        # Descending fake scores just to populate RetrievedChunk.score; RRF only cares
        # about rank position, not these values.
        return [
            _chunk(cid, score=1.0 - i * 0.1)
            for i, cid in enumerate(self._order[:top_k])
        ]


async def test_rrf_prefers_a_chunk_ranked_highly_by_both_retrievers() -> None:
    # chunk 1: rank 1 in vector, rank 2 in bm25 -> 1/61 + 1/62
    # chunk 2: rank 2 in vector, rank 1 in bm25 -> 1/62 + 1/61  (same total, tie)
    # chunk 3: rank 3 in vector only            -> 1/63
    vector = _FakeRetriever([1, 2, 3])
    bm25 = _FakeRetriever([2, 1])
    hybrid = HybridRetriever(vector, bm25, k=60, candidate_pool=10)

    results = await hybrid.search("query", top_k=3)

    # 1 and 2 tie (both appear at ranks {1,2} across the two lists); 3 is last since
    # it's only in one list at rank 3.
    assert {r.chunk_id for r in results[:2]} == {1, 2}
    assert results[2].chunk_id == 3


async def test_rrf_chunk_only_in_one_retriever_still_included() -> None:
    vector = _FakeRetriever([1])
    bm25 = _FakeRetriever([2])
    hybrid = HybridRetriever(vector, bm25, k=60, candidate_pool=10)

    results = await hybrid.search("query", top_k=10)

    assert {r.chunk_id for r in results} == {1, 2}


async def test_rrf_score_matches_formula() -> None:
    vector = _FakeRetriever([5])
    bm25 = _FakeRetriever([5])
    hybrid = HybridRetriever(vector, bm25, k=60, candidate_pool=10)

    results = await hybrid.search("query", top_k=1)

    # chunk 5 is rank 1 in both lists: 1/(60+1) + 1/(60+1) = 2/61
    assert results[0].score == 2 / 61


async def test_rrf_respects_top_k() -> None:
    vector = _FakeRetriever([1, 2, 3, 4, 5])
    bm25 = _FakeRetriever([1, 2, 3, 4, 5])
    hybrid = HybridRetriever(vector, bm25, k=60, candidate_pool=10)

    results = await hybrid.search("query", top_k=2)

    assert len(results) == 2
