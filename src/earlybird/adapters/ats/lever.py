"""Lever postings API: one GET returns every published posting (no `limit` means no paging)."""

import re
from typing import Any
from urllib.parse import quote

import structlog

from earlybird.core.errors import AdapterError
from earlybird.core.http import HttpClient
from earlybird.core.models import AtsRef, Company, Job
from earlybird.core.text import clean, from_epoch_ms, html_to_text

SOURCE = "lever"

log = structlog.get_logger()

# salaryRange.interval looks like "per-year-salary" or "per-hour-wage".
_INTERVAL = re.compile(r"^per-([a-z]+)-")


def endpoint(ref: AtsRef) -> str:
    host = "api.eu.lever.co" if ref.options.get("region") == "eu" else "api.lever.co"
    return f"https://{host}/v0/postings/{quote(ref.id, safe='')}?mode=json"


def _description(raw: dict[str, Any]) -> str | None:
    parts = [raw.get("description") or raw.get("descriptionPlain") or ""]
    for item in raw.get("lists") or []:
        parts.append(f"<h3>{item.get('text') or ''}</h3><ul>{item.get('content') or ''}</ul>")
    parts.append(raw.get("additional") or raw.get("additionalPlain") or "")
    return html_to_text("\n".join(parts))


def _salary(raw: dict[str, Any]) -> dict[str, Any]:
    salary = raw.get("salaryRange")
    if not isinstance(salary, dict) or (salary.get("min") is None and salary.get("max") is None):
        return {}
    period = _INTERVAL.match(salary.get("interval") or "")
    return {
        "salary_min": salary.get("min"),
        "salary_max": salary.get("max"),
        "salary_currency": clean(salary.get("currency")),
        "salary_period": period.group(1) if period else None,
    }


def _to_job(raw: Any, company: Company) -> Job:
    if not isinstance(raw, dict):
        raise TypeError(f"posting is {type(raw).__name__}, not an object")
    title = clean(raw["text"])
    if not title:
        raise ValueError("posting has no title")
    categories = raw.get("categories") or {}
    names = [categories.get("location"), *(categories.get("allLocations") or [])]
    return Job(
        source=SOURCE,
        external_id=str(raw["id"]),
        company_slug=company.slug,
        company_name=company.name,
        title=title,
        url=raw["hostedUrl"],
        locations=list(dict.fromkeys(name for value in names if (name := clean(value)))),
        remote_raw=clean(raw.get("workplaceType")),
        department=clean(categories.get("department") or categories.get("team")),
        employment_type=clean(categories.get("commitment")),
        posted_at=from_epoch_ms(raw.get("createdAt")),
        description_text=_description(raw),
        **_salary(raw),
    )


def parse(payload: Any, company: Company) -> list[Job]:
    """Map a `/v0/postings/{slug}?mode=json` response to Jobs, skipping malformed postings."""
    if not isinstance(payload, list):
        raise AdapterError(f"{SOURCE}: expected a list of postings")
    jobs: list[Job] = []
    for raw in payload:
        try:
            jobs.append(_to_job(raw, company))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            log.warning(
                "adapter.skip_posting", source=SOURCE, company=company.slug, reason=repr(exc)
            )
    return jobs


async def fetch(http: HttpClient, company: Company, ref: AtsRef) -> list[Job]:
    return parse(await http.get_json(endpoint(ref)), company)
