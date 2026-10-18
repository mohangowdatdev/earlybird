import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from structlog.testing import capture_logs

from earlybird.adapters.boards import remoteok
from earlybird.core.errors import AdapterError
from earlybird.core.http import HttpClient

FIXTURE = Path(__file__).parents[1] / "fixtures" / "remoteok" / "api.json"


def _payload() -> list[Any]:
    data: list[Any] = json.loads(FIXTURE.read_text())
    return data


def test_parse_fixture_skips_legal_notice() -> None:
    payload = _payload()
    assert "legal" in payload[0]

    jobs = remoteok.parse(payload)

    assert len(jobs) == len(payload) - 1
    job = jobs[0]
    assert job.source == "remoteok"
    assert job.external_id == "1137537"
    assert job.company_name == "Sanctuary Computer"
    assert job.company_slug == "sanctuary-computer"
    assert job.title == "Head of Technology"
    assert str(job.url) == (
        "https://remoteok.com/remote-jobs/remote-head-of-technology-sanctuary-computer-1137537"
    )
    assert job.locations == []
    assert job.remote_raw == "remote"
    assert job.posted_at == datetime(2026, 10, 16, 17, 55, 35, tzinfo=UTC)
    assert job.salary_min == 140000
    assert job.salary_max == 250000
    assert job.salary_currency is None
    assert job.description_text
    assert "<" not in job.description_text
    for parsed in jobs:
        assert str(parsed.url).startswith("https://remoteok.com/remote-jobs/")
        assert parsed.posted_at is not None
        assert parsed.posted_at.tzinfo is not None


def test_parse_keeps_location_text_and_treats_zero_salary_as_unknown() -> None:
    jobs = {job.external_id: job for job in remoteok.parse(_payload())}

    restricted = jobs["1136950"]
    assert restricted.locations == ["Remote - US"]
    assert restricted.remote_raw == "Remote - US"
    assert restricted.salary_min is None
    assert restricted.salary_max is None


def test_parse_repairs_double_encoded_utf8() -> None:
    jobs = {job.external_id: job for job in remoteok.parse(_payload())}

    assert jobs["1137155"].title == "Oracle Fusion Cloud Lead — Logistics & Supply Chain Management"
    assert "we’re" in (jobs["1136950"].description_text or "")


def test_parse_skips_malformed_postings() -> None:
    legal, valid, no_title, *_ = _payload()
    del no_title["position"]

    with capture_logs() as logs:
        jobs = remoteok.parse([legal, valid, no_title, "not a job"])

    assert [job.external_id for job in jobs] == [valid["id"]]
    skips = [entry for entry in logs if entry["event"] == "adapter.skip_posting"]
    assert len(skips) == 2
    assert all(entry["source"] == "remoteok" for entry in skips)


def test_parse_rejects_wrong_top_level_shape() -> None:
    with pytest.raises(AdapterError):
        remoteok.parse({"jobs": []})


async def test_fetch_calls_the_api(respx_mock: respx.MockRouter) -> None:
    route = respx_mock.get(remoteok.API_URL).mock(return_value=httpx.Response(200, json=_payload()))

    async with HttpClient() as http:
        jobs = await remoteok.fetch(http)

    assert route.call_count == 1
    assert len(jobs) == len(_payload()) - 1
