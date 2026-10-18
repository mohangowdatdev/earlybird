"""We Work Remotely board adapter: the engineering category RSS feeds, deduped by guid.

Each item title is "Company: Title". `region` is the board's remote region (usually "Anywhere in
the World"); `country`, when present, is a flag-prefixed list of the countries applicants must be
in and is the more specific restriction. `state` looks like the company's HQ, so it is not used.
"""

import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

import structlog
from pydantic import HttpUrl

from earlybird.core.errors import AdapterError
from earlybird.core.http import HttpClient
from earlybird.core.models import Job
from earlybird.core.text import clean, html_to_text, slugify

SOURCE = "weworkremotely"
MIN_INTERVAL_MINUTES = 0
# Public dataset allowed? Public RSS meant for syndication; no written terms reachable.
PUBLIC_OK = True
BASE_URL = "https://weworkremotely.com"
FEED_URLS = tuple(
    f"{BASE_URL}/categories/{category}.rss"
    for category in (
        "remote-back-end-programming-jobs",
        "remote-full-stack-programming-jobs",
        "remote-front-end-programming-jobs",
        "remote-devops-sysadmin-jobs",
    )
)

_FLAG = re.compile("[\U0001f1e6-\U0001f1ff]{2}")  # a pair of regional indicators is one flag

log = structlog.get_logger()


def parse(payload: str) -> list[Job]:
    """Turn one RSS feed into Jobs, keeping the first item for each guid."""
    try:
        # Feeds are size-bounded and expat does not resolve external entities by default.
        root = ET.fromstring(payload)  # noqa: S314
    except ET.ParseError as exc:
        raise AdapterError(f"{SOURCE}: feed is not valid XML: {exc}") from exc
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise AdapterError(f"{SOURCE}: expected <rss><channel>, got <{root.tag}>")
    jobs: dict[str, Job] = {}
    for item in channel.findall("item"):
        try:
            job = _to_job(item)
        except ValueError as exc:
            log.warning("adapter.skip_posting", source=SOURCE, reason=repr(exc))
            continue
        jobs.setdefault(job.external_id, job)
    return list(jobs.values())


async def fetch(http: HttpClient) -> list[Job]:
    jobs: dict[str, Job] = {}
    for url in FEED_URLS:
        for job in parse(await http.get_text(url)):
            jobs.setdefault(job.external_id, job)
    return list(jobs.values())


def _to_job(item: ET.Element) -> Job:
    company, sep, title = (_text(item, "title") or "").partition(":")
    company_name, title_text = clean(company), clean(title)
    if not sep or not company_name or not title_text:
        raise ValueError(f"title is not 'Company: Title': {_text(item, 'title')!r}")
    link = _text(item, "link") or _text(item, "guid")
    if not link:
        raise ValueError("missing link")
    url = urljoin(BASE_URL, link)
    region = _text(item, "region")
    countries = _countries(_text(item, "country"))
    return Job(
        source=SOURCE,
        external_id=_text(item, "guid") or url,
        company_slug=slugify(company_name),
        company_name=company_name,
        title=title_text,
        url=HttpUrl(url),
        locations=countries or ([region] if region else []),
        remote_raw=", ".join(countries) or region or "remote",
        employment_type=_text(item, "type"),
        posted_at=_rfc822(_text(item, "pubDate")),
        description_text=html_to_text(item.findtext("description")),
    )


def _text(item: ET.Element, tag: str) -> str | None:
    return clean(item.findtext(tag))


def _countries(value: str | None) -> list[str]:
    """`🇫🇷 France, 🇪🇸 Spain, and 🇳🇱 Netherlands` -> `["France", "Spain", "Netherlands"]`."""
    if not value:
        return []
    parts = _FLAG.split(value) if _FLAG.search(value) else [value]
    names = (re.sub(r"(,\s*)?(\band\b)?\s*$", "", part.strip()).strip() for part in parts)
    return [name for name in names if name]


def _rfc822(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
