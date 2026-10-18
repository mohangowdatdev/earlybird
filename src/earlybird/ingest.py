"""Public-plane ingestion: fetch every source, then normalize, extract, dedupe and store.

Fetching is concurrent and failure-isolated: one broken company or source is recorded in
`adapter_runs` / `company_status` and never fails the run. Storing is idempotent.
"""

import asyncio
import hashlib
import json
import secrets
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import Connection, Engine, and_, bindparam, func, select

from earlybird.adapters.registry import (
    ATS_ADAPTERS,
    BOARD_ADAPTERS,
    PRIVATE_ONLY_BOARDS,
    PUBLIC_SOURCES,
)
from earlybird.core.errors import AdapterError, NotFoundError
from earlybird.core.http import HttpClient
from earlybird.core.models import AtsRef, Company, Job, RemoteType, Visibility
from earlybird.core.normalize import canonical_key, location_bucket
from earlybird.db.schema import adapter_runs, company_status, jobs
from earlybird.enrich.rules import extract

log = structlog.get_logger()

CLOSE_AFTER_MISSED_RUNS = 2
BOARD_JOB_TTL = timedelta(days=30)
_REMOTE_TYPES = frozenset(
    {RemoteType.REMOTE_INDIA_OK, RemoteType.REMOTE_RESTRICTED, RemoteType.REMOTE_UNSPECIFIED}
)


@dataclass
class FetchOutcome:
    source: str
    jobs: list[Job]
    company: Company | None = None
    ref: AtsRef | None = None
    error: AdapterError | None = None


@dataclass
class SourceStats:
    source: str
    started_at: datetime
    companies_total: int = 0
    companies_failed: int = 0
    jobs_found: int = 0
    jobs_new: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.companies_failed == 0:
            return "ok"
        return "error" if self.companies_failed >= self.companies_total else "partial"


async def _fetch_ats(http: HttpClient, source: str, company: Company, ref: AtsRef) -> FetchOutcome:
    try:
        found = await ATS_ADAPTERS[source].fetch(http, company, ref)
    except AdapterError as exc:
        log.warning("ingest.company_failed", source=source, company=company.slug, error=str(exc))
        return FetchOutcome(source, [], company, ref, exc)
    return FetchOutcome(source, found, company, ref)


async def _fetch_board(http: HttpClient, source: str) -> FetchOutcome:
    try:
        found = await BOARD_ADAPTERS[source].fetch(http)
    except AdapterError as exc:
        log.warning("ingest.board_failed", source=source, error=str(exc))
        return FetchOutcome(source, [], error=exc)
    return FetchOutcome(source, found)


def boards_due(conn: Connection, sources: Iterable[str], now: datetime) -> list[str]:
    """Boards whose own rate limits allow a run now (e.g. Remotive: a few calls per day)."""
    due = []
    for source in sources:
        interval = timedelta(minutes=BOARD_ADAPTERS[source].MIN_INTERVAL_MINUTES)
        last_ok = conn.execute(
            select(func.max(adapter_runs.c.started_at)).where(
                adapter_runs.c.source == source, adapter_runs.c.status == "ok"
            )
        ).scalar()
        if last_ok is None or now - last_ok >= interval:
            due.append(source)
        else:
            log.info("ingest.board_skipped", source=source, reason="min_interval")
    return due


async def fetch_all(
    http: HttpClient, companies: list[Company], ats_sources: set[str], boards: list[str]
) -> list[FetchOutcome]:
    tasks = [
        _fetch_ats(http, ref.type, company, ref)
        for company in companies
        for ref in company.ats
        if ref.type in ats_sources
    ]
    tasks += [_fetch_board(http, source) for source in boards]
    return list(await asyncio.gather(*tasks))


def _content_hash(job: Job) -> str:
    raw = json.dumps(
        [job.title, str(job.url), job.locations, job.remote_raw, job.description_text,
         job.salary_min, job.salary_max],
        default=str,
    )  # fmt: skip
    return hashlib.sha1(raw.encode()).hexdigest()[:16]  # noqa: S324


def job_row(job: Job, *, visibility: Visibility) -> dict[str, Any]:
    """Everything derived from a Job, ready for the `jobs` table (minus seen/closed bookkeeping)."""
    facts = extract(job)
    bucket = location_bucket(job.locations, is_remote=facts.remote_type in _REMOTE_TYPES)
    return {
        "job_id": job.job_id,
        "source": job.source,
        "external_id": job.external_id,
        "canonical_key": canonical_key(job.company_name, job.title, bucket),
        "company_slug": job.company_slug,
        "company_name": job.company_name,
        "title": job.title,
        "url": str(job.url),
        "locations": job.locations,
        "remote_raw": job.remote_raw,
        "department": job.department,
        "employment_type": job.employment_type,
        "posted_at": job.posted_at,
        # Descriptions are kept only on the private plane (never republished).
        "description_text": job.description_text if visibility is Visibility.PRIVATE else None,
        "content_hash": _content_hash(job),
        "remote_type": facts.remote_type.value,
        "yoe_min": facts.yoe_min,
        "yoe_max": facts.yoe_max,
        "seniority": facts.seniority.value,
        "stack": facts.stack,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "salary_currency": job.salary_currency,
        "salary_period": job.salary_period,
        "summary": facts.summary,
        "extraction_method": facts.method.value,
        "visibility": visibility.value,
    }


def _store_jobs(
    conn: Connection, found: list[Job], now: datetime, *, visibility: Visibility
) -> tuple[int, set[str]]:
    """Insert new jobs, refresh changed ones, mark all as seen. Returns (new count, seen ids)."""
    unique = {job.job_id: job for job in found}
    if not unique:
        return 0, set()
    existing = dict(
        conn.execute(
            select(jobs.c.job_id, jobs.c.content_hash).where(jobs.c.job_id.in_(list(unique)))
        ).all()
    )
    new_rows, changed_rows = [], []
    for job_id, job in unique.items():
        if job_id not in existing:
            row = job_row(job, visibility=visibility)
            new_rows.append({**row, "first_seen_at": now, "last_seen_at": now, "missed_runs": 0})
        elif existing[job_id] != _content_hash(job):
            row = job_row(job, visibility=visibility)
            changed_rows.append({f"b_{k}": v for k, v in row.items()})
    if new_rows:
        conn.execute(jobs.insert(), new_rows)
    if changed_rows:
        columns = [k.removeprefix("b_") for k in changed_rows[0] if k != "b_job_id"]
        conn.execute(
            jobs.update()
            .where(jobs.c.job_id == bindparam("b_job_id"))
            .values({c: bindparam(f"b_{c}") for c in columns}),
            changed_rows,
        )
    seen = list(unique)
    for start in range(0, len(seen), 500):
        conn.execute(
            jobs.update()
            .where(jobs.c.job_id.in_(seen[start : start + 500]))
            .values(last_seen_at=now, missed_runs=0, closed_at=None)
        )
    return len(new_rows), set(seen)


def _close_missing_for_company(
    conn: Connection, source: str, company_slug: str, seen: set[str], now: datetime
) -> None:
    """An ATS job missing from a *successful* fetch twice in a row is closed (fail-open)."""
    open_ids = conn.execute(
        select(jobs.c.job_id, jobs.c.missed_runs).where(
            jobs.c.source == source,
            jobs.c.company_slug == company_slug,
            jobs.c.closed_at.is_(None),
        )
    ).all()
    for job_id, previously_missed in open_ids:
        if job_id in seen:
            continue
        missed = previously_missed + 1
        conn.execute(
            jobs.update()
            .where(jobs.c.job_id == job_id)
            .values(
                missed_runs=missed, closed_at=now if missed >= CLOSE_AFTER_MISSED_RUNS else None
            )
        )


def _close_stale_board_jobs(conn: Connection, source: str, now: datetime) -> None:
    """Boards only list recent jobs, so absence isn't closure; age them out instead."""
    conn.execute(
        jobs.update()
        .where(
            and_(
                jobs.c.source == source,
                jobs.c.closed_at.is_(None),
                jobs.c.last_seen_at < now - BOARD_JOB_TTL,
            )
        )
        .values(closed_at=now)
    )


def _record_company(conn: Connection, outcome: FetchOutcome, now: datetime) -> None:
    assert outcome.company is not None and outcome.ref is not None  # noqa: S101
    key = {
        "company_slug": outcome.company.slug,
        "source": outcome.source,
        "ats_id": outcome.ref.id,
    }
    where = and_(*(getattr(company_status.c, k) == v for k, v in key.items()))
    previous = conn.execute(
        select(company_status.c.consecutive_failures).where(where)
    ).scalar_one_or_none()
    if outcome.error is None:
        status, failures = "ok", 0
    else:
        status = "not_found" if isinstance(outcome.error, NotFoundError) else "error"
        failures = (previous or 0) + 1
    values = {
        "status": status,
        "last_checked_at": now,
        "consecutive_failures": failures,
        "open_jobs": len(outcome.jobs),
        "error": str(outcome.error) if outcome.error else None,
    }
    if previous is None:
        conn.execute(company_status.insert().values(**key, **values))
    else:
        conn.execute(company_status.update().where(where).values(**values))


def store(
    engine: Engine,
    outcomes: list[FetchOutcome],
    *,
    run_id: str,
    started_at: datetime,
    now: datetime,
    visibility: Visibility = Visibility.PUBLIC,
) -> list[SourceStats]:
    stats: dict[str, SourceStats] = {}
    with engine.begin() as conn:
        for outcome in outcomes:
            s = stats.setdefault(outcome.source, SourceStats(outcome.source, started_at))
            s.companies_total += 1
            if outcome.error is not None:
                s.companies_failed += 1
                s.errors.append(str(outcome.error))
            new, seen = _store_jobs(conn, outcome.jobs, now, visibility=visibility)
            s.jobs_found += len(seen)
            s.jobs_new += new
            if outcome.company is not None:
                _record_company(conn, outcome, now)
                if outcome.error is None:
                    _close_missing_for_company(
                        conn, outcome.source, outcome.company.slug, seen, now
                    )
            elif outcome.error is None:
                _close_stale_board_jobs(conn, outcome.source, now)
        for s in stats.values():
            conn.execute(
                adapter_runs.insert().values(
                    run_id=run_id,
                    source=s.source,
                    started_at=s.started_at,
                    finished_at=now,
                    status=s.status,
                    companies_total=s.companies_total,
                    companies_failed=s.companies_failed,
                    jobs_found=s.jobs_found,
                    jobs_new=s.jobs_new,
                    error="\n".join(s.errors[:5]) or None,
                )
            )
    return list(stats.values())


def new_run_id(now: datetime) -> str:
    return f"{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"


async def run(
    engine: Engine,
    companies: list[Company],
    *,
    sources: set[str] | None,
    now_fn: Callable[[], datetime],
    timeout: float,
    concurrency: int,
    visibility: Visibility = Visibility.PUBLIC,
) -> list[SourceStats]:
    """Fetch and store one ingestion run. `now_fn` returns the current UTC datetime.

    Public runs (GitHub Actions) never touch private-only boards; private runs (the laptop)
    fetch only those boards, keeping their jobs and descriptions local.
    """
    started_at = now_fn()
    allowed = PUBLIC_SOURCES if visibility is Visibility.PUBLIC else PRIVATE_ONLY_BOARDS
    wanted = (sources or set(allowed)) & allowed
    with engine.connect() as conn:
        boards = boards_due(conn, sorted(wanted & set(BOARD_ADAPTERS)), started_at)
    async with HttpClient(timeout=timeout, concurrency=concurrency) as http:
        outcomes = await fetch_all(http, companies, wanted & set(ATS_ADAPTERS), boards)
    stats = store(
        engine,
        outcomes,
        run_id=new_run_id(started_at),
        started_at=started_at,
        now=now_fn(),
        visibility=visibility,
    )
    for s in stats:
        log.info(
            "ingest.source_done",
            source=s.source,
            status=s.status,
            companies=s.companies_total,
            failed=s.companies_failed,
            found=s.jobs_found,
            new=s.jobs_new,
        )
    return stats
