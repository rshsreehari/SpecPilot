"""multi-provider support

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-03

Additive migration: existing Stripe rows are preserved, never wiped. A `providers` table
is added, a `provider_id` column is backfilled onto endpoints/parameters/chunks from a
single synthesized 'stripe' provider row, and only then is it made NOT NULL and folded
into endpoints' uniqueness constraint. See docs/HISTORY.md / STATE.md for why this project
moved from a single hardcoded spec to configurable providers.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_STRIPE_SPEC_URL = "https://raw.githubusercontent.com/stripe/openapi/master/openapi/spec3.json"


def upgrade() -> None:
    op.create_table(
        "providers",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("spec_url_or_path", sa.String(), nullable=False),
        sa.Column("spec_version", sa.String(), nullable=True),
        sa.Column("openapi_version", sa.String(), nullable=True),
        sa.Column("ingested_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("endpoint_count", sa.Integer(), nullable=False, server_default="0"),
    )

    # Every existing endpoints/parameters/chunks row predates the provider concept and
    # is Stripe data - a single synthesized row accounts for all of it.
    op.execute(
        sa.text(
            "INSERT INTO providers (id, name, spec_url_or_path) "
            "VALUES ('stripe', 'Stripe', :spec_url)"
        ).bindparams(spec_url=_STRIPE_SPEC_URL)
    )

    for table in ("endpoints", "parameters", "chunks"):
        op.add_column(table, sa.Column("provider_id", sa.String(), nullable=True))
        op.execute(f"UPDATE {table} SET provider_id = 'stripe'")
        op.alter_column(table, "provider_id", nullable=False)
        op.create_foreign_key(
            f"fk_{table}_provider_id",
            table,
            "providers",
            ["provider_id"],
            ["id"],
            ondelete="CASCADE",
        )

    op.drop_constraint("uq_endpoint_method_path", "endpoints", type_="unique")
    op.create_unique_constraint(
        "uq_endpoint_provider_method_path", "endpoints", ["provider_id", "method", "path"]
    )
    op.create_index(
        "ix_endpoints_provider_method_path", "endpoints", ["provider_id", "method", "path"]
    )
    op.create_index("ix_chunks_provider_id", "chunks", ["provider_id"])

    op.execute(
        "UPDATE providers SET endpoint_count = "
        "(SELECT count(*) FROM endpoints WHERE endpoints.provider_id = providers.id)"
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_provider_id", table_name="chunks")
    op.drop_index("ix_endpoints_provider_method_path", table_name="endpoints")
    op.drop_constraint("uq_endpoint_provider_method_path", "endpoints", type_="unique")
    op.create_unique_constraint("uq_endpoint_method_path", "endpoints", ["method", "path"])

    for table in ("chunks", "parameters", "endpoints"):
        op.drop_constraint(f"fk_{table}_provider_id", table, type_="foreignkey")
        op.drop_column(table, "provider_id")

    op.drop_table("providers")
