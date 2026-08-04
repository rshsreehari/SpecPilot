from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ProviderSourceType = Literal["url", "upload"]
ProviderJobStatus = Literal[
    "pending", "downloading", "parsing", "embedding", "done", "failed"
]


class ProviderSourceRequest(BaseModel):
    source_type: ProviderSourceType
    url: str | None = None
    spec_content: str | None = None

    @model_validator(mode="after")
    def validate_source(self) -> ProviderSourceRequest:
        if self.source_type == "url":
            if not self.url or self.spec_content is not None:
                raise ValueError("URL sources require 'url' and must not include 'spec_content'")
        elif not self.spec_content or self.url is not None:
            raise ValueError(
                "upload sources require 'spec_content' and must not include 'url'"
            )
        return self


class ProviderCreateRequest(ProviderSourceRequest):
    id: str = Field(
        min_length=2,
        max_length=40,
        pattern=r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])$",
    )
    name: str = Field(min_length=1, max_length=120)
    path_prefixes: list[str] = Field(default_factory=list)


class PrefixPreview(BaseModel):
    prefix: str
    endpoint_count: int


class ProviderPreviewResponse(BaseModel):
    openapi_version: str
    title: str
    endpoint_count: int
    sample_paths: list[str]
    detected_tags: list[str]
    path_prefixes: list[PrefixPreview]
    warnings: list[str]


class ProviderCreateResponse(BaseModel):
    job_id: str
    provider_id: str
    status: Literal["pending"] = "pending"


class JobProgress(BaseModel):
    current: int
    total: int
    stage_label: str


class SkippedItem(BaseModel):
    kind: str
    count: int
    reason: str


class ProviderJobResponse(BaseModel):
    job_id: str
    provider_id: str
    status: ProviderJobStatus
    progress: JobProgress
    endpoint_count: int | None = None
    skipped: list[SkippedItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class ProviderSourceResponse(BaseModel):
    type: Literal["url", "upload", "file"]
    location: str


class ProviderResponse(BaseModel):
    id: str
    name: str
    ingested: bool
    endpoint_count: int
    openapi_version: str | None
    ingested_at: datetime | None
    source: ProviderSourceResponse
    origin: Literal["bundled", "runtime"]
    evaluation_questions_defined: bool
    evaluation_questions_path: str


class DeletedCounts(BaseModel):
    providers: int
    endpoints: int
    parameters: int
    chunks: int
    managed_spec_file: bool


class ProviderDeleteResponse(BaseModel):
    provider_id: str
    deleted: DeletedCounts
