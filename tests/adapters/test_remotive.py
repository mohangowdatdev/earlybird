import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from structlog.testing import capture_logs

from earlybird.adapters.boards import remotive
from earlybird.core.errors import AdapterError
from earlybird.core.http import HttpClient

FIXTURE = Path(__file__).parents[1] / "fixtures" / "remotive" / "remote_jobs.json"


def _payload() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE.read_text())
    return data


def test_parse_fixture() -> None:
    jobs = remotive.parse(_payload())

    assert len(jobs) == 4
    job = jobs[0]
    assert job.source == "remotive"
    assert job.external_id == "2069746"
    assert job.company_name == "Mitre Media"
    assert job.company_slug == "mitre-media"
    assert job.title == "Tech Lead Full-Stack Rails Engineer"
    assert str(job.url) == (
        "https://remotive.com/remote-jobs/software-development/"
        "tech-lead-full-stack-rails-engineer-2069746"
    )
    assert job.locations == ["USA", "Canada", "USA timezones"]
    assert job.remote_raw == "USA, Canada, USA timezones"
    assert job.employment_type == "full_time"
    assert job.posted_at == datetime(2026, 10, 14, 20, 33, 44, tzinfo=UTC)
    assert job.salary_min is None  # salary is free text ("$170k - $200k"), not structured
    assert job.description_text
    for parsed in jobs:
        assert str(parsed.url).startswith("https://remotive.com/remote-jobs/")
        assert parsed.posted_at is not None
        assert parsed.posted_at.tzinfo is not None


def test_parse_cleans_company_whitespace() -> None:
    job = remotive.parse(_payload())[1]

    assert job.company_name == "Coalition Technologies"
    assert job.remote_raw == "Worldwide"
    assert job.locations == ["Worldwide"]


def test_parse_skips_malformed_postings() -> None:
    valid, no_url, *_ = _payload()["jobs"]
    del no_url["url"]

    with capture_logs() as logs:
        jobs = remotive.parse({"jobs": [valid, no_url, None]})

    assert [job.external_id for job in jobs] == [str(valid["id"])]
    skips = [entry for entry in logs if entry["event"] == "adapter.skip_posting"]
    assert len(skips) == 2


@pytest.mark.parametrize("payload", [[], {"job-count": 0}, "jobs"])
def test_parse_rejects_wrong_top_level_shape(payload: Any) -> None:
    with pytest.raises(AdapterError):
        remotive.parse(payload)


async def test_fetch_makes_a_single_call(respx_mock: respx.MockRouter) -> None:
    route = respx_mock.get(remotive.API_URL).mock(return_value=httpx.Response(200, json=_payload()))

    async with HttpClient() as http:
        jobs = await remotive.fetch(http)

    assert route.call_count == 1
    assert len(jobs) == 4


def test_min_interval_respects_four_calls_a_day() -> None:
    assert remotive.MIN_INTERVAL_MINUTES * 4 >= 24 * 60
