from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.tools import AgentContext
from src.answer.mistral_client import ChatClient, MistralChatClient
from src.api.schemas import QueryRequest
from src.db import async_session_maker
from src.retrieval.base import Retriever
from src.retrieval.factory import build_retriever

_chat_client = MistralChatClient()


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session_maker() as session:
        yield session


async def get_retriever(
    request: QueryRequest, session: AsyncSession = Depends(get_session)
) -> Retriever:
    return await build_retriever(request.strategy, session, request.provider_id)


async def get_agent_context(
    request: QueryRequest, session: AsyncSession = Depends(get_session)
) -> AgentContext:
    retriever = await build_retriever(request.strategy, session, request.provider_id)
    return AgentContext(
        session=session,
        retriever=retriever,
        top_k_default=request.top_k,
        provider_id=request.provider_id,
    )


def get_chat_client() -> ChatClient:
    return _chat_client
