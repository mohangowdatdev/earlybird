"""Database schema (SQLAlchemy Core). One schema for the public state and the local DB.

Public-plane tables: jobs, adapter_runs, company_status.
Private-plane tables (always empty in the public state): app_state, tracker.
See docs/data-model.md.
"""

from sqlalchemy import (
    JSON,
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

from earlybird.db.types import UTCDateTime

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "pk": "pk_%(table_name)s",
    }
)

jobs = Table(
    "jobs",
    metadata,
    Column("job_id", String(16), primary_key=True),
    Column("source", String(40), nullable=False),
    Column("external_id", String(200), nullable=False),
    Column("canonical_key", String(16), nullable=False, index=True),
    Column("company_slug", String(120), nullable=False, index=True),
    Column("company_name", String(200), nullable=False),
    Column("title", String(300), nullable=False),
    Column("url", Text, nullable=False),
    Column("locations", JSON, nullable=False),
    Column("remote_raw", String(300)),
    Column("department", String(200)),
    Column("employment_type", String(80)),
    Column("posted_at", UTCDateTime),
    # Private plane only. Always NULL in the public state (never republish descriptions).
    Column("description_text", Text),
    Column("content_hash", String(16), nullable=False),
    Column("remote_type", String(30), nullable=False),
    Column("yoe_min", Integer),
    Column("yoe_max", Integer),
    Column("seniority", String(20), nullable=False),
    Column("stack", JSON, nullable=False),
    Column("salary_min", Float),
    Column("salary_max", Float),
    Column("salary_currency", String(8)),
    Column("salary_period", String(16)),
    Column("summary", String(300), nullable=False),
    Column("extraction_method", String(10), nullable=False),
    Column("extractor_version", Integer),
    Column("visibility", String(10), nullable=False),
    Column("first_seen_at", UTCDateTime, nullable=False, index=True),
    Column("last_seen_at", UTCDateTime, nullable=False),
    Column("closed_at", UTCDateTime),
    Column("missed_runs", Integer, nullable=False),
    UniqueConstraint("source", "external_id"),
)

adapter_runs = Table(
    "adapter_runs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String(40), nullable=False, index=True),
    Column("source", String(40), nullable=False, index=True),
    Column("started_at", UTCDateTime, nullable=False),
    Column("finished_at", UTCDateTime, nullable=False),
    Column("status", String(10), nullable=False),
    Column("companies_total", Integer, nullable=False),
    Column("companies_failed", Integer, nullable=False),
    Column("jobs_found", Integer, nullable=False),
    Column("jobs_new", Integer, nullable=False),
    Column("error", Text),
)

company_status = Table(
    "company_status",
    metadata,
    Column("company_slug", String(120), primary_key=True),
    Column("source", String(40), primary_key=True),
    Column("ats_id", String(200), primary_key=True),
    Column("status", String(12), nullable=False),
    Column("last_checked_at", UTCDateTime, nullable=False),
    Column("consecutive_failures", Integer, nullable=False),
    Column("open_jobs", Integer, nullable=False),
    Column("error", Text),
)

app_state = Table(
    "app_state",
    metadata,
    Column("key", String(80), primary_key=True),
    Column("value", Text, nullable=False),
)

tracker = Table(
    "tracker",
    metadata,
    Column("job_id", String(16), primary_key=True),
    Column("status", String(20), nullable=False),
    Column("reason", String(40)),
    Column("note", Text),
    Column("updated_at", UTCDateTime, nullable=False),
)
