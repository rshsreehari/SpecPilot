from __future__ import annotations

import time
from dataclasses import dataclass

from src.answer.core import GeneratedAnswer, generate_answer
from src.answer.mistral_client import ChatClient
from src.answer.schemas import AnswerResult, Citation
from src.eval.truth import verify_endpoint
from src.retrieval.base import Retriever

# No context is provided; the model must answer from its own training-time knowledge of
# the provider's API. This is the baseline that proves retrieval is doing work (Phase 2
# goal). The provider name is filled in per-run - naming "Stripe" for a GitHub question
# would bias the baseline before it even starts.
NO_RETRIEVAL_SYSTEM_PROMPT_TEMPLATE = """You are an assistant answering questions about the {provider_name} \
API from your own knowledge. No documentation context is provided for this question.

Rules:
- Answer as best you can from what you know about the {provider_name} API.
- If you are not confident an endpoint exists, say so explicitly instead of guessing.
- Respond with a single JSON object with exactly these keys:
  "answer": string, a concise natural-language answer.
  "code_snippet": string or null, an example code snippet if relevant.
  "citations": array of objects with "method", "path", "operation_id" \
(operation_id may be null), one per endpoint you believe is relevant.
"""


@dataclass(frozen=True)
class TimedAnswer:
    generated: GeneratedAnswer
    latency_ms: float


async def answer_with_retrieval(
    question: str,
    top_k: int,
    retriever: Retriever,
    chat_client: ChatClient,
    seed: int | None = None,
    provider_id: str | None = None,
) -> TimedAnswer:
    start = time.perf_counter()
    generated = await generate_answer(
        question, top_k, retriever, chat_client, seed=seed, provider_id=provider_id
    )
    return TimedAnswer(generated, (time.perf_counter() - start) * 1000)


async def answer_without_retrieval(
    question: str,
    chat_client: ChatClient,
    seed: int | None = None,
    provider_name: str = "the",
    provider_id: str | None = None,
) -> TimedAnswer:
    start = time.perf_counter()
    system_prompt = NO_RETRIEVAL_SYSTEM_PROMPT_TEMPLATE.format(provider_name=provider_name)
    response = await chat_client.chat_json(system_prompt, question, seed=seed)
    latency_ms = (time.perf_counter() - start) * 1000

    # Verified the same mechanical way as the retrieval-backed path (see
    # answer/core.py::_verify_citations) - a citation the model produced from memory
    # alone is just as checkable against the spec as one grounded in a retrieved chunk.
    citations = []
    for raw_citation in response.data.get("citations", []):
        citation = Citation(**raw_citation)
        is_verified = verify_endpoint(provider_id, citation.method, citation.path)
        citations.append(citation.model_copy(update={"provider_id": provider_id, "verified": is_verified}))
    result = AnswerResult(
        answer=response.data.get("answer", ""),
        code_snippet=response.data.get("code_snippet"),
        citations=citations,
        retrieved_chunk_ids=[],
    )
    generated = GeneratedAnswer(result, [], response.prompt_tokens, response.completion_tokens)
    return TimedAnswer(generated, latency_ms)
