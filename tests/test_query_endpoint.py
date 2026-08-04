from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from src.answer.mistral_client import ChatResponse
from src.api.app import app
from src.api.deps import get_chat_client, get_retriever, get_session
from src.retrieval.base import RetrievedChunk


class FakeSession:
    def add(self, obj: Any) -> None:
        pass

    async def commit(self) -> None:
        pass


class FakeRetriever:
    async def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                chunk_id=1,
                endpoint_id=1,
                provider_id="stripe",
                text="POST /v1/subscriptions creates a subscription.",
                method="POST",
                path="/v1/subscriptions",
                operation_id="PostSubscriptions",
                score=0.9,
            )
        ]


class FakeChatClient:
    async def chat_json(self, system: str, user: str, seed: int | None = None) -> ChatResponse:
        return ChatResponse(
            data={
                "answer": "Create a subscription with POST /v1/subscriptions.",
                "code_snippet": "stripe.Subscription.create(...)",
                "citations": [
                    {
                        "method": "POST",
                        "path": "/v1/subscriptions",
                        "operation_id": "PostSubscriptions",
                    }
                ],
            },
            prompt_tokens=100,
            completion_tokens=50,
        )


@pytest.fixture(autouse=True)
def override_dependencies() -> Iterator[None]:
    async def fake_session() -> AsyncIterator[FakeSession]:
        yield FakeSession()

    app.dependency_overrides[get_session] = fake_session
    app.dependency_overrides[get_retriever] = lambda: FakeRetriever()
    app.dependency_overrides[get_chat_client] = lambda: FakeChatClient()
    yield
    app.dependency_overrides.clear()


async def test_query_returns_answer_with_citations() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/query", json={"question": "How do I create a subscription?"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"]
    assert body["citations"] == [
        {
            "method": "POST",
            "path": "/v1/subscriptions",
            "operation_id": "PostSubscriptions",
            "provider_id": "stripe",
            "verified": True,
        }
    ]
    assert body["retrieved_chunk_ids"] == [1]


async def test_health_returns_ok() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
