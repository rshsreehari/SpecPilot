from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest

from src.retrieval import factory as factory_module
from src.retrieval.bm25 import BM25Retriever, MultiProviderBM25Retriever
from src.retrieval.factory import build_retriever, invalidate_bm25_cache, load_bm25_index
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.naive import NaiveVectorRetriever
from src.retrieval.rerank import RerankedRetriever


@dataclass
class _ChunkRow:
    id: int
    endpoint_id: int
    method: str
    path: str
    operation_id: str | None
    text: str


@dataclass
class _FakeScalars:
    items: list[Any]

    def all(self) -> list[Any]:
        return self.items


@dataclass
class _FakeResult:
    items: list[Any]

    def all(self) -> list[Any]:
        return self.items

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self.items)


class _FakeSession:
    def __init__(self, responses: list[list[Any]]) -> None:
        self._responses = responses
        self.call_count = 0

    async def execute(self, _stmt: Any) -> _FakeResult:
        items = self._responses[self.call_count]
        self.call_count += 1
        return _FakeResult(items)


@pytest.fixture(autouse=True)
def _clear_bm25_cache() -> Iterator[None]:
    invalidate_bm25_cache()
    yield
    invalidate_bm25_cache()


async def test_build_retriever_naive_needs_no_db_call() -> None:
    session = _FakeSession([])
    retriever = await build_retriever("naive", session, "stripe")

    assert isinstance(retriever, NaiveVectorRetriever)
    assert session.call_count == 0


async def test_build_retriever_unknown_strategy_raises() -> None:
    session = _FakeSession([])
    with pytest.raises(ValueError, match="unknown retrieval strategy"):
        await build_retriever("not-a-strategy", session, "stripe")


async def test_build_retriever_bm25_scoped_to_one_provider() -> None:
    session = _FakeSession([[_ChunkRow(1, 1, "GET", "/v1/x", "GetX", "some text")]])

    retriever = await build_retriever("bm25", session, "stripe")

    assert isinstance(retriever, BM25Retriever)
    assert session.call_count == 1


async def test_build_retriever_bm25_all_providers_queries_each_index_separately() -> None:
    session = _FakeSession(
        [
            ["stripe", "github"],  # _all_ingested_provider_ids
            [_ChunkRow(1, 1, "GET", "/v1/x", "GetX", "stripe text")],  # stripe's chunks
            [_ChunkRow(2, 2, "GET", "/repos/x", "GetRepo", "github text")],  # github's chunks
        ]
    )

    retriever = await build_retriever("bm25", session, None)

    assert isinstance(retriever, MultiProviderBM25Retriever)
    assert session.call_count == 3


async def test_build_retriever_hybrid_wraps_naive_and_bm25() -> None:
    session = _FakeSession([[_ChunkRow(1, 1, "GET", "/v1/x", "GetX", "some text")]])

    retriever = await build_retriever("hybrid", session, "stripe")

    assert isinstance(retriever, HybridRetriever)


async def test_build_retriever_reranked_wraps_hybrid() -> None:
    session = _FakeSession([[_ChunkRow(1, 1, "GET", "/v1/x", "GetX", "some text")]])

    retriever = await build_retriever("reranked", session, "stripe")

    assert isinstance(retriever, RerankedRetriever)


async def test_load_bm25_index_is_cached_across_calls() -> None:
    session = _FakeSession([[_ChunkRow(1, 1, "GET", "/v1/x", "GetX", "some text")]])

    first = await load_bm25_index(session, "stripe")
    second = await load_bm25_index(session, "stripe")

    assert first is second
    assert session.call_count == 1  # second call was served from cache, no new query


async def test_invalidate_bm25_cache_for_one_provider_forces_rebuild() -> None:
    session = _FakeSession(
        [
            [_ChunkRow(1, 1, "GET", "/v1/x", "GetX", "v1")],
            [_ChunkRow(1, 1, "GET", "/v1/x", "GetX", "v2")],
        ]
    )

    await load_bm25_index(session, "stripe")
    invalidate_bm25_cache("stripe")
    await load_bm25_index(session, "stripe")

    assert session.call_count == 2


async def test_invalidate_bm25_cache_with_no_argument_clears_everything() -> None:
    session = _FakeSession(
        [
            [_ChunkRow(1, 1, "GET", "/v1/x", "GetX", "v1")],
            [_ChunkRow(1, 1, "GET", "/v1/x", "GetX", "v2")],
        ]
    )

    await load_bm25_index(session, "stripe")
    invalidate_bm25_cache()
    await load_bm25_index(session, "stripe")

    assert session.call_count == 2
    assert "stripe" in factory_module._bm25_cache
