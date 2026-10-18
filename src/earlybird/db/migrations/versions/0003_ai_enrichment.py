"""ai enrichment

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-19 00:45:28.304004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import earlybird.db.types

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_batches",
        sa.Column("batch_id", sa.String(length=80), nullable=False),
        sa.Column("submitted_at", earlybird.db.types.UTCDateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("job_hashes", sa.JSON(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False),
        sa.Column("finished_at", earlybird.db.types.UTCDateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("batch_id", name=op.f("pk_ai_batches")),
    )
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("model", sa.String(length=40), nullable=False),
        sa.Column("requests", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("recorded_at", earlybird.db.types.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_usage")),
    )
    with op.batch_alter_table("ai_usage", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_ai_usage_month"), ["month"], unique=False)

    op.create_table(
        "scores",
        sa.Column("job_id", sa.String(length=16), nullable=False),
        sa.Column("profile_version", sa.String(length=16), nullable=False),
        sa.Column("fit", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=400), nullable=False),
        sa.Column("matched", sa.JSON(), nullable=False),
        sa.Column("missing", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(length=40), nullable=False),
        sa.Column("scored_at", earlybird.db.types.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("job_id", "profile_version", name=op.f("pk_scores")),
    )
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("domain", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("subdomain", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("work_setup", sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column("eligible_countries", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("eligible_regions", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("office_cities", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("required_languages", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("visa_sponsorship", sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column("skills_required", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("skills_preferred", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("responsibilities", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("ai_summary", sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column("ai_version", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("ai_content_hash", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("ai_model", sa.String(length=40), nullable=True))
        batch_op.add_column(
            sa.Column("enriched_at", earlybird.db.types.UTCDateTime(timezone=True), nullable=True)
        )
    # Seniority scale changed: staff_plus -> staff_principal, executive -> director.
    op.execute("UPDATE jobs SET seniority = 'staff_principal' WHERE seniority = 'staff_plus'")
    op.execute("UPDATE jobs SET seniority = 'director' WHERE seniority = 'executive'")


def downgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("enriched_at")
        batch_op.drop_column("ai_model")
        batch_op.drop_column("ai_content_hash")
        batch_op.drop_column("ai_version")
        batch_op.drop_column("ai_summary")
        batch_op.drop_column("responsibilities")
        batch_op.drop_column("skills_preferred")
        batch_op.drop_column("skills_required")
        batch_op.drop_column("visa_sponsorship")
        batch_op.drop_column("required_languages")
        batch_op.drop_column("office_cities")
        batch_op.drop_column("eligible_regions")
        batch_op.drop_column("eligible_countries")
        batch_op.drop_column("work_setup")
        batch_op.drop_column("subdomain")
        batch_op.drop_column("domain")

    op.drop_table("scores")
    with op.batch_alter_table("ai_usage", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_ai_usage_month"))

    op.drop_table("ai_usage")
    op.drop_table("ai_batches")
