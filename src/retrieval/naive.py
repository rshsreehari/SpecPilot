from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ingest.embed import embed_texts
from src.models import Chunk, Endpoint
from src.retrieval.base import RetrievedChunk


class NaiveVectorRetriever:
    """Cosine similarity search over pgvector, optionally scoped to one provider.

    provider_id=None searches across every ingested provider's chunks in one ranked
    pgvector query - cosine distance is comparable across providers (same embedding
    model, same metric), unlike BM25's IDF, which is corpus-dependent and can't be
    pooled this way (see bm25.py)."""

    def __init__(self, session: AsyncSession, provider_id: str | None = None) -> None:
        self._session = session
        self._provider_id = provider_id

    async def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        [query_vector] = embed_texts([query])
        distance = Chunk.embedding.cosine_distance(query_vector)

        stmt = (
            select(Chunk, Endpoint, distance.label("distance"))
            .join(Endpoint, Chunk.endpoint_id == Endpoint.id)
            .order_by(distance)
            .limit(top_k)
        )
        if self._provider_id is not None:
            stmt = stmt.where(Chunk.provider_id == self._provider_id)
        result = await self._session.execute(stmt)

        return [
            RetrievedChunk(
                chunk_id=chunk.id,
                endpoint_id=endpoint.id,
                provider_id=chunk.provider_id,
                text=chunk.text,
                method=endpoint.method,
                path=endpoint.path,
                operation_id=endpoint.operation_id,
                score=1.0 - dist,
            )
            for chunk, endpoint, dist in result.all()
        ]
