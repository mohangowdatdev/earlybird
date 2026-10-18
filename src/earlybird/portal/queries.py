"""Read models for the portal: Dawn groups, Nest columns, search."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Connection, or_, select

from earlybird.db.schema import jobs, tracker
from earlybird.private.profile import Profile
from earlybird.private.scoring import Bucket, Score, score_job

TRIAGE_OPEN = ("new", "seen")
NEST_COLUMNS = ("saved", "shortlisted", "applied", "interviewing", "offer", "rejected")


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


def _group(rows: list[dict[str, Any]], profile: Profile, since: datetime | None) -> list[Card]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["canonical_key"]].append(row)
    cards = []
    for members in groups.values():
        scored = [(score_job(m, profile), m) for m in members]
        best_score, best = max(scored, key=lambda pair: pair[0].value)
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
    order = {Bucket.STRONG: 0, Bucket.MAYBE: 1, Bucket.EXCLUDED: 2}[card.score.bucket]
    return order, -card.score.value, -card.job["first_seen_at"].timestamp()


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
) -> list[Card]:
    stmt = (
        select(jobs, tracker.c.status)
        .select_from(jobs.outerjoin(tracker, tracker.c.job_id == jobs.c.job_id))
        .where(
            jobs.c.closed_at.is_(None),
            jobs.c.first_seen_at >= now - window,
            or_(tracker.c.status.is_(None), tracker.c.status.in_(TRIAGE_OPEN)),
        )
    )
    if remote:
        stmt = stmt.where(jobs.c.remote_type == remote)
    if source:
        stmt = stmt.where(jobs.c.source == source)
    if query:
        like = f"%{query.lower()}%"
        stmt = stmt.where(or_(jobs.c.title.ilike(like), jobs.c.company_name.ilike(like)))
    rows = [dict(r) for r in conn.execute(stmt).mappings()]
    return sorted(_group(rows, profile, since), key=_rank)


def nest_cards(conn: Connection, profile: Profile) -> dict[str, list[Card]]:
    stmt = (
        select(jobs, tracker.c.status, tracker.c.note, tracker.c.updated_at)
        .select_from(jobs.join(tracker, tracker.c.job_id == jobs.c.job_id))
        .where(tracker.c.status.in_(NEST_COLUMNS))
        .order_by(tracker.c.updated_at.desc())
    )
    columns: dict[str, list[Card]] = {c: [] for c in NEST_COLUMNS}
    for row in conn.execute(stmt).mappings():
        data = dict(row)
        card = Card(
            job=data,
            score=score_job(data, profile),
            job_ids=[data["job_id"]],
            sources=[(data["source"], data["url"])],
            is_new=False,
            status=data["status"],
            extra={"note": data["note"], "updated_at": data["updated_at"]},
        )
        columns[data["status"]].append(card)
    return columns


def search(conn: Connection, profile: Profile, query: str, *, limit: int = 200) -> list[Card]:
    like = f"%{query.lower()}%"
    stmt = (
        select(jobs, tracker.c.status)
        .select_from(jobs.outerjoin(tracker, tracker.c.job_id == jobs.c.job_id))
        .where(
            jobs.c.closed_at.is_(None),
            or_(jobs.c.title.ilike(like), jobs.c.company_name.ilike(like)),
        )
        .order_by(jobs.c.first_seen_at.desc())
        .limit(limit)
    )
    rows = [dict(r) for r in conn.execute(stmt).mappings()]
    return sorted(_group(rows, profile, None), key=_rank)
