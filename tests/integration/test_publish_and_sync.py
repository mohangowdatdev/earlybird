import json
from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import Engine, select

from earlybird.core.models import Company, Job
from earlybird.db.engine import make_engine, upgrade
from earlybird.db.schema import app_state, jobs, tracker
from earlybird.health.report import build_report
from earlybird.ingest import FetchOutcome, store
from earlybird.private.sync import get_state, merge_state
from earlybird.publish.dataset import PUBLIC_JOB_FIELDS, PrivacyViolationError, write_dataset
from tests.conftest import NOW


@pytest.fixture
def populated(engine: Engine, company: Company, make_job: Callable[..., Job]) -> Engine:
    outcome = FetchOutcome(
        "greenhouse",
        [make_job(), make_job(external_id="1002", title="ML Engineer")],
        company,
        company.ats[0],
    )
    store(engine, [outcome], run_id="r1", started_at=NOW, now=NOW)
    return engine


def _publish(engine: Engine, db_path: Path, out: Path) -> list[Path]:
    with engine.connect() as conn:
        report = build_report(conn, NOW)
    return write_dataset(engine, db_path, out, report, NOW)


def test_dataset_assets_and_allow_list(populated: Engine, db_path: Path, tmp_path: Path) -> None:
    out = tmp_path / "dist"
    paths = _publish(populated, db_path, out)
    assert {p.name for p in paths} == {
        "state.db.gz", "jobs.json", "health.json", "checksums.txt",
    }  # fmt: skip
    payload = json.loads((out / "jobs.json").read_text())
    assert payload["count"] == 2
    assert all(set(job) == set(PUBLIC_JOB_FIELDS) for job in payload["jobs"])
    assert "description_text" not in (out / "jobs.json").read_text()
    health = json.loads((out / "health.json").read_text())
    assert health["open_jobs"] == 2


@pytest.mark.parametrize(
    "poison",
    [
        lambda c: c.execute(jobs.update().values(description_text="full JD")),
        lambda c: c.execute(jobs.update().values(visibility="private")),
        lambda c: c.execute(tracker.insert().values(job_id="x", status="saved", updated_at=NOW)),
        lambda c: c.execute(app_state.insert().values(key="k", value="v")),
    ],
)
def test_privacy_guard_refuses(
    populated: Engine, db_path: Path, tmp_path: Path, poison: Callable[..., object]
) -> None:
    with populated.begin() as conn:
        poison(conn)
    with pytest.raises(PrivacyViolationError):
        _publish(populated, db_path, tmp_path / "dist")


def test_sync_merges_without_touching_private_data(
    populated: Engine, db_path: Path, tmp_path: Path
) -> None:
    local_url = f"sqlite:///{tmp_path / 'local.db'}"
    upgrade(local_url)
    local = make_engine(local_url)
    job_id = next(iter(populated.connect().execute(select(jobs.c.job_id)).scalars()))
    with local.begin() as conn:
        conn.execute(tracker.insert().values(job_id=job_id, status="saved", updated_at=NOW))

    assert merge_state(db_path, local, NOW) == 2
    with local.begin() as conn:
        conn.execute(jobs.update().values(description_text="fetched privately"))
    assert merge_state(db_path, local, NOW) == 0  # idempotent

    with local.connect() as conn:
        assert conn.execute(select(tracker.c.status)).scalar_one() == "saved"
        assert set(conn.execute(select(jobs.c.description_text)).scalars()) == {"fetched privately"}
        assert get_state(conn, "last_sync_at") == NOW.isoformat()
