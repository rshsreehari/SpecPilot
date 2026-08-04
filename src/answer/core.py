from __future__ import annotations

from dataclasses import dataclass

from src.answer.mistral_client import ChatClient
from src.answer.prompt import SYSTEM_PROMPT, build_user_prompt
from src.answer.schemas import AnswerResult, Citation
from src.eval.truth import verify_endpoint
from src.retrieval.base import RetrievedChunk, Retriever


def _infer_citation_provider(
    citation: Citation, chunks: list[RetrievedChunk], request_provider_id: str | None
) -> str | None:
    """A citation grounded in one of the actually-retrieved chunks gets that chunk's
    provider - the strongest signal available, and the only one that matters when
    searching across every ingested provider at once (request_provider_id is None in
    that case). Falls back to the request's own provider scope (or None) when the
    citation doesn't match anything retrieved, e.g. a model citing from memory."""
    for chunk in chunks:
        if chunk.method == citation.method and chunk.path == citation.path:
            return chunk.provider_id
    return request_provider_id


def _verify_citations(
    citations: list[Citation], chunks: list[RetrievedChunk], provider_id: str | None
) -> list[Citation]:
    """Mechanical check against the OpenAPI spec (the same answer key eval grading
    uses) - not a quality judgement, just does this endpoint exist for the provider it
    claims. Never LLM-graded. A citation naming a provider that was never ingested (or
    with no resolvable provider at all) is unverified, not an error."""
    verified: list[Citation] = []
    for citation in citations:
        resolved_provider = citation.provider_id or _infer_citation_provider(
            citation, chunks, provider_id
        )
        is_verified = verify_endpoint(resolved_provider, citation.method, citation.path)
        verified.append(
            citation.model_copy(update={"provider_id": resolved_provider, "verified": is_verified})
        )
    return verified


@dataclass
class GeneratedAnswer:
    result: AnswerResult
    retrieved_chunks: list[RetrievedChunk]
    prompt_tokens: int
    completion_tokens: int


async def generate_answer(
    question: str,
    top_k: int,
    retriever: Retriever,
    chat_client: ChatClient,
    seed: int | None = None,
    provider_id: str | None = None,
) -> GeneratedAnswer:
    chunks = await retriever.search(question, top_k)

    if not chunks:
        result = AnswerResult(
            answer="The documentation does not cover this.",
            code_snippet=None,
            citations=[],
            retrieved_chunk_ids=[],
        )
        return GeneratedAnswer(result, [], 0, 0)

    response = await chat_client.chat_json(
        SYSTEM_PROMPT, build_user_prompt(question, chunks), seed=seed
    )
    citations = _verify_citations(
        [Citation(**c) for c in response.data.get("citations", [])], chunks, provider_id
    )
    result = AnswerResult(
        answer=response.data.get("answer", ""),
        code_snippet=response.data.get("code_snippet"),
        citations=citations,
        retrieved_chunk_ids=[chunk.chunk_id for chunk in chunks],
    )
    return GeneratedAnswer(result, chunks, response.prompt_tokens, response.completion_tokens)
