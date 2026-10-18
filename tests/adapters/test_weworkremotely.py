from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
from structlog.testing import capture_logs

from earlybird.adapters.boards import weworkremotely
from earlybird.core.errors import AdapterError
from earlybird.core.http import HttpClient

FIXTURE = Path(__file__).parents[1] / "fixtures" / "weworkremotely" / "full_stack.rss"


def _feed(*items: str) -> str:
    return f"<rss><channel><title>t</title>{''.join(items)}</channel></rss>"


def _item(title: str, link: str = "https://weworkremotely.com/remote-jobs/x", **extra: str) -> str:
    fields = "".join(f"<{tag}>{value}</{tag}>" for tag, value in extra.items())
    return f"<item><title>{title}</title><guid>{link}</guid><link>{link}</link>{fields}</item>"


@pytest.fixture(autouse=True)
def _no_pacing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("earlybird.core.http.HOST_INTERVALS", {})


def test_parse_fixture_splits_company_and_dedupes_guid() -> None:
    feed = FIXTURE.read_text()
    assert feed.count("<item>") == 6  # the live feed repeats one posting

    jobs = weworkremotely.parse(feed)

    assert len(jobs) == 5
    job = jobs[0]
    url = "https://weworkremotely.com/remote-jobs/lithic-senior-software-engineer-product-platform"
    assert job.source == "weworkremotely"
    assert job.external_id == url
    assert str(job.url) == url
    assert job.company_name == "Lithic"
    assert job.company_slug == "lithic"
    assert job.title == "Senior Software Engineer, Product Platform"
    assert job.locations == ["Anywhere in the World"]
    assert job.remote_raw == "Anywhere in the World"
    assert job.employment_type == "Full-Time"
    assert job.posted_at == datetime(2026, 10, 18, 7, 31, 5, tzinfo=UTC)
    assert job.description_text
    assert "<" not in job.description_text
    for parsed in jobs:
        assert str(parsed.url).startswith("https://weworkremotely.com/remote-jobs/")
        assert parsed.posted_at is not None
        assert parsed.posted_at.tzinfo is not None


def test_parse_prefers_country_list_over_region() -> None:
    jobs = weworkremotely.parse(FIXTURE.read_text())
    medify = next(job for job in jobs if job.company_name == "Medify")

    assert medify.locations == ["United Kingdom of Great Britain and Northern Ireland"]
    assert medify.remote_raw == "United Kingdom of Great Britain and Northern Ireland"
    assert {job.remote_raw for job in jobs} >= {"USA Only", "North America Only"}


def test_parse_splits_flagged_country_lists() -> None:
    countries = "🇫🇷 France, 🇵🇹 Portugal, 🇪🇸 Spain, and 🇳🇱 Netherlands"
    feed = _feed(_item("Acme: Engineer", region="Anywhere in the World", country=countries))

    job = weworkremotely.parse(feed)[0]

    assert job.locations == ["France", "Portugal", "Spain", "Netherlands"]
    assert job.remote_raw == "France, Portugal, Spain, Netherlands"


def test_parse_keeps_extra_colons_in_title_and_defaults_remote_raw() -> None:
    job = weworkremotely.parse(_feed(_item("Yooli: FULL TIME: Software Engineer")))[0]

    assert job.company_name == "Yooli"
    assert job.title == "FULL TIME: Software Engineer"
    assert job.remote_raw == "remote"
    assert job.posted_at is None


def test_parse_skips_malformed_items() -> None:
    feed = _feed(
        _item("Acme: Engineer"),
        _item("No company separator", link="https://weworkremotely.com/remote-jobs/y"),
        "<item><title>Acme: No link</title></item>",
    )

    with capture_logs() as logs:
        jobs = weworkremotely.parse(feed)

    assert [job.title for job in jobs] == ["Engineer"]
    skips = [entry for entry in logs if entry["event"] == "adapter.skip_posting"]
    assert len(skips) == 2


@pytest.mark.parametrize("payload", ["not xml", "<feed><entry/></feed>", "<rss/>"])
def test_parse_rejects_wrong_top_level_shape(payload: str) -> None:
    with pytest.raises(AdapterError):
        weworkremotely.parse(payload)


async def test_fetch_reads_every_feed_and_dedupes(respx_mock: respx.MockRouter) -> None:
    routes = [
        respx_mock.get(url).mock(return_value=httpx.Response(200, text=FIXTURE.read_text()))
        for url in weworkremotely.FEED_URLS
    ]

    async with HttpClient() as http:
        jobs = await weworkremotely.fetch(http)

    assert all(route.call_count == 1 for route in routes)
    assert len(jobs) == 5
