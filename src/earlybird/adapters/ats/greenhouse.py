"""Greenhouse Job Board API: one GET returns every published job for a board, unpaginated."""

import re
from typing import Any
from urllib.parse import quote

import structlog

from earlybird.core.errors import AdapterError
from earlybird.core.http import HttpClient
from earlybird.core.models import AtsRef, Company, Job
from earlybird.core.text import clean, html_to_text, parse_iso

SOURCE = "greenhouse"

log = structlog.get_logger()

# Boards join several locations into one string, e.g. "London, UK; San Francisco, CA | Remote".
_LOCATION_SEPARATOR = re.compile(r"\s*[|;]\s*")


def endpoint(ref: AtsRef) -> str:
    return f"https://boards-api.greenhouse.io/v1/boards/{quote(ref.id, safe='')}/jobs?content=true"


def _locations(raw: dict[str, Any]) -> list[str]:
    location = raw.get("location") or {}
    names = _LOCATION_SEPARATOR.split(location.get("name") or "")
    names += [office.get("name") for office in raw.get("offices") or []]
    return list(dict.fromkeys(name for value in names if (name := clean(value))))


def _to_job(raw: Any, company: Company) -> Job:
    if not isinstance(raw, dict):
        raise TypeError(f"posting is {type(raw).__name__}, not an object")
    title = clean(raw["title"])
    if not title:
        raise ValueError("posting has no title")
    departments = raw.get("departments") or []
    return Job(
        source=SOURCE,
        external_id=str(raw["id"]),
        company_slug=company.slug,
        company_name=company.name,
        title=title,
        url=raw["absolute_url"],
        locations=_locations(raw),
        department=clean(departments[0].get("name")) if departments else None,
        posted_at=parse_iso(raw.get("first_published") or raw.get("updated_at")),
        description_text=html_to_text(raw.get("content")),
    )


def parse(payload: Any, company: Company) -> list[Job]:
    """Map a `/jobs?content=true` response to Jobs, skipping malformed postings."""
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise AdapterError(f"{SOURCE}: expected an object with a 'jobs' list")
    jobs: list[Job] = []
    for raw in payload["jobs"]:
        try:
            jobs.append(_to_job(raw, company))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            log.warning(
                "adapter.skip_posting", source=SOURCE, company=company.slug, reason=repr(exc)
            )
    return jobs


async def fetch(http: HttpClient, company: Company, ref: AtsRef) -> list[Job]:
    return parse(await http.get_json(endpoint(ref)), company)
