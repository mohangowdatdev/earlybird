"""Database schema (SQLAlchemy Core). One schema for the public state and the local DB.

Public-plane tables: jobs, adapter_runs, company_status, ai_batches, ai_usage.
Private-plane tables (always empty in the public state): app_state, tracker, scores.
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
    # AI enrichment (ADR 0017): generic, public-safe facts read from the description.
    Column("domain", String(20)),
    Column("subdomain", String(80)),
    Column("work_setup", String(10)),
    Column("eligible_countries", JSON),
    Column("eligible_regions", JSON),
    Column("office_cities", JSON),
    Column("required_languages", JSON),
    Column("visa_sponsorship", String(10)),
    Column("skills_required", JSON),
    Column("skills_preferred", JSON),
    Column("responsibilities", JSON),
    Column("ai_summary", String(300)),
    Column("ai_version", Integer),
    Column("ai_content_hash", String(16)),
    Column("ai_model", String(40)),
    Column("enriched_at", UTCDateTime),
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

ai_batches = Table(
    "ai_batches",
    metadata,
    Column("batch_id", String(80), primary_key=True),
    Column("submitted_at", UTCDateTime, nullable=False),
    Column("status", String(20), nullable=False),
    Column("request_count", Integer, nullable=False),
    # job_id -> content hash at submission; results apply only if the posting is unchanged
    Column("job_hashes", JSON, nullable=False),
    Column("estimated_cost_usd", Float, nullable=False),
    Column("finished_at", UTCDateTime),
)

ai_usage = Table(
    "ai_usage",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("month", String(7), nullable=False, index=True),
    Column("kind", String(20), nullable=False),
    Column("mode", String(10), nullable=False),
    Column("model", String(40), nullable=False),
    Column("requests", Integer, nullable=False),
    Column("input_tokens", Integer, nullable=False),
    Column("output_tokens", Integer, nullable=False),
    Column("cache_read_tokens", Integer, nullable=False),
    Column("cache_write_tokens", Integer, nullable=False),
    Column("cost_usd", Float, nullable=False),
    Column("recorded_at", UTCDateTime, nullable=False),
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


scores = Table(
    "scores",
    metadata,
    Column("job_id", String(16), primary_key=True),
    Column("profile_version", String(16), primary_key=True),
    Column("fit", Integer, nullable=False),
    Column("reason", String(400), nullable=False),
    Column("matched", JSON, nullable=False),
    Column("missing", JSON, nullable=False),
    Column("model", String(40), nullable=False),
    Column("scored_at", UTCDateTime, nullable=False),
)
