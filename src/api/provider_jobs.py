from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from src.api.provider_schemas import (
    JobProgress,
    ProviderJobResponse,
    ProviderJobStatus,
    SkippedItem,
)
from src.db import async_session_maker
from src.ingest.pipeline import IngestSummary, delete_provider_data, run_ingest
from src.logging import get_logger
from src.providers import ProviderConfig, find_cached_spec_path, remove_provider

logger = get_logger(__name__)

SKIP_REASON_LABELS = {
    "ref_missing": "A referenced OpenAPI component was missing",
    "ref_unsupported": "An external reference is not supported",
    "ref_not_object": "A referenced component was not an object",
    "ref_cycle": "A circular reference was stopped safely",
    "ref_depth_exceeded": "A reference chain exceeded the safe depth limit",
    "schema_composition_too_deep": "Schema composition exceeded the safe depth limit",
    "path_item_invalid": "A path entry was not a valid OpenAPI path object",
    "operation_invalid": "An HTTP operation was not a valid OpenAPI operation object",
    "parameter_invalid": "A parameter could not be resolved or had no name",
}


class ProviderJobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, ProviderJobResponse] = {}

    def create(self, provider_id: str) -> ProviderJobResponse:
        job_id = uuid4().hex
        job = ProviderJobResponse(
            job_id=job_id,
            provider_id=provider_id,
            status="pending",
            progress=JobProgress(current=0, total=0, stage_label="Waiting to start"),
        )
        self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> ProviderJobResponse | None:
        job = self._jobs.get(job_id)
        return job.model_copy(deep=True) if job else None

    def update(
        self,
        job_id: str,
        *,
        status: ProviderJobStatus,
        current: int,
        total: int,
        stage_label: str,
    ) -> None:
        job = self._jobs[job_id]
        job.status = status
        job.progress = JobProgress(current=current, total=total, stage_label=stage_label)

    def complete(self, job_id: str, summary: IngestSummary) -> None:
        job = self._jobs[job_id]
        job.status = "done"
        job.progress = JobProgress(
            current=summary.endpoints_parsed,
            total=summary.endpoints_parsed,
            stage_label="Complete",
        )
        job.endpoint_count = summary.endpoints_parsed
        job.skipped = [
            SkippedItem(
                kind=kind,
                count=count,
                reason=SKIP_REASON_LABELS.get(kind, kind.replace("_", " ").capitalize()),
            )
            for kind, count in sorted(summary.skipped.items())
            if count
        ]

    def fail(self, job_id: str, error: str) -> None:
        job = self._jobs[job_id]
        job.status = "failed"
        job.error = error
        job.progress = JobProgress(
            current=job.progress.current,
            total=job.progress.total,
            stage_label="Failed",
        )

    def clear(self) -> None:
        self._jobs.clear()


job_registry = ProviderJobRegistry()
_ingest_job_lock = asyncio.Lock()


async def run_provider_job(
    job_id: str,
    provider: ProviderConfig,
    managed_spec_path: Path | None = None,
    *,
    registry: ProviderJobRegistry = job_registry,
    remove_config: Callable[[str], bool] = remove_provider,
) -> None:
    async def report(stage: str, current: int, total: int, label: str) -> None:
        registry.update(
            job_id,
            status=stage,
            current=current,
            total=total,
            stage_label=label,
        )

    try:
        async with _ingest_job_lock, async_session_maker() as session:
            summary = await run_ingest(session, provider, refresh=True, progress=report)
        registry.complete(job_id, summary)
    except Exception as error:  # noqa: BLE001 - background jobs must preserve every failure
        # A failed first ingestion must not reserve the id forever or leave a dead
        # provider in the selector. Preserve the real error in the job before cleanup.
        registry.fail(job_id, str(error))
        logger.warning(
            "provider_ingest_job_failed",
            provider_id=provider.id,
            job_id=job_id,
            error=str(error),
        )
        await asyncio.to_thread(remove_config, provider.id)
        if managed_spec_path is not None:
            await asyncio.to_thread(managed_spec_path.unlink, missing_ok=True)
        cached_path = await asyncio.to_thread(find_cached_spec_path, provider.id)
        if cached_path is not None:
            await asyncio.to_thread(cached_path.unlink, missing_ok=True)
        try:
            async with async_session_maker() as cleanup_session:
                await delete_provider_data(cleanup_session, provider.id)
        except Exception as cleanup_error:  # noqa: BLE001 - original error is already preserved
            logger.warning(
                "provider_ingest_cleanup_failed",
                provider_id=provider.id,
                job_id=job_id,
                error=str(cleanup_error),
            )
