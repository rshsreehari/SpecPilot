from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from src.models import Chunk, Endpoint
from src.retrieval import naive as naive_module
from src.retrieval.naive import NaiveVectorRetriever


@dataclass
class _FakeResult:
    rows: list[tuple[Chunk, Endpoint, float]]

    def all(self) -> list[tuple[Chunk, Endpoint, float]]:
        return self.rows


class _FakeSession:
    def __init__(self, rows: list[tuple[Chunk, Endpoint, float]]) -> None:
        self._rows = rows
        self.executed_statements: list[Any] = []

    async def execute(self, stmt: Any) -> _FakeResult:
        self.executed_statements.append(stmt)
        return _FakeResult(self._rows)


def _row(chunk_id: int, provider_id: str, distance: float) -> tuple[Chunk, Endpoint, float]:
    chunk = Chunk(id=chunk_id, provider_id=provider_id, endpoint_id=1, text="some text")
    chunk.id = chunk_id
    endpoint = Endpoint(
        provider_id=provider_id, method="GET", path="/v1/x", operation_id="GetX", tags=[]
    )
    endpoint.id = 1
    return chunk, endpoint, distance


@pytest.fixture(autouse=True)
def _fake_embed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(naive_module, "embed_texts", lambda texts: [[0.1, 0.2, 0.3]])


async def test_search_returns_retrieved_chunks_with_provider_id() -> None:
    session = _FakeSession(rows=[_row(1, "stripe", 0.1)])
    retriever = NaiveVectorRetriever(session, provider_id=None)

    results = await retriever.search("a query", top_k=5)

    assert len(results) == 1
    assert results[0].provider_id == "stripe"
    assert results[0].score == pytest.approx(0.9)


async def test_search_with_provider_id_adds_a_where_clause() -> None:
    session = _FakeSession(rows=[_row(1, "stripe", 0.1)])
    retriever = NaiveVectorRetriever(session, provider_id="stripe")

    await retriever.search("a query", top_k=5)

    compiled = str(session.executed_statements[0])
    assert "WHERE chunks.provider_id" in compiled


async def test_search_without_provider_id_has_no_where_clause() -> None:
    session = _FakeSession(rows=[])
    retriever = NaiveVectorRetriever(session, provider_id=None)

    await retriever.search("a query", top_k=5)

    compiled = str(session.executed_statements[0])
    assert "WHERE" not in compiled
