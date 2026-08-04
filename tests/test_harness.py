from __future__ import annotations

from typing import Any

from src.answer.mistral_client import ChatResponse
from src.eval.harness import answer_with_retrieval, answer_without_retrieval
from src.retrieval.base import RetrievedChunk


class _FakeRetriever:
    async def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                chunk_id=1,
                endpoint_id=1,
                provider_id="stripe",
                text="POST /v1/customers creates a customer.",
                method="POST",
                path="/v1/customers",
                operation_id="PostCustomers",
                score=0.9,
            )
        ]


class _FakeChatClient:
    async def chat_json(self, system: str, user: str, seed: int | None = None) -> ChatResponse:
        return ChatResponse(
            data={
                "answer": "Create a customer with POST /v1/customers.",
                "code_snippet": None,
                "citations": [
                    {"method": "POST", "path": "/v1/customers", "operation_id": "PostCustomers"}
                ],
            },
            prompt_tokens=50,
            completion_tokens=20,
        )

    async def chat_raw(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError


async def test_answer_with_retrieval_returns_timed_result() -> None:
    timed = await answer_with_retrieval(
        "How do I create a customer?", 5, _FakeRetriever(), _FakeChatClient()
    )

    assert timed.generated.result.answer == "Create a customer with POST /v1/customers."
    assert timed.generated.result.retrieved_chunk_ids == [1]
    assert timed.latency_ms >= 0


async def test_answer_without_retrieval_has_no_retrieved_chunks() -> None:
    timed = await answer_without_retrieval("How do I create a customer?", _FakeChatClient())

    assert timed.generated.result.retrieved_chunk_ids == []
    assert len(timed.generated.result.citations) == 1
    assert timed.generated.prompt_tokens == 50
    assert timed.generated.completion_tokens == 20
    assert timed.latency_ms >= 0


async def test_answer_without_retrieval_verifies_citations_when_provider_id_given() -> None:
    # POST /v1/customers is a real, ingested Stripe endpoint - the no-retrieval baseline
    # must be checked against the spec exactly like the retrieval-backed path is, not
    # left permanently unverified just because it never touched a retriever.
    timed = await answer_without_retrieval(
        "How do I create a customer?", _FakeChatClient(), provider_id="stripe"
    )

    assert timed.generated.result.citations[0].verified is True
    assert timed.generated.result.citations[0].provider_id == "stripe"


async def test_answer_without_retrieval_unverified_when_no_provider_id() -> None:
    timed = await answer_without_retrieval("How do I create a customer?", _FakeChatClient())

    assert timed.generated.result.citations[0].verified is False
