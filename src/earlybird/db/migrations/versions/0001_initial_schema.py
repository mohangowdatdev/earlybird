"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-18 22:04:19.381401
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import earlybird.db.types

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "adapter_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("started_at", earlybird.db.types.UTCDateTime(timezone=True), nullable=False),
        sa.Column("finished_at", earlybird.db.types.UTCDateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("companies_total", sa.Integer(), nullable=False),
        sa.Column("companies_failed", sa.Integer(), nullable=False),
        sa.Column("jobs_found", sa.Integer(), nullable=False),
        sa.Column("jobs_new", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_adapter_runs")),
    )
    with op.batch_alter_table("adapter_runs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_adapter_runs_run_id"), ["run_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_adapter_runs_source"), ["source"], unique=False)

    op.create_table(
        "app_state",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_app_state")),
    )
    op.create_table(
        "company_status",
        sa.Column("company_slug", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("ats_id", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("last_checked_at", earlybird.db.types.UTCDateTime(timezone=True), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("open_jobs", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("company_slug", "source", "ats_id", name=op.f("pk_company_status")),
    )
    op.create_table(
        "jobs",
        sa.Column("job_id", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=False),
        sa.Column("canonical_key", sa.String(length=16), nullable=False),
        sa.Column("company_slug", sa.String(length=120), nullable=False),
        sa.Column("company_name", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("locations", sa.JSON(), nullable=False),
        sa.Column("remote_raw", sa.String(length=300), nullable=True),
        sa.Column("department", sa.String(length=200), nullable=True),
        sa.Column("employment_type", sa.String(length=80), nullable=True),
        sa.Column("posted_at", earlybird.db.types.UTCDateTime(timezone=True), nullable=True),
        sa.Column("description_text", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=16), nullable=False),
        sa.Column("remote_type", sa.String(length=30), nullable=False),
        sa.Column("yoe_min", sa.Integer(), nullable=True),
        sa.Column("yoe_max", sa.Integer(), nullable=True),
        sa.Column("seniority", sa.String(length=20), nullable=False),
        sa.Column("stack", sa.JSON(), nullable=False),
        sa.Column("salary_min", sa.Float(), nullable=True),
        sa.Column("salary_max", sa.Float(), nullable=True),
        sa.Column("salary_currency", sa.String(length=8), nullable=True),
        sa.Column("salary_period", sa.String(length=16), nullable=True),
        sa.Column("summary", sa.String(length=300), nullable=False),
        sa.Column("extraction_method", sa.String(length=10), nullable=False),
        sa.Column("visibility", sa.String(length=10), nullable=False),
        sa.Column("first_seen_at", earlybird.db.types.UTCDateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", earlybird.db.types.UTCDateTime(timezone=True), nullable=False),
        sa.Column("closed_at", earlybird.db.types.UTCDateTime(timezone=True), nullable=True),
        sa.Column("missed_runs", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("job_id", name=op.f("pk_jobs")),
        sa.UniqueConstraint("source", "external_id", name=op.f("uq_jobs_source")),
    )
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_jobs_canonical_key"), ["canonical_key"], unique=False)
        batch_op.create_index(batch_op.f("ix_jobs_company_slug"), ["company_slug"], unique=False)
        batch_op.create_index(batch_op.f("ix_jobs_first_seen_at"), ["first_seen_at"], unique=False)

    op.create_table(
        "tracker",
        sa.Column("job_id", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("updated_at", earlybird.db.types.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("job_id", name=op.f("pk_tracker")),
    )


def downgrade() -> None:
    op.drop_table("tracker")
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_jobs_first_seen_at"))
        batch_op.drop_index(batch_op.f("ix_jobs_company_slug"))
        batch_op.drop_index(batch_op.f("ix_jobs_canonical_key"))

    op.drop_table("jobs")
    op.drop_table("company_status")
    op.drop_table("app_state")
    with op.batch_alter_table("adapter_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_adapter_runs_source"))
        batch_op.drop_index(batch_op.f("ix_adapter_runs_run_id"))

    op.drop_table("adapter_runs")
