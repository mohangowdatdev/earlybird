"""A small work queue for model extraction that outlives one run (descriptions included).

Lives in its own SQLite file, never in the public state: on Actions it is kept in the repo's
private Actions cache, on the laptop under var/. Losing it only means some jobs keep rule facts.
"""

from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import JSON, Column, Engine, Integer, MetaData, String, Table, delete, select

from earlybird.core.models import Job
from earlybird.db.engine import make_engine
from earlybird.db.types import UTCDateTime

metadata = MetaData()
llm_queue = Table(
    "llm_queue",
    metadata,
    Column("job_id", String(16), primary_key=True),
    Column("priority", Integer, nullable=False),
    Column("enqueued_at", UTCDateTime, nullable=False),
    Column("job", JSON, nullable=False),
)
MAX_AGE = timedelta(days=14)


def open_queue(path: Path) -> Engine:
    engine = make_engine(f"sqlite:///{path}")
    metadata.create_all(engine)
    return engine


def enqueue(engine: Engine, items: Iterable[tuple[Job, int]], now: datetime) -> int:
    rows = [
        {
            "job_id": job.job_id,
            "priority": prio,
            "enqueued_at": now,
            "job": job.model_dump(mode="json"),
        }
        for job, prio in items
    ]
    if not rows:
        return 0
    with engine.begin() as conn:
        conn.execute(delete(llm_queue).where(llm_queue.c.job_id.in_([r["job_id"] for r in rows])))
        conn.execute(llm_queue.insert(), rows)
    return len(rows)


def take(engine: Engine, limit: int) -> list[Job]:
    with engine.connect() as conn:
        payloads = conn.execute(
            select(llm_queue.c.job)
            .order_by(llm_queue.c.priority, llm_queue.c.enqueued_at)
            .limit(limit)
        ).scalars()
        return [Job.model_validate(p) for p in payloads]


def remove(engine: Engine, job_ids: Iterable[str]) -> None:
    ids = list(job_ids)
    if ids:
        with engine.begin() as conn:
            conn.execute(delete(llm_queue).where(llm_queue.c.job_id.in_(ids)))


def prune(engine: Engine, now: datetime) -> None:
    with engine.begin() as conn:
        conn.execute(delete(llm_queue).where(llm_queue.c.enqueued_at < now - MAX_AGE))


def size(engine: Engine) -> int:
    with engine.connect() as conn:
        return len(conn.execute(select(llm_queue.c.job_id)).all())
