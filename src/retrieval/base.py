from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class RetrievedChunk(BaseModel):
    chunk_id: int
    endpoint_id: int
    provider_id: str
    text: str
    method: str
    path: str
    operation_id: str | None
    score: float


@runtime_checkable
class Retriever(Protocol):
    async def search(self, query: str, top_k: int) -> list[RetrievedChunk]: ...
