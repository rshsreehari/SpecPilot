from __future__ import annotations

from pydantic import BaseModel


class Citation(BaseModel):
    method: str
    path: str
    operation_id: str | None = None
    provider_id: str | None = None
    verified: bool = False


class AnswerResult(BaseModel):
    answer: str
    code_snippet: str | None
    citations: list[Citation]
    retrieved_chunk_ids: list[int]
