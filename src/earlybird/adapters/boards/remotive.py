"""Remotive board adapter: one GET of `https://remotive.com/api/remote-jobs` (all categories).

Terms (API legal notice and github.com/remotive-io/remote-jobs-api): link back to the job's
Remotive URL and name Remotive as the source; do not submit the jobs to third-party sites such
as Google Jobs or LinkedIn Jobs. Jobs are delayed by 24 hours. Call at most 4 times a day;
more than 2 calls a minute are blocked.
"""

from typing import Any

import structlog
from pydantic import HttpUrl

from earlybird.core.errors import AdapterError
from earlybird.core.http import HttpClient
from earlybird.core.models import Job
from earlybird.core.text import clean, html_to_text, parse_iso, slugify

SOURCE = "remotive"
MIN_INTERVAL_MINUTES = 360  # "we advise max. 4 times a day"
# Public dataset allowed? Terms: do not submit Remotive jobs to third-party websites.
PUBLIC_OK = False
API_URL = "https://remotive.com/api/remote-jobs"

log = structlog.get_logger()


def parse(payload: Any) -> list[Job]:
    """Turn the API's `{"jobs": [...]}` object into Jobs."""
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
    return parse(await http.get_json(API_URL))


def _to_job(item: Any) -> Job:
    if not isinstance(item, dict):
        raise TypeError(f"posting is a {type(item).__name__}, not an object")
    company = _required(item, "company_name")
    restriction = clean(item.get("candidate_required_location"))
    locations = [part for part in map(clean, (restriction or "").split(",")) if part]
    return Job(
        source=SOURCE,
        external_id=_required(item, "id"),
        company_slug=slugify(company),
        company_name=company,
        title=_required(item, "title"),
        url=HttpUrl(_required(item, "url")),
        locations=locations,
        remote_raw=restriction or "remote",
        employment_type=clean(item.get("job_type")),
        posted_at=parse_iso(item.get("publication_date")),  # naive in the feed; read as UTC
        description_text=html_to_text(item.get("description")),
    )


def _required(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    text = clean(str(value)) if isinstance(value, str | int) else None
    if not text:
        raise ValueError(f"missing {key}")
    return text
