from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ingest.chunk import build_chunk_text
from src.ingest.download import fetch_spec
from src.ingest.embed import embed_texts
from src.ingest.parse import parse_spec
from src.logging import get_logger, warning_counts
from src.models import Chunk, Endpoint, Parameter, Provider
from src.providers import ProviderConfig
from src.retrieval.factory import invalidate_bm25_cache

logger = get_logger(__name__)


@dataclass
class IngestSummary:
    provider_id: str
    endpoints_parsed: int
    parameters_extracted: int
    chunks_embedded: int
    skipped: dict[str, int] = field(default_factory=dict)


@dataclass
class DeleteSummary:
    providers: int
    endpoints: int
    parameters: int
    chunks: int


IngestProgress = Callable[[str, int, int, str], Awaitable[None]]


async def _report_progress(
    progress: IngestProgress | None,
    stage: str,
    current: int,
    total: int,
    label: str,
) -> None:
    if progress is not None:
        await progress(stage, current, total, label)


def _provider_location(provider: ProviderConfig) -> str:
    return provider.path if provider.is_local else (provider.url or "")


async def _upsert_provider_row(
    session: AsyncSession, provider: ProviderConfig, spec: dict[str, Any], endpoint_count: int
) -> None:
    info = spec.get("info")
    spec_version = info.get("version") if isinstance(info, dict) else None
    openapi_version = spec.get("openapi")

    existing = await session.get(Provider, provider.id)
    if existing is None:
        session.add(
            Provider(
                id=provider.id,
                name=provider.name,
                spec_url_or_path=_provider_location(provider),
                spec_version=spec_version,
                openapi_version=openapi_version,
                endpoint_count=endpoint_count,
            )
        )
    else:
        existing.name = provider.name
        existing.spec_url_or_path = _provider_location(provider)
        existing.spec_version = spec_version
        existing.openapi_version = openapi_version
        existing.endpoint_count = endpoint_count
        existing.ingested_at = datetime.now(UTC)


async def run_ingest(
    session: AsyncSession,
    provider: ProviderConfig,
    refresh: bool = False,
    progress: IngestProgress | None = None,
) -> IngestSummary:
    """Ingests exactly one provider's spec. Scoped end to end: deletes only this
    provider's existing rows before rebuilding, never another provider's - two providers
    must be able to coexist, and re-ingesting one must never touch the other's data."""
    warning_counts.clear()
    if provider.is_local:
        await _report_progress(progress, "parsing", 0, 0, "Reading uploaded spec")
    else:
        await _report_progress(progress, "downloading", 0, 0, "Downloading spec")
    spec = await fetch_spec(provider, refresh=refresh)
    await _report_progress(progress, "parsing", 0, 0, "Parsing OpenAPI document")
    parsed_endpoints = await asyncio.to_thread(
        parse_spec,
        spec,
        path_prefixes=provider.path_prefixes,
    )
    logger.info(
        "spec_parsed",
        provider=provider.id,
        endpoint_count=len(parsed_endpoints),
        path_prefixes=provider.path_prefixes,
    )

    await session.execute(delete(Chunk).where(Chunk.provider_id == provider.id))
    await session.execute(delete(Parameter).where(Parameter.provider_id == provider.id))
    await session.execute(delete(Endpoint).where(Endpoint.provider_id == provider.id))

    # Provider row must exist (and be flushed) before any endpoint referencing it is
    # flushed - session.get() below triggers autoflush, and if endpoints were already
    # added to the session by that point, the FK constraint fails because the provider
    # row itself hadn't been inserted yet.
    await _upsert_provider_row(session, provider, spec, len(parsed_endpoints))

    texts = [build_chunk_text(endpoint) for endpoint in parsed_endpoints]
    total = len(texts)
    await _report_progress(progress, "embedding", 0, total, f"Embedding 0 of {total}")
    embeddings: list[list[float]] = []
    batch_size = 32
    for start in range(0, total, batch_size):
        batch = texts[start : start + batch_size]
        batch_embeddings = await asyncio.to_thread(embed_texts, batch)
        embeddings.extend(batch_embeddings)
        current = min(start + len(batch), total)
        await _report_progress(
            progress,
            "embedding",
            current,
            total,
            f"Embedding {current} of {total}",
        )

    parameter_count = 0
    for parsed, text, embedding in zip(parsed_endpoints, texts, embeddings, strict=True):
        endpoint = Endpoint(
            provider_id=provider.id,
            method=parsed.method,
            path=parsed.path,
            operation_id=parsed.operation_id,
            summary=parsed.summary,
            description=parsed.description,
            tags=parsed.tags,
        )
        endpoint.parameters = [
            Parameter(
                provider_id=provider.id,
                name=param.name,
                location=param.location,
                type=param.type,
                required=param.required,
                description=param.description,
            )
            for param in parsed.parameters
        ]
        parameter_count += len(endpoint.parameters)
        endpoint.chunks = [Chunk(provider_id=provider.id, text=text, embedding=embedding)]
        session.add(endpoint)

    await session.commit()
    invalidate_bm25_cache(provider.id)

    summary = IngestSummary(
        provider_id=provider.id,
        endpoints_parsed=len(parsed_endpoints),
        parameters_extracted=parameter_count,
        chunks_embedded=len(parsed_endpoints),
        skipped=dict(warning_counts),
    )
    logger.info(
        "ingest_complete",
        provider=provider.id,
        endpoints_parsed=summary.endpoints_parsed,
        parameters_extracted=summary.parameters_extracted,
        skipped=summary.skipped,
    )
    return summary


async def delete_provider_data(session: AsyncSession, provider_id: str) -> DeleteSummary:
    """Deletes a provider row and, via ondelete=CASCADE, every endpoint/parameter/chunk
    that belonged to it. Does not touch specs.yaml - callers remove the config entry
    separately (src.providers.remove_provider)."""
    async def count(model: type[Provider | Endpoint | Parameter | Chunk]) -> int:
        statement = select(func.count()).select_from(model)
        if model is Provider:
            statement = statement.where(Provider.id == provider_id)
        else:
            statement = statement.where(model.provider_id == provider_id)
        return int((await session.execute(statement)).scalar_one())

    summary = DeleteSummary(
        providers=await count(Provider),
        endpoints=await count(Endpoint),
        parameters=await count(Parameter),
        chunks=await count(Chunk),
    )
    await session.execute(delete(Provider).where(Provider.id == provider_id))
    await session.commit()
    invalidate_bm25_cache(provider_id)
    return summary
