from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.answer.core import generate_answer
from src.answer.mistral_client import ChatClient
from src.answer.schemas import AnswerResult
from src.logging import get_logger
from src.models import Query
from src.retrieval.base import Retriever

logger = get_logger(__name__)


@dataclass
class AnsweredQuestion:
    result: AnswerResult
    prompt_tokens: int
    completion_tokens: int


async def answer_question(
    question: str,
    top_k: int,
    retriever: Retriever,
    chat_client: ChatClient,
    session: AsyncSession,
    provider_id: str | None = None,
) -> AnsweredQuestion:
    generated = await generate_answer(
        question, top_k, retriever, chat_client, provider_id=provider_id
    )
    result = generated.result

    session.add(
        Query(
            question=question,
            answer=result.answer,
            code_snippet=result.code_snippet,
            citations=[c.model_dump() for c in result.citations],
            retrieved_chunk_ids=result.retrieved_chunk_ids,
        )
    )
    await session.commit()

    logger.info(
        "answer_generated",
        question=question,
        citation_count=len(result.citations),
        retrieved_count=len(result.retrieved_chunk_ids),
    )
    return AnsweredQuestion(
        result=result,
        prompt_tokens=generated.prompt_tokens,
        completion_tokens=generated.completion_tokens,
    )
