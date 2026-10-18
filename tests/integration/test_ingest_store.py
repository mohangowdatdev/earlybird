from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import Engine, select

from earlybird.adapters.registry import PRIVATE_ONLY_BOARDS, PUBLIC_SOURCES
from earlybird.core.errors import AdapterError, NotFoundError
from earlybird.core.models import Company, Job, Visibility
from earlybird.db.schema import adapter_runs, company_status, jobs
from earlybird.ingest import FetchOutcome, store
from tests.conftest import NOW


def _store(engine: Engine, outcomes: list[FetchOutcome], hours: int = 0) -> None:
    when = NOW + timedelta(hours=hours)
    store(engine, outcomes, run_id=f"run-{hours}", started_at=when, now=when)


def _jobs(engine: Engine) -> dict[str, dict[str, object]]:
    with engine.connect() as conn:
        return {r.job_id: dict(r._mapping) for r in conn.execute(select(jobs))}


def test_new_jobs_are_stored_without_descriptions(
    engine: Engine, company: Company, make_job: Callable[..., Job]
) -> None:
    job = make_job()
    _store(engine, [FetchOutcome("greenhouse", [job, job], company, company.ats[0])])
    rows = _jobs(engine)
    assert list(rows) == [job.job_id]
    row = rows[job.job_id]
    assert row["description_text"] is None
    assert row["remote_type"] == "remote_india_ok"
    assert row["first_seen_at"] == NOW
    assert row["visibility"] == "public"


def test_rerun_is_idempotent_and_updates_last_seen(
    engine: Engine, company: Company, make_job: Callable[..., Job]
) -> None:
    outcome = FetchOutcome("greenhouse", [make_job()], company, company.ats[0])
    _store(engine, [outcome])
    _store(engine, [outcome], hours=2)
    (row,) = _jobs(engine).values()
    assert row["first_seen_at"] == NOW
    assert row["last_seen_at"] == NOW + timedelta(hours=2)
    with engine.connect() as conn:
        runs = conn.execute(select(adapter_runs.c.jobs_new)).scalars().all()
    assert runs == [1, 0]


def test_changed_content_is_re_extracted(
    engine: Engine, company: Company, make_job: Callable[..., Job]
) -> None:
    _store(engine, [FetchOutcome("greenhouse", [make_job()], company, company.ats[0])])
    changed = make_job(locations=["Remote - US"])
    _store(engine, [FetchOutcome("greenhouse", [changed], company, company.ats[0])], hours=2)
    (row,) = _jobs(engine).values()
    assert row["remote_type"] == "remote_restricted"


def test_missing_jobs_close_after_two_successful_runs(
    engine: Engine, company: Company, make_job: Callable[..., Job]
) -> None:
    ref = company.ats[0]
    _store(engine, [FetchOutcome("greenhouse", [make_job()], company, ref)])
    _store(engine, [FetchOutcome("greenhouse", [], company, ref)], hours=2)
    assert next(iter(_jobs(engine).values()))["closed_at"] is None
    _store(engine, [FetchOutcome("greenhouse", [], company, ref)], hours=4)
    assert next(iter(_jobs(engine).values()))["closed_at"] == NOW + timedelta(hours=4)


def test_failed_fetch_never_closes_jobs(
    engine: Engine, company: Company, make_job: Callable[..., Job]
) -> None:
    ref = company.ats[0]
    _store(engine, [FetchOutcome("greenhouse", [make_job()], company, ref)])
    for hours in (2, 4, 6):
        failure = FetchOutcome("greenhouse", [], company, ref, AdapterError("boom"))
        _store(engine, [failure], hours=hours)
    assert next(iter(_jobs(engine).values()))["closed_at"] is None
    with engine.connect() as conn:
        status = conn.execute(select(company_status)).one()
        last_run = conn.execute(
            select(adapter_runs).order_by(adapter_runs.c.id.desc()).limit(1)
        ).one()
    assert status.consecutive_failures == 3
    assert status.status == "error"
    assert last_run.status == "error"


def test_partial_failure_and_dead_slug(
    engine: Engine, company: Company, make_job: Callable[..., Job]
) -> None:
    other = company.model_copy(update={"slug": "gone"})
    _store(
        engine,
        [
            FetchOutcome("greenhouse", [make_job()], company, company.ats[0]),
            FetchOutcome("greenhouse", [], other, other.ats[0], NotFoundError("404")),
        ],
    )
    with engine.connect() as conn:
        run = conn.execute(select(adapter_runs)).one()
        dead = (
            conn.execute(
                select(company_status.c.company_slug).where(company_status.c.status == "not_found")
            )
            .scalars()
            .all()
        )
    assert run.status == "partial"
    assert dead == ["gone"]


def test_board_jobs_age_out(engine: Engine, make_job: Callable[..., Job]) -> None:
    board_job = make_job(source="remoteok", external_id="r1", company_slug="acme-ai")
    _store(engine, [FetchOutcome("remoteok", [board_job])])
    _store(engine, [FetchOutcome("remoteok", [])], hours=24 * 29)
    assert next(iter(_jobs(engine).values()))["closed_at"] is None
    _store(engine, [FetchOutcome("remoteok", [])], hours=24 * 31)
    assert next(iter(_jobs(engine).values()))["closed_at"] is not None


def test_private_only_boards_never_reach_public_runs() -> None:
    assert {"himalayas", "remotive"} <= PRIVATE_ONLY_BOARDS
    assert not PRIVATE_ONLY_BOARDS & PUBLIC_SOURCES


def test_private_visibility_keeps_description_locally(
    engine: Engine, make_job: Callable[..., Job]
) -> None:
    job = make_job(source="himalayas", external_id="h1", company_slug="acme-ai")
    when = NOW
    store(
        engine,
        [FetchOutcome("himalayas", [job])],
        run_id="p1",
        started_at=when,
        now=when,
        visibility=Visibility.PRIVATE,
    )
    (row,) = _jobs(engine).values()
    assert row["visibility"] == "private"
    assert row["description_text"] == job.description_text
