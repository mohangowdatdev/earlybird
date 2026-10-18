import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import respx
from structlog.testing import capture_logs

from earlybird.adapters.ats import greenhouse
from earlybird.core.errors import AdapterError, NotFoundError
from earlybird.core.http import HttpClient
from earlybird.core.models import AtsRef, Company

FIXTURE = Path(__file__).parent.parent / "fixtures" / "greenhouse" / "anthropic.json"
REF = AtsRef(type="greenhouse", id="anthropic")
COMPANY = Company(slug="anthropic", name="Anthropic", ats=[REF])
URL = "https://boards-api.greenhouse.io/v1/boards/anthropic/jobs?content=true"


def _payload() -> Any:
    return json.loads(FIXTURE.read_text())


def test_endpoint() -> None:
    assert greenhouse.endpoint(REF) == URL


def test_parse_fixture() -> None:
    jobs = greenhouse.parse(_payload(), COMPANY)

    assert len(jobs) == 4
    assert all(str(job.url).startswith("https://job-boards.greenhouse.io/") for job in jobs)
    assert all(job.posted_at is not None and job.posted_at.tzinfo for job in jobs)
    assert all(job.description_text and "<" not in job.description_text for job in jobs)

    fellows = jobs[0]
    assert fellows.source == "greenhouse"
    assert fellows.external_id == "5183044008"
    assert fellows.company_slug == "anthropic"
    assert fellows.company_name == "Anthropic"
    assert fellows.title == "Anthropic Fellows Program, AI Safety & Security"
    assert str(fellows.url) == "https://job-boards.greenhouse.io/anthropic/jobs/5183044008"
    assert fellows.locations == [
        "London, UK",
        "Ontario, CAN",
        "Remote-Friendly, United States",
        "San Francisco, CA",
        "British Columbia, CA",
        "Ontario, CA",
        "Remote-Friendly US (Travel Required)",
    ]
    assert fellows.remote_raw is None
    assert fellows.department == "AI Research & Engineering"
    assert fellows.employment_type is None
    assert fellows.posted_at == datetime(2026, 4, 10, 0, 28, 23, tzinfo=UTC)
    assert fellows.salary_min is None
    assert fellows.description_text is not None
    assert fellows.description_text.startswith("About Anthropic")


def test_parse_skips_malformed_posting() -> None:
    payload = _payload()
    payload["jobs"] = [payload["jobs"][0], {"title": "No id or url"}, "not a posting"]

    with capture_logs() as logs:
        jobs = greenhouse.parse(payload, COMPANY)

    assert [job.external_id for job in jobs] == ["5183044008"]
    assert [entry["event"] for entry in logs] == ["adapter.skip_posting"] * 2


@pytest.mark.parametrize("payload", [[], {"meta": {}}, {"jobs": {}}, None])
def test_parse_rejects_wrong_shape(payload: Any) -> None:
    with pytest.raises(AdapterError):
        greenhouse.parse(payload, COMPANY)


@respx.mock
async def test_fetch_calls_endpoint() -> None:
    route = respx.get(URL).respond(json=_payload())

    async with HttpClient(attempts=1) as http:
        jobs = await greenhouse.fetch(http, COMPANY, REF)

    assert route.called
    assert len(jobs) == 4


@respx.mock
async def test_fetch_404_raises_not_found() -> None:
    respx.get(URL).respond(404)

    async with HttpClient(attempts=1) as http:
        with pytest.raises(NotFoundError):
            await greenhouse.fetch(http, COMPANY, REF)
