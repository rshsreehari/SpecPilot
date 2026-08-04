from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models import Chunk, Endpoint, Provider
from src.retrieval.base import Retriever
from src.retrieval.bm25 import BM25Index, BM25Retriever, MultiProviderBM25Retriever
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.naive import NaiveVectorRetriever
from src.retrieval.rerank import RerankedRetriever

STRATEGIES = ("naive", "bm25", "hybrid", "reranked")

# One BM25Index per provider, built lazily on first use and reused after - rebuilding it
# from scratch on every request would rescan that provider's whole chunk table for no
# reason, since chunks only change on re-ingest. invalidate_bm25_cache() is the other
# half of this contract: ingest calls it so a long-lived process (the API server) never
# serves an index built from a provider's previous data after a re-ingest.
_bm25_cache: dict[str, BM25Index] = {}


def invalidate_bm25_cache(provider_id: str | None = None) -> None:
    if provider_id is None:
        _bm25_cache.clear()
    else:
        _bm25_cache.pop(provider_id, None)


async def load_bm25_index(session: AsyncSession, provider_id: str) -> BM25Index:
    """Builds (or returns the cached) BM25Index for exactly one provider. Never called
    with an unscoped query - see BM25Index's docstring for why pooling providers into one
    index would corrupt IDF."""
    if provider_id in _bm25_cache:
        return _bm25_cache[provider_id]

    rows = (
        await session.execute(
            select(
                Chunk.id,
                Chunk.endpoint_id,
                Endpoint.method,
                Endpoint.path,
                Endpoint.operation_id,
                Chunk.text,
            )
            .join(Endpoint, Chunk.endpoint_id == Endpoint.id)
            .where(Chunk.provider_id == provider_id)
        )
    ).all()
    chunks = [
        (row.id, row.endpoint_id, row.method, row.path, row.operation_id, row.text)
        for row in rows
    ]
    index = BM25Index.build(provider_id, chunks, k1=settings.bm25_k1, b=settings.bm25_b)
    _bm25_cache[provider_id] = index
    return index


async def _all_ingested_provider_ids(session: AsyncSession) -> list[str]:
    return list((await session.execute(select(Provider.id))).scalars().all())


async def _build_bm25(session: AsyncSession, provider_id: str | None) -> Retriever:
    if provider_id is not None:
        return BM25Retriever(await load_bm25_index(session, provider_id))

    provider_ids = await _all_ingested_provider_ids(session)
    indices = [await load_bm25_index(session, pid) for pid in provider_ids]
    return MultiProviderBM25Retriever(indices, k=settings.rrf_k)


async def build_retriever(
    strategy: str, session: AsyncSession, provider_id: str | None = None
) -> Retriever:
    """provider_id=None searches across every ingested provider. For naive (pgvector
    cosine similarity), that's a single query with no WHERE clause - cosine distance is
    comparable across providers. For bm25, "all providers" is NOT a single unscoped
    query; see _build_bm25 / MultiProviderBM25Retriever."""
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown retrieval strategy: {strategy!r}. Choose from {STRATEGIES}")

    naive = NaiveVectorRetriever(session, provider_id)
    if strategy == "naive":
        return naive

    bm25 = await _build_bm25(session, provider_id)
    if strategy == "bm25":
        return bm25

    hybrid = HybridRetriever(naive, bm25, k=settings.rrf_k)
    if strategy == "hybrid":
        return hybrid

    return RerankedRetriever(
        hybrid,
        model_name=settings.cross_encoder_model,
        candidate_pool=settings.rerank_candidate_pool,
    )
