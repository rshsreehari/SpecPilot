from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from src.config import settings


class Base(DeclarativeBase):
    pass


class Provider(Base):
    """One configured API spec (specs.yaml). id is the config id (e.g. "stripe"), not a
    surrogate integer - it's a stable, human-chosen handle used throughout the CLI, API,
    and eval question files."""

    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    spec_url_or_path: Mapped[str]
    spec_version: Mapped[str | None]
    openapi_version: Mapped[str | None]
    ingested_at: Mapped[datetime] = mapped_column(server_default=func.now())
    endpoint_count: Mapped[int] = mapped_column(default=0)

    endpoints: Mapped[list[Endpoint]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )


class Endpoint(Base):
    __tablename__ = "endpoints"
    __table_args__ = (
        UniqueConstraint("provider_id", "method", "path", name="uq_endpoint_provider_method_path"),
        Index("ix_endpoints_provider_method_path", "provider_id", "method", "path"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"))
    method: Mapped[str]
    path: Mapped[str]
    operation_id: Mapped[str | None]
    summary: Mapped[str | None]
    description: Mapped[str | None]
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)

    provider: Mapped[Provider] = relationship(back_populates="endpoints")
    parameters: Mapped[list[Parameter]] = relationship(
        back_populates="endpoint", cascade="all, delete-orphan"
    )
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="endpoint", cascade="all, delete-orphan"
    )


class Parameter(Base):
    __tablename__ = "parameters"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"))
    endpoint_id: Mapped[int] = mapped_column(ForeignKey("endpoints.id", ondelete="CASCADE"))
    name: Mapped[str]
    location: Mapped[str]
    type: Mapped[str | None]
    required: Mapped[bool] = mapped_column(default=False)
    description: Mapped[str | None]

    endpoint: Mapped[Endpoint] = relationship(back_populates="parameters")


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (Index("ix_chunks_provider_id", "provider_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"))
    endpoint_id: Mapped[int] = mapped_column(ForeignKey("endpoints.id", ondelete="CASCADE"))
    text: Mapped[str]
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dim))

    endpoint: Mapped[Endpoint] = relationship(back_populates="chunks")


class Query(Base):
    __tablename__ = "queries"

    id: Mapped[int] = mapped_column(primary_key=True)
    question: Mapped[str]
    answer: Mapped[str]
    code_snippet: Mapped[str | None]
    citations: Mapped[list[dict]] = mapped_column(JSON)
    retrieved_chunk_ids: Mapped[list[int]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
