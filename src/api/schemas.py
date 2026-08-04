from __future__ import annotations

from pydantic import BaseModel, Field

from src.agent.loop import TraceStep
from src.answer.schemas import Citation
from src.config import settings


class QueryRequest(BaseModel):
    question: str
    top_k: int = Field(default=settings.top_k_default, ge=1, le=20)
    strategy: str = Field(default=settings.retrieval_strategy)
    provider_id: str | None = Field(
        default=None, description="Restrict to one provider; omit to search all ingested providers"
    )


class QueryResponse(BaseModel):
    answer: str
    code_snippet: str | None
    citations: list[Citation]
    retrieved_chunk_ids: list[int]


class AgentQueryResponse(QueryResponse):
    trace: list[TraceStep]
