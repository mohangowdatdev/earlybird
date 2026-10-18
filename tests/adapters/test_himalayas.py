import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from structlog.testing import capture_logs

from earlybird.adapters.boards import himalayas
from earlybird.core.errors import AdapterError
from earlybird.core.http import HttpClient

FIXTURE = Path(__file__).parents[1] / "fixtures" / "himalayas" / "jobs_page.json"


def _page() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE.read_text())
    return data


@pytest.fixture(autouse=True)
def _no_pacing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("earlybird.core.http.HOST_INTERVALS", {})


def test_parse_fixture() -> None:
    jobs = himalayas.parse(_page())

    assert len(jobs) == 5
    job = next(j for j in jobs if j.company_name == "Circle")
    url = "https://himalayas.app/companies/circle-com/jobs/senior-data-scientist"
    assert job.source == "himalayas"
    assert job.external_id == url
    assert str(job.url) == url
    assert job.company_slug == "circle"
    assert job.title == "Senior Data Scientist"
    assert job.locations == ["United States"]
    assert job.remote_raw == "United States"
    assert job.employment_type == "Full Time"
    assert job.posted_at == datetime(2026, 10, 18, 13, 46, 50, tzinfo=UTC)
    assert job.salary_min == 152500
    assert job.salary_max == 205000
    assert job.salary_currency == "USD"
    assert job.salary_period == "annual"
    assert job.description_text
    for parsed in jobs:
        assert str(parsed.url).startswith("https://himalayas.app/companies/")
        assert parsed.posted_at is not None
        assert parsed.posted_at.tzinfo is not None


def test_parse_empty_restrictions_mean_worldwide_and_no_salary_means_no_currency() -> None:
    job = next(j for j in himalayas.parse(_page()) if j.company_name == "inovex GmbH")

    assert job.locations == []
    assert job.remote_raw == "Worldwide"
    assert job.salary_min is None
    assert job.salary_currency is None
    assert job.salary_period is None


def test_parse_accepts_documented_object_locations_and_ms_timestamps() -> None:
    page = _page()
    item = page["jobs"][0]
    item["locationRestrictions"] = [{"alpha2": "IN", "name": "India", "slug": "india"}]
    item["pubDate"] = 1792331516000

    job = himalayas.parse({"jobs": [item]})[0]

    assert job.locations == ["India"]
    assert job.posted_at == datetime(2026, 10, 18, 13, 51, 56, tzinfo=UTC)


def test_parse_skips_malformed_postings() -> None:
    valid, no_company, *_ = _page()["jobs"]
    no_company["companyName"] = None

    with capture_logs() as logs:
        jobs = himalayas.parse({"jobs": [valid, no_company, 42]})

    assert len(jobs) == 1
    skips = [entry for entry in logs if entry["event"] == "adapter.skip_posting"]
    assert len(skips) == 2


@pytest.mark.parametrize("payload", [[], {"jobs": None}, {"data": []}])
def test_parse_rejects_wrong_top_level_shape(payload: Any) -> None:
    with pytest.raises(AdapterError):
        himalayas.parse(payload)


async def test_fetch_follows_cursor_and_stops_on_empty_page(respx_mock: respx.MockRouter) -> None:
    first = _page()
    seen: list[dict[str, str]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        seen.append(params)
        if "cursor" not in params:
            return httpx.Response(200, json=first)
        return httpx.Response(200, json={"jobs": [], "nextCursor": "more"})

    respx_mock.get(host="himalayas.app", path="/jobs/api").mock(side_effect=respond)

    async with HttpClient() as http:
        jobs = await himalayas.fetch(http)

    assert len(jobs) == 5
    assert seen == [{"limit": "20"}, {"limit": "20", "cursor": first["nextCursor"]}]


async def test_fetch_stops_without_next_cursor(respx_mock: respx.MockRouter) -> None:
    last = _page()
    del last["nextCursor"]
    route = respx_mock.get(host="himalayas.app", path="/jobs/api").mock(
        return_value=httpx.Response(200, json=last)
    )

    async with HttpClient() as http:
        jobs = await himalayas.fetch(http)

    assert route.call_count == 1
    assert len(jobs) == 5


async def test_fetch_respects_page_cap(
    respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(himalayas, "MAX_PAGES", 2)
    route = respx_mock.get(host="himalayas.app", path="/jobs/api").mock(
        return_value=httpx.Response(200, json=_page())
    )

    async with HttpClient() as http:
        await himalayas.fetch(http)

    assert route.call_count == 2
