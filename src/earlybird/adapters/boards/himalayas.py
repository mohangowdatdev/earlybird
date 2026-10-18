"""Himalayas board adapter: the browse feed `https://himalayas.app/jobs/api`, cursor-paginated.

Terms (himalayas.app/docs/remote-jobs-api): show visible Himalayas source credit with a link
back, send every Apply action to the API's `applicationLink` (used here as `url`), and do not
redistribute jobs to other job boards or aggregators. Unkeyed calls share one public allowance;
the data is cached and refreshed roughly daily.
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import HttpUrl

from earlybird.core.errors import AdapterError
from earlybird.core.http import HttpClient
from earlybird.core.models import Job
from earlybird.core.text import clean, html_to_text, parse_iso, slugify

SOURCE = "himalayas"
# Docs: data refreshes about daily and polling more often has no benefit; 4 runs a day.
MIN_INTERVAL_MINUTES = 360
# Public dataset allowed? Terms: no redistribution to other job boards or aggregators.
PUBLIC_OK = False
API_URL = "https://himalayas.app/jobs/api"
PAGE_SIZE = 20  # documented maximum
MAX_PAGES = 10
_MS_THRESHOLD = 10**11  # anything larger is epoch milliseconds, not seconds

log = structlog.get_logger()


def parse(payload: Any) -> list[Job]:
    """Turn one page of the browse feed into Jobs."""
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise AdapterError(f"{SOURCE}: expected an object with a 'jobs' list")
    jobs: list[Job] = []
    for item in payload["jobs"]:
        try:
            jobs.append(_to_job(item))
        except (KeyError, TypeError, ValueError) as exc:
            log.warning("adapter.skip_posting", source=SOURCE, reason=repr(exc))
    return jobs


async def fetch(http: HttpClient) -> list[Job]:
    """Walk the feed newest-first via `nextCursor`, stopping at the end or after MAX_PAGES."""
    jobs: list[Job] = []
    cursor: str | None = None
    for _ in range(MAX_PAGES):
        params: dict[str, str | int] = {"limit": PAGE_SIZE}
        if cursor:
            params["cursor"] = cursor
        payload = await http.get_json(API_URL, params=params)
        jobs.extend(parse(payload))
        cursor = payload.get("nextCursor")
        if not payload["jobs"] or not cursor:
            break
    return jobs


def _to_job(item: Any) -> Job:
    if not isinstance(item, dict):
        raise TypeError(f"posting is a {type(item).__name__}, not an object")
    company = _required(item, "companyName")
    url = _required(item, "applicationLink")
    locations = [
        name for name in map(_location_name, item.get("locationRestrictions") or []) if name
    ]
    salary_min = _number(item.get("minSalary"))
    salary_max = _number(item.get("maxSalary"))
    has_salary = salary_min is not None or salary_max is not None
    return Job(
        source=SOURCE,
        external_id=clean(item.get("guid")) or url,
        company_slug=slugify(company),
        company_name=company,
        title=_required(item, "title"),
        url=HttpUrl(url),
        locations=locations,
        # The API documents an empty locationRestrictions list as "open worldwide".
        remote_raw=", ".join(locations) or "Worldwide",
        employment_type=clean(item.get("employmentType")),
        posted_at=_timestamp(item.get("pubDate")),
        description_text=html_to_text(item.get("description")),
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=clean(item.get("currency")) if has_salary else None,
        salary_period=clean(item.get("salaryPeriod")) if has_salary else None,
    )


def _required(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    text = clean(value) if isinstance(value, str) else None
    if not text:
        raise ValueError(f"missing {key}")
    return text


def _location_name(entry: Any) -> str | None:
    """Live data sends country names; the OpenAPI spec says `{alpha2, name, slug}` objects."""
    if isinstance(entry, dict):
        entry = entry.get("name")
    return clean(entry) if isinstance(entry, str) else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _timestamp(value: Any) -> datetime | None:
    """Live data sends epoch seconds; the docs say milliseconds or ISO 8601. Accept all three."""
    if isinstance(value, str):
        return parse_iso(value)
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        return None
    seconds = value / 1000 if value > _MS_THRESHOLD else value
    return datetime.fromtimestamp(seconds, tz=UTC)
