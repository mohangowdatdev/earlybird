from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from earlybird.core.config import Settings
from earlybird.core.models import Company, Job
from earlybird.db.engine import make_engine
from earlybird.db.schema import tracker
from earlybird.ingest import FetchOutcome, store
from earlybird.portal.app import create_app
from tests.conftest import NOW


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        profile_path=tmp_path / "profile.yaml",
        registry_path=Path("registry/companies.yaml"),
        dawn_window_days=36500,
    )


@pytest.fixture
def client(settings: Settings, company: Company, make_job: Callable[..., Job]) -> TestClient:
    app = create_app(settings)
    engine = make_engine(settings.db_url)
    store(
        engine,
        [FetchOutcome("greenhouse", [make_job()], company, company.ats[0])],
        run_id="r1",
        started_at=NOW,
        now=NOW,
    )
    return TestClient(app)


def test_first_visit_goes_to_profile_builder(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.headers["location"] == "/profile?welcome=1"
    assert "Build your profile" in client.get("/profile?welcome=1").text


def test_profile_builder_saves_and_dawn_scores(client: TestClient, settings: Settings) -> None:
    response = client.post(
        "/profile",
        data={
            "name": "Mohan",
            "yoe": "7",
            "role_families": "Data Engineer, ML Engineer",
            "skills_must": "python, spark",
            "remote_types": ["remote_india_ok", "remote_unspecified", "unknown"],
            "exclude_title_patterns": "intern, director",
            "chirp_daily_cap": "5",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "data engineer" in settings.profile_path.read_text()

    dawn = client.get("/dawn")
    assert dawn.status_code == 200
    assert "Senior Data Engineer" in dawn.text
    assert "1 strong" in dawn.text


def test_invalid_profile_shows_errors(client: TestClient) -> None:
    response = client.post("/profile", data={"yoe": "-3"})
    assert response.status_code == 200
    assert "yoe" in response.text


def test_triage_updates_tracker(
    client: TestClient, settings: Settings, make_job: Callable[..., Job]
) -> None:
    job_id = make_job().job_id
    response = client.post(
        "/triage", data={"job_ids": job_id, "status": "dismissed", "reason": "location"}
    )
    assert response.status_code == 200
    with make_engine(settings.db_url).connect() as conn:
        row = conn.execute(select(tracker)).one()
    assert (row.status, row.reason) == ("dismissed", "location")
    assert client.post("/triage", data={"job_ids": job_id, "status": "bogus"}).status_code == 400


def test_health_endpoint(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["report"]["open_jobs"] == 1
    assert body["last_sync_at"] is None
