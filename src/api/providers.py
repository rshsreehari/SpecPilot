from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.provider_jobs import job_registry, run_provider_job
from src.api.provider_schemas import (
    DeletedCounts,
    PrefixPreview,
    ProviderCreateRequest,
    ProviderCreateResponse,
    ProviderDeleteResponse,
    ProviderJobResponse,
    ProviderPreviewResponse,
    ProviderResponse,
    ProviderSourceRequest,
    ProviderSourceResponse,
)
from src.eval.questions import QUESTIONS_DIR
from src.ingest.download import (
    MAX_SPEC_BYTES,
    SpecDownloadError,
    SpecFormatError,
    download_spec_text,
    parse_spec_text,
)
from src.ingest.parse import ParsedEndpoint, parse_spec
from src.ingest.pipeline import delete_provider_data
from src.logging import warning_counts
from src.models import Provider
from src.providers import (
    SPEC_CACHE_DIR,
    ProviderConfig,
    ProviderConfigError,
    add_provider,
    find_cached_spec_path,
    load_providers,
    remove_provider,
)

router = APIRouter(prefix="/api/providers", tags=["providers"])
_config_lock = asyncio.Lock()
_UPLOAD_DIR = SPEC_CACHE_DIR / "uploads"


def _source_for_config(config: ProviderConfig) -> ProviderSourceResponse:
    if config.url:
        return ProviderSourceResponse(type="url", location=config.url)
    location = config.path or ""
    source_type = "upload" if _is_managed_upload(Path(location)) else "file"
    return ProviderSourceResponse(type=source_type, location=location)


def _source_for_row(row: Provider) -> ProviderSourceResponse:
    location = row.spec_url_or_path
    if location.startswith(("http://", "https://")):
        return ProviderSourceResponse(type="url", location=location)
    source_type = "upload" if _is_managed_upload(Path(location)) else "file"
    return ProviderSourceResponse(type=source_type, location=location)


def _is_managed_upload(path: Path) -> bool:
    try:
        path.resolve().relative_to(_UPLOAD_DIR.resolve())
        return True
    except ValueError:
        return False


async def _question_metadata(provider_id: str) -> tuple[bool, str]:
    path = QUESTIONS_DIR / f"{provider_id}.yaml"
    return await asyncio.to_thread(path.is_file), str(path)


@router.get("", response_model=list[ProviderResponse])
async def list_providers(session: AsyncSession = Depends(get_session)) -> list[ProviderResponse]:
    """Configured providers plus any still-ingested orphan rows, with enough source and
    evaluation metadata for the provider management UI to explain their actual state."""
    configured = await asyncio.to_thread(load_providers)
    ingested_rows = {row.id: row for row in (await session.execute(select(Provider))).scalars().all()}

    providers: list[ProviderResponse] = []
    for provider_id, config in configured.items():
        row = ingested_rows.get(provider_id)
        questions_defined, questions_path = await _question_metadata(provider_id)
        providers.append(
            ProviderResponse(
                id=provider_id,
                name=config.name,
                ingested=row is not None,
                endpoint_count=row.endpoint_count if row else 0,
                openapi_version=row.openapi_version if row else None,
                ingested_at=row.ingested_at if row else None,
                source=_source_for_config(config),
                origin=config.origin,
                evaluation_questions_defined=questions_defined,
                evaluation_questions_path=questions_path,
            )
        )

    for provider_id, row in ingested_rows.items():
        if provider_id in configured:
            continue
        questions_defined, questions_path = await _question_metadata(provider_id)
        providers.append(
            ProviderResponse(
                id=provider_id,
                name=row.name,
                ingested=True,
                endpoint_count=row.endpoint_count,
                openapi_version=row.openapi_version,
                ingested_at=row.ingested_at,
                source=_source_for_row(row),
                origin="runtime",
                evaluation_questions_defined=questions_defined,
                evaluation_questions_path=questions_path,
            )
        )

    return providers


async def _read_source(request: ProviderSourceRequest, provider_id: str) -> str:
    if request.source_type == "url":
        assert request.url is not None  # validated by ProviderSourceRequest
        return await download_spec_text(request.url, provider_id)
    assert request.spec_content is not None  # validated by ProviderSourceRequest
    if len(request.spec_content.encode("utf-8")) > MAX_SPEC_BYTES:
        raise HTTPException(status_code=413, detail="Uploaded spec is larger than the 50 MB limit")
    return request.spec_content


def _prefix_counts(endpoints: list[ParsedEndpoint]) -> list[PrefixPreview]:
    counts: dict[str, int] = {}
    for endpoint in endpoints:
        first_segment = endpoint.path.strip("/").split("/", 1)[0]
        prefix = f"/{first_segment}" if first_segment else "/"
        counts[prefix] = counts.get(prefix, 0) + 1
    return [
        PrefixPreview(prefix=prefix, endpoint_count=count)
        for prefix, count in sorted(counts.items())
    ]


def _warning_messages() -> list[str]:
    labels = {
        "ref_missing": "Some referenced components are missing from the document.",
        "ref_unsupported": "External references are not supported and were skipped.",
        "ref_cycle": "Circular references were stopped safely.",
        "ref_depth_exceeded": "A reference chain exceeded the safe depth limit.",
        "schema_composition_too_deep": "A schema composition exceeded the safe depth limit.",
        "path_item_invalid": "Some path entries were not valid OpenAPI path objects.",
        "operation_invalid": "Some HTTP operations were not valid OpenAPI operation objects.",
        "parameter_invalid": "Some parameters could not be resolved or had no name.",
    }
    return [
        f"{labels.get(kind, kind.replace('_', ' ').capitalize())} ({count})"
        for kind, count in sorted(warning_counts.items())
        if count
    ]


@router.post("/preview", response_model=ProviderPreviewResponse)
async def preview_provider(request: ProviderSourceRequest) -> ProviderPreviewResponse:
    try:
        text = await _read_source(request, "preview")
        spec = await asyncio.to_thread(parse_spec_text, text, "preview")
        warning_counts.clear()
        endpoints = await asyncio.to_thread(parse_spec, spec)
    except HTTPException:
        raise
    except SpecDownloadError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except SpecFormatError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    info = spec.get("info")
    title = info.get("title") if isinstance(info, dict) else None
    paths = list(dict.fromkeys(endpoint.path for endpoint in endpoints))
    tags = sorted({tag for endpoint in endpoints for tag in endpoint.tags})
    return ProviderPreviewResponse(
        openapi_version=str(spec["openapi"]),
        title=title if isinstance(title, str) and title.strip() else "Untitled API",
        endpoint_count=len(endpoints),
        sample_paths=paths[:10],
        detected_tags=tags,
        path_prefixes=_prefix_counts(endpoints),
        warnings=_warning_messages(),
    )


def _upload_extension(text: str) -> str:
    try:
        json.loads(text)
        return "json"
    except json.JSONDecodeError:
        return "yaml"


async def _write_managed_upload(provider_id: str, text: str) -> Path:
    extension = await asyncio.to_thread(_upload_extension, text)
    path = _UPLOAD_DIR / f"{provider_id}.{extension}"
    await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(path.write_text, text)
    return path


@router.post(
    "",
    response_model=ProviderCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_provider(
    request: ProviderCreateRequest,
    background_tasks: BackgroundTasks,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> ProviderCreateResponse:
    managed_path: Path | None = None
    async with _config_lock:
        configured = await asyncio.to_thread(load_providers)
        if request.id in configured or await session.get(Provider, request.id) is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Provider id {request.id!r} is already taken. Choose another id.",
            )

        try:
            if request.source_type == "upload":
                assert request.spec_content is not None  # validated by ProviderCreateRequest
                if len(request.spec_content.encode("utf-8")) > MAX_SPEC_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="Uploaded spec is larger than the 50 MB limit",
                    )
                managed_path = await _write_managed_upload(request.id, request.spec_content)

            provider = await asyncio.to_thread(
                add_provider,
                request.id,
                request.name.strip(),
                request.url,
                str(managed_path) if managed_path else None,
                tuple(request.path_prefixes),
                "runtime",
            )
        except ProviderConfigError as error:
            if managed_path is not None:
                await asyncio.to_thread(managed_path.unlink, missing_ok=True)
            raise HTTPException(status_code=409, detail=str(error)) from error

    job = job_registry.create(request.id)
    background_tasks.add_task(run_provider_job, job.job_id, provider, managed_path)
    response.headers["Location"] = f"/api/providers/jobs/{job.job_id}"
    return ProviderCreateResponse(job_id=job.job_id, provider_id=request.id)


@router.get("/jobs/{job_id}", response_model=ProviderJobResponse)
async def get_provider_job(job_id: str) -> ProviderJobResponse:
    job = job_registry.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Ingestion job {job_id!r} was not found. Jobs are stored in memory and "
                "are cleared when the SpecPilot server restarts."
            ),
        )
    return job


async def _remove_managed_files(provider_id: str, config: ProviderConfig) -> bool:
    candidates: list[Path] = []
    cached = await asyncio.to_thread(find_cached_spec_path, provider_id)
    if cached is not None:
        candidates.append(cached)
    if config.path and _is_managed_upload(Path(config.path)):
        candidates.append(Path(config.path))

    deleted = False
    for path in dict.fromkeys(candidates):
        if await asyncio.to_thread(path.is_file):
            await asyncio.to_thread(path.unlink)
            deleted = True
    return deleted


@router.delete("/{provider_id}", response_model=ProviderDeleteResponse)
async def delete_provider(
    provider_id: str,
    session: AsyncSession = Depends(get_session),
) -> ProviderDeleteResponse:
    async with _config_lock:
        configured = await asyncio.to_thread(load_providers)
        config = configured.get(provider_id)
        if config is None:
            raise HTTPException(
                status_code=400,
                detail=f"Provider {provider_id!r} is not configured in specs.yaml.",
            )
        # Delete the database data first. If the later config write fails, a retry can
        # still find the configured provider and finish cleanup; the reverse order can
        # leave an orphan row that this endpoint is required to refuse.
        summary = await delete_provider_data(session, provider_id)
        removed = await asyncio.to_thread(remove_provider, provider_id)
        if not removed:
            raise HTTPException(
                status_code=400,
                detail=f"Provider {provider_id!r} could not be removed from specs.yaml.",
            )

    managed_file_deleted = await _remove_managed_files(provider_id, config)
    return ProviderDeleteResponse(
        provider_id=provider_id,
        deleted=DeletedCounts(
            providers=summary.providers,
            endpoints=summary.endpoints,
            parameters=summary.parameters,
            chunks=summary.chunks,
            managed_spec_file=managed_file_deleted,
        ),
    )
