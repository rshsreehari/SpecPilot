from __future__ import annotations

from src.retrieval.base import RetrievedChunk, Retriever
from src.retrieval.bm25 import BM25Index, BM25Retriever
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.naive import NaiveVectorRetriever
from src.retrieval.rerank import RerankedRetriever


class _FakeRetriever:
    """Satisfies the Retriever protocol without a real DB or model - used to assemble
    hybrid/reranked without needing Postgres or the cross-encoder in this test."""

    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self._chunks = chunks

    async def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        return self._chunks[:top_k]


def _chunk(chunk_id: int) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        endpoint_id=chunk_id,
        provider_id="stripe",
        text=f"chunk {chunk_id} some words about subscriptions",
        method="GET",
        path=f"/v1/thing/{chunk_id}",
        operation_id=None,
        score=1.0,
    )


def test_all_four_strategies_satisfy_the_retriever_protocol() -> None:
    # Construction only - no DB, no model, no network. Confirms every strategy from
    # Phase 3 implements the same interface Phase 1 defined, so callers never care which
    # one they got.
    bm25_index = BM25Index.build("stripe", [], k1=1.5, b=0.75)
    bm25 = BM25Retriever(bm25_index)
    naive = NaiveVectorRetriever(session=None)
    hybrid = HybridRetriever(naive, bm25)
    reranked = RerankedRetriever(hybrid)

    assert isinstance(naive, Retriever)
    assert isinstance(bm25, Retriever)
    assert isinstance(hybrid, Retriever)
    assert isinstance(reranked, Retriever)


async def test_bm25_retriever_satisfies_interface() -> None:
    index = BM25Index.build(
        "stripe", [(1, 1, "GET", "/v1/x", None, "some text about subscriptions")], k1=1.5, b=0.75
    )
    retriever = BM25Retriever(index)

    results = await retriever.search("subscriptions", top_k=5)

    assert all(isinstance(r, RetrievedChunk) for r in results)


async def test_hybrid_retriever_satisfies_interface() -> None:
    fake = _FakeRetriever([_chunk(1), _chunk(2)])
    retriever = HybridRetriever(fake, fake, k=60, candidate_pool=5)

    results = await retriever.search("subscriptions", top_k=5)

    assert all(isinstance(r, RetrievedChunk) for r in results)
    assert {r.chunk_id for r in results} == {1, 2}


async def test_reranked_retriever_satisfies_interface_with_empty_candidates() -> None:
    # Avoids loading the real cross-encoder model in a unit test: with zero candidates,
    # RerankedRetriever.search returns early before touching the model at all.
    empty = _FakeRetriever([])
    hybrid = HybridRetriever(empty, empty, k=60, candidate_pool=5)
    retriever = RerankedRetriever(hybrid, candidate_pool=5)

    results = await retriever.search("subscriptions", top_k=5)

    assert results == []
