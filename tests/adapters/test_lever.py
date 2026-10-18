import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import respx
from structlog.testing import capture_logs

from earlybird.adapters.ats import lever
from earlybird.core.errors import AdapterError, NotFoundError
from earlybird.core.http import HttpClient
from earlybird.core.models import AtsRef, Company

FIXTURE = Path(__file__).parent.parent / "fixtures" / "lever" / "quantinuum.json"
REF = AtsRef(type="lever", id="quantinuum", options={"region": "eu"})
COMPANY = Company(slug="quantinuum", name="Quantinuum", ats=[REF])
URL = "https://api.eu.lever.co/v0/postings/quantinuum?mode=json"


def _payload() -> Any:
    return json.loads(FIXTURE.read_text())


def test_endpoint_honours_region() -> None:
    assert lever.endpoint(REF) == URL
    us = AtsRef(type="lever", id="palantir")
    assert lever.endpoint(us) == "https://api.lever.co/v0/postings/palantir?mode=json"


def test_parse_fixture() -> None:
    jobs = lever.parse(_payload(), COMPANY)

    assert len(jobs) == 4
    assert all(str(job.url).startswith("https://jobs.eu.lever.co/quantinuum/") for job in jobs)
    assert all(job.posted_at is not None and job.posted_at.tzinfo for job in jobs)
    assert [job.remote_raw for job in jobs] == ["remote", "onsite", "hybrid", "onsite"]

    pic = jobs[0]
    assert pic.source == "lever"
    assert pic.external_id == "070202ce-8399-48b8-90e1-fb6952bc1d40"
    assert pic.company_slug == "quantinuum"
    assert pic.company_name == "Quantinuum"
    assert pic.title == "Senior Photonic Integrated Circuit (PIC) Design - 745"
    assert str(pic.url) == (
        "https://jobs.eu.lever.co/quantinuum/070202ce-8399-48b8-90e1-fb6952bc1d40"
    )
    assert pic.locations == [
        "US Broomfield, CO",
        "US Remote",
        "US Albuquerque, NM",
        "US Brooklyn Park, MN",
    ]
    assert pic.department == "Science & Technology"
    assert pic.employment_type == "Full-time"
    assert pic.posted_at == datetime(2026, 7, 17, 18, 43, 31, 316000, tzinfo=UTC)
    assert (pic.salary_min, pic.salary_max) == (148000, 185000)
    assert (pic.salary_currency, pic.salary_period) == ("USD", "year")


def test_parse_combines_description_lists_and_additional() -> None:
    raw = _payload()[0]
    text = lever.parse([raw], COMPANY)[0].description_text

    assert text is not None
    assert text.startswith("We are seeking a Senior Photonic Integrated Circuit")
    for item in raw["lists"]:
        assert item["text"].strip() in text
    assert "<" not in text


def test_parse_salary_variants() -> None:
    intern, no_salary = lever.parse(_payload(), COMPANY)[1:3]

    assert (intern.salary_min, intern.salary_max, intern.salary_period) == (24, 36, "hour")
    assert intern.salary_currency == "USD"
    assert no_salary.salary_min is None
    assert no_salary.salary_period is None


def test_parse_skips_malformed_posting() -> None:
    payload = [_payload()[0], {"text": "No id or url"}, None]

    with capture_logs() as logs:
        jobs = lever.parse(payload, COMPANY)

    assert [job.external_id for job in jobs] == ["070202ce-8399-48b8-90e1-fb6952bc1d40"]
    assert [entry["event"] for entry in logs] == ["adapter.skip_posting"] * 2


@pytest.mark.parametrize("payload", [{}, {"ok": False, "error": "Document not found"}, None])
def test_parse_rejects_wrong_shape(payload: Any) -> None:
    with pytest.raises(AdapterError):
        lever.parse(payload, COMPANY)


@respx.mock
async def test_fetch_calls_endpoint() -> None:
    route = respx.get(URL).respond(json=_payload())

    async with HttpClient(attempts=1) as http:
        jobs = await lever.fetch(http, COMPANY, REF)

    assert route.called
    assert len(jobs) == 4


@respx.mock
async def test_fetch_404_raises_not_found() -> None:
    respx.get(URL).respond(404, json={"ok": False, "error": "Document not found"})

    async with HttpClient(attempts=1) as http:
        with pytest.raises(NotFoundError):
            await lever.fetch(http, COMPANY, REF)
