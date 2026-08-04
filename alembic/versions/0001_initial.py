"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-01

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "endpoints",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("operation_id", sa.String(), nullable=True),
        sa.Column("summary", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.UniqueConstraint("method", "path", name="uq_endpoint_method_path"),
    )

    op.create_table(
        "parameters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "endpoint_id",
            sa.Integer(),
            sa.ForeignKey("endpoints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("location", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("description", sa.String(), nullable=True),
    )

    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "endpoint_id",
            sa.Integer(),
            sa.ForeignKey("endpoints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
    )

    op.create_table(
        "queries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question", sa.String(), nullable=False),
        sa.Column("answer", sa.String(), nullable=False),
        sa.Column("code_snippet", sa.String(), nullable=True),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("retrieved_chunk_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("queries")
    op.drop_table("chunks")
    op.drop_table("parameters")
    op.drop_table("endpoints")
