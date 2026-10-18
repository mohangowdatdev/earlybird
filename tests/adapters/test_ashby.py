import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import respx
from structlog.testing import capture_logs

from earlybird.adapters.ats import ashby
from earlybird.core.errors import AdapterError, NotFoundError
from earlybird.core.http import HttpClient
from earlybird.core.models import AtsRef, Company

FIXTURE = Path(__file__).parent.parent / "fixtures" / "ashby" / "openai.json"
REF = AtsRef(type="ashby", id="openai")
COMPANY = Company(slug="openai", name="OpenAI", ats=[REF])
URL = "https://api.ashbyhq.com/posting-api/job-board/openai?includeCompensation=true"


def _payload() -> Any:
    return json.loads(FIXTURE.read_text())


def test_endpoint() -> None:
    assert ashby.endpoint(REF) == URL


def test_parse_fixture() -> None:
    jobs = ashby.parse(_payload(), COMPANY)

    assert len(jobs) == 4
    assert all(str(job.url).startswith("https://jobs.ashbyhq.com/openai/") for job in jobs)
    assert all(job.posted_at is not None and job.posted_at.tzinfo for job in jobs)
    assert all(job.description_text and "<" not in job.description_text for job in jobs)
    assert [job.remote_raw for job in jobs] == ["Remote", "Hybrid", "OnSite", None]

    lead = jobs[0]
    assert lead.source == "ashby"
    assert lead.external_id == "676d359b-0ef6-40a5-81d5-d4f2eb198eab"
    assert lead.company_slug == "openai"
    assert lead.company_name == "OpenAI"
    assert lead.title == "Clean Energy and New Technology Lead"
    assert str(lead.url) == "https://jobs.ashbyhq.com/openai/676d359b-0ef6-40a5-81d5-d4f2eb198eab"
    assert lead.locations == ["US - Remote", "Seattle", "San Francisco"]
    assert lead.department == "Scaling"
    assert lead.employment_type == "FullTime"
    assert lead.posted_at == datetime(2026, 10, 13, 15, 14, 57, 218000, tzinfo=UTC)
    assert (lead.salary_min, lead.salary_max) == (212800, 389000)
    assert (lead.salary_currency, lead.salary_period) == ("USD", "year")


def test_parse_salary_variants() -> None:
    hourly, no_comp = ashby.parse(_payload(), COMPANY)[2:]

    assert (hourly.salary_min, hourly.salary_max, hourly.salary_period) == (
        60.58,
        108.17,
        "hour",
    )
    assert no_comp.salary_min is None
    assert no_comp.salary_max is None
    assert no_comp.salary_currency is None


def test_parse_remote_falls_back_to_is_remote() -> None:
    raw = _payload()["jobs"][3] | {"isRemote": True}

    assert ashby.parse({"jobs": [raw]}, COMPANY)[0].remote_raw == "isRemote=true"


def test_parse_skips_unlisted_and_malformed_postings() -> None:
    payload = _payload()
    first = payload["jobs"][0]
    unlisted = first | {"id": "hidden", "isListed": False}
    payload["jobs"] = [first, unlisted, {"title": "No id or url"}, 42]

    with capture_logs() as logs:
        jobs = ashby.parse(payload, COMPANY)

    assert [job.external_id for job in jobs] == ["676d359b-0ef6-40a5-81d5-d4f2eb198eab"]
    assert [entry["event"] for entry in logs] == ["adapter.skip_posting"] * 2


@pytest.mark.parametrize("payload", [[], {"apiVersion": "1"}, {"jobs": "none"}, None])
def test_parse_rejects_wrong_shape(payload: Any) -> None:
    with pytest.raises(AdapterError):
        ashby.parse(payload, COMPANY)


@respx.mock
async def test_fetch_calls_endpoint() -> None:
    route = respx.get(URL).respond(json=_payload())

    async with HttpClient(attempts=1) as http:
        jobs = await ashby.fetch(http, COMPANY, REF)

    assert route.called
    assert len(jobs) == 4


@respx.mock
async def test_fetch_404_raises_not_found() -> None:
    respx.get(URL).respond(404)

    async with HttpClient(attempts=1) as http:
        with pytest.raises(NotFoundError):
            await ashby.fetch(http, COMPANY, REF)
