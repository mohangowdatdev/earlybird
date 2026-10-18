from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine

from earlybird.core.models import Company, Job
from earlybird.db.engine import make_engine, upgrade

NOW = datetime(2026, 10, 18, 6, 0, tzinfo=UTC)


@pytest.fixture
def make_job() -> Callable[..., Job]:
    def _make(**overrides: Any) -> Job:
        data: dict[str, Any] = {
            "source": "greenhouse",
            "external_id": "1001",
            "company_slug": "acme",
            "company_name": "Acme AI",
            "title": "Senior Data Engineer",
            "url": "https://boards.greenhouse.io/acme/jobs/1001",
            "locations": ["Remote - India"],
            "description_text": "5+ years of experience with Python, Spark and Airflow.",
        }
        data.update(overrides)
        return Job.model_validate(data)

    return _make


@pytest.fixture
def company() -> Company:
    return Company.model_validate(
        {"slug": "acme", "name": "Acme AI", "ats": [{"type": "greenhouse", "id": "acme"}]}
    )


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def engine(db_path: Path) -> Engine:
    url = f"sqlite:///{db_path}"
    upgrade(url)
    return make_engine(url)
