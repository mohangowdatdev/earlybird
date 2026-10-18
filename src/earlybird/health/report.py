"""Source health: error, zero-results streak, sharp drops, staleness (docs/operations.md)."""

from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field
from sqlalchemy import Connection, func, select

from earlybird.db.schema import adapter_runs, company_status, jobs

ZERO_STREAK = 3
DROP_RATIO = 0.3  # flag when the latest count is below 30% of the 7-day average (a >70% drop)
STALE_AFTER = timedelta(hours=6)


class Flag(StrEnum):
    ERROR = "error"
    PARTIAL = "partial"
    ZERO_RESULTS = "zero_results_3x"
    DROP = "drop_70pct"
    STALE = "stale"


class SourceHealth(BaseModel):
    source: str
    last_run_at: datetime
    last_status: str
    jobs_found: int
    companies_total: int
    companies_failed: int
    flags: list[Flag] = Field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return not self.flags


class HealthReport(BaseModel):
    generated_at: datetime
    sources: list[SourceHealth]
    open_jobs: int
    companies_tracked: int
    new_last_24h: int
    dead_slugs: list[str]

    @property
    def problems(self) -> list[SourceHealth]:
        return [s for s in self.sources if s.flags]


def _source_health(
    conn: Connection, source: str, now: datetime, stale_after: timedelta
) -> SourceHealth:
    runs = conn.execute(
        select(adapter_runs)
        .where(adapter_runs.c.source == source)
        .order_by(adapter_runs.c.started_at.desc())
        .limit(100)
    ).all()
    latest = runs[0]
    flags: list[Flag] = []
    if latest.status == "error":
        flags.append(Flag.ERROR)
    elif latest.status == "partial":
        flags.append(Flag.PARTIAL)
    recent = runs[:ZERO_STREAK]
    if len(recent) == ZERO_STREAK and all(r.jobs_found == 0 for r in recent):
        flags.append(Flag.ZERO_RESULTS)
    week = [
        r.jobs_found
        for r in runs[1:]
        if r.started_at >= now - timedelta(days=7) and r.status != "error"
    ]
    if week and latest.jobs_found < DROP_RATIO * (sum(week) / len(week)):
        flags.append(Flag.DROP)
    if now - latest.started_at > stale_after:
        flags.append(Flag.STALE)
    return SourceHealth(
        source=source,
        last_run_at=latest.started_at,
        last_status=latest.status,
        jobs_found=latest.jobs_found,
        companies_total=latest.companies_total,
        companies_failed=latest.companies_failed,
        flags=flags,
    )


def build_report(
    conn: Connection, now: datetime, *, stale_after: dict[str, timedelta] | None = None
) -> HealthReport:
    """`stale_after` overrides staleness per source (e.g. rate-limited boards run rarely)."""
    overrides = stale_after or {}
    sources = conn.execute(select(adapter_runs.c.source).distinct()).scalars().all()
    open_filter = (jobs.c.closed_at.is_(None), jobs.c.visibility == "public")
    return HealthReport(
        generated_at=now,
        sources=[
            _source_health(conn, s, now, overrides.get(s, STALE_AFTER)) for s in sorted(sources)
        ],
        open_jobs=conn.execute(select(func.count()).where(*open_filter)).scalar_one(),
        companies_tracked=conn.execute(
            select(func.count(func.distinct(company_status.c.company_slug)))
        ).scalar_one(),
        new_last_24h=conn.execute(
            select(func.count()).where(
                *open_filter, jobs.c.first_seen_at >= now - timedelta(days=1)
            )
        ).scalar_one(),
        dead_slugs=sorted(
            conn.execute(
                select(company_status.c.company_slug).where(company_status.c.status == "not_found")
            ).scalars()
        ),
    )
