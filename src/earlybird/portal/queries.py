"""Read models for the portal: Dawn queue, job detail, Nest board, overview, explore, sources."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Connection, func, or_, select

from earlybird.db.schema import adapter_runs, company_status, jobs, tracker
from earlybird.private.profile import Profile
from earlybird.private.scoring import Bucket, Score, score_job

TRIAGE_OPEN = ("new", "seen")
NEST_COLUMNS = ("saved", "shortlisted", "applied", "interviewing", "offer", "rejected")
_BUCKET_ORDER = {Bucket.STRONG: 0, Bucket.MAYBE: 1, Bucket.EXCLUDED: 2}


@dataclass
class Card:
    """One canonical job (possibly seen on several sources)."""

    job: dict[str, Any]
    score: Score
    job_ids: list[str]
    sources: list[tuple[str, str]]
    is_new: bool
    status: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


Fits = dict[str, dict[str, Any]]


def _group(
    rows: list[dict[str, Any]],
    profile: Profile,
    since: datetime | None,
    fits: Fits | None = None,
    now: datetime | None = None,
) -> list[Card]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["canonical_key"]].append(row)
    cards = []
    for members in groups.values():
        scored = [(score_job(m, profile, (fits or {}).get(m["job_id"]), now), m) for m in members]
        best_score, best = max(scored, key=lambda pair: (pair[0].bucket != Bucket.EXCLUDED,
                                                          pair[0].rank))  # fmt: skip
        first_seen = min(m["first_seen_at"] for m in members)
        cards.append(
            Card(
                job={**best, "first_seen_at": first_seen},
                score=best_score,
                job_ids=[m["job_id"] for m in members],
                sources=[(m["source"], m["url"]) for m in members],
                is_new=since is None or first_seen > since,
                status=best.get("status"),
            )
        )
    return cards


def _rank(card: Card) -> tuple[int, float, float]:
    return (
        _BUCKET_ORDER[card.score.bucket],
        -card.score.rank,
        -card.job["first_seen_at"].timestamp(),
    )


def _open_jobs(
    *,
    remote: str | None,
    source: str | None,
    query: str | None,
    untriaged: bool,
    domain: str | None = None,
) -> Any:
    stmt = (
        select(jobs, tracker.c.status)
        .select_from(jobs.outerjoin(tracker, tracker.c.job_id == jobs.c.job_id))
        .where(jobs.c.closed_at.is_(None))
    )
    if untriaged:
        stmt = stmt.where(or_(tracker.c.status.is_(None), tracker.c.status.in_(TRIAGE_OPEN)))
    if remote:
        stmt = stmt.where(jobs.c.remote_type == remote)
    if source:
        stmt = stmt.where(jobs.c.source == source)
    if domain:
        stmt = stmt.where(jobs.c.domain == domain)
    if query:
        like = f"%{query.lower()}%"
        stmt = stmt.where(or_(jobs.c.title.ilike(like), jobs.c.company_name.ilike(like)))
    return stmt


def dawn_cards(
    conn: Connection,
    profile: Profile,
    *,
    now: datetime,
    window: timedelta,
    since: datetime | None,
    remote: str | None = None,
    source: str | None = None,
    query: str | None = None,
    domain: str | None = None,
    fits: Fits | None = None,
) -> list[Card]:
    stmt = _open_jobs(
        remote=remote, source=source, query=query, untriaged=True, domain=domain
    ).where(jobs.c.first_seen_at >= now - window)
    rows = [dict(r) for r in conn.execute(stmt).mappings()]
    return sorted(_group(rows, profile, since, fits, now), key=_rank)


def explore_cards(
    conn: Connection,
    profile: Profile,
    *,
    query: str | None,
    remote: str | None,
    source: str | None,
    domain: str | None = None,
    fits: Fits | None = None,
    now: datetime | None = None,
    limit: int = 3000,
) -> list[Card]:
    stmt = (
        _open_jobs(remote=remote, source=source, query=query, untriaged=False, domain=domain)
        .order_by(jobs.c.first_seen_at.desc())
        .limit(limit)
    )
    rows = [dict(r) for r in conn.execute(stmt).mappings()]
    return sorted(_group(rows, profile, None, fits, now), key=_rank)


def job_detail(
    conn: Connection,
    job_id: str,
    profile: Profile,
    fits: Fits | None = None,
    now: datetime | None = None,
) -> Card | None:
    row = (
        conn.execute(
            select(jobs, tracker.c.status, tracker.c.note, tracker.c.reason)
            .select_from(jobs.outerjoin(tracker, tracker.c.job_id == jobs.c.job_id))
            .where(jobs.c.job_id == job_id)
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    members = [
        dict(r)
        for r in conn.execute(
            select(jobs).where(
                jobs.c.canonical_key == row["canonical_key"], jobs.c.closed_at.is_(None)
            )
        ).mappings()
    ] or [dict(row)]
    data = dict(row)
    return Card(
        job={**data, "first_seen_at": min(m["first_seen_at"] for m in members)},
        score=score_job(data, profile, (fits or {}).get(job_id), now),
        job_ids=[m["job_id"] for m in members],
        sources=[(m["source"], m["url"]) for m in members],
        is_new=False,
        status=data["status"],
        extra={"note": data["note"], "reason": data["reason"]},
    )


def nest_cards(
    conn: Connection, profile: Profile, fits: Fits | None = None
) -> dict[str, list[Card]]:
    stmt = (
        select(jobs, tracker.c.status, tracker.c.note, tracker.c.updated_at)
        .select_from(jobs.join(tracker, tracker.c.job_id == jobs.c.job_id))
        .where(tracker.c.status.in_(NEST_COLUMNS))
        .order_by(tracker.c.updated_at.desc())
    )
    columns: dict[str, list[Card]] = {c: [] for c in NEST_COLUMNS}
    seen_groups: set[str] = set()
    for row in conn.execute(stmt).mappings():
        data = dict(row)
        if data["canonical_key"] in seen_groups:
            continue  # one card per canonical job, even if triaged via several sources
        seen_groups.add(data["canonical_key"])
        columns[data["status"]].append(
            Card(
                job=data,
                score=score_job(data, profile, (fits or {}).get(data["job_id"])),
                job_ids=[data["job_id"]],
                sources=[(data["source"], data["url"])],
                is_new=False,
                status=data["status"],
                extra={"note": data["note"], "updated_at": data["updated_at"]},
            )
        )
    return columns


def tracker_fingerprint(conn: Connection) -> tuple[int, Any]:
    """Cheap change marker for triage state (row count + latest update)."""
    count, latest = conn.execute(select(func.count(), func.max(tracker.c.updated_at))).one()
    return int(count), latest


def status_counts(conn: Connection) -> dict[str, int]:
    rows = conn.execute(
        select(tracker.c.status, func.count(func.distinct(jobs.c.canonical_key)))
        .select_from(tracker.join(jobs, jobs.c.job_id == tracker.c.job_id))
        .group_by(tracker.c.status)
    ).all()
    return {status: int(count) for status, count in rows}


def applied_since(conn: Connection, since: datetime) -> int:
    return int(
        conn.execute(
            select(func.count()).where(tracker.c.status == "applied", tracker.c.updated_at >= since)
        ).scalar_one()
    )


def recent_activity(conn: Connection, limit: int = 6) -> list[dict[str, Any]]:
    rows = conn.execute(
        select(
            jobs.c.job_id,
            jobs.c.title,
            jobs.c.company_name,
            jobs.c.url,
            tracker.c.status,
            tracker.c.reason,
            tracker.c.updated_at,
        )
        .select_from(tracker.join(jobs, jobs.c.job_id == tracker.c.job_id))
        .where(tracker.c.status.not_in(TRIAGE_OPEN))
        .order_by(tracker.c.updated_at.desc())
        .limit(limit)
    ).mappings()
    return [dict(r) for r in rows]


def source_history(conn: Connection, runs: int = 24) -> dict[str, list[dict[str, Any]]]:
    """Recent runs per source, oldest first (for sparklines)."""
    history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rows = conn.execute(
        select(
            adapter_runs.c.source,
            adapter_runs.c.started_at,
            adapter_runs.c.jobs_found,
            adapter_runs.c.jobs_new,
            adapter_runs.c.status,
        ).order_by(adapter_runs.c.started_at.desc())
    ).mappings()
    for row in rows:
        if len(history[row["source"]]) < runs:
            history[row["source"]].append(dict(row))
    return {source: list(reversed(items)) for source, items in history.items()}


def company_directory(conn: Connection) -> list[dict[str, Any]]:
    """Every company with open jobs (any source), busiest first."""
    rows = conn.execute(
        select(
            jobs.c.company_slug,
            func.max(jobs.c.company_name).label("name"),
            func.count().label("open_jobs"),
        )
        .where(jobs.c.closed_at.is_(None))
        .group_by(jobs.c.company_slug)
        .order_by(func.count().desc())
    ).mappings()
    return [dict(r) for r in rows]


def companies(conn: Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        select(company_status).order_by(
            company_status.c.status.desc(), company_status.c.open_jobs.desc()
        )
    ).mappings()
    return [dict(r) for r in rows]
