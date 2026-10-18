"""Ashby posting API: one GET returns every published posting on a job board, unpaginated."""

import re
from typing import Any
from urllib.parse import quote

import structlog

from earlybird.core.errors import AdapterError
from earlybird.core.http import HttpClient
from earlybird.core.models import AtsRef, Company, Job
from earlybird.core.text import clean, html_to_text, parse_iso

SOURCE = "ashby"

log = structlog.get_logger()

# Compensation intervals look like "1 YEAR" or "1 HOUR".
_INTERVAL = re.compile(r"^1 ([A-Z]+)$")


def endpoint(ref: AtsRef) -> str:
    slug = quote(ref.id, safe="")
    return f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"


def _remote_raw(raw: dict[str, Any]) -> str | None:
    """`workplaceType` when set; `isRemote` alone is coarse (it is true for hybrid roles too)."""
    workplace = clean(raw.get("workplaceType"))
    if workplace:
        return workplace
    is_remote = raw.get("isRemote")
    return None if is_remote is None else f"isRemote={str(bool(is_remote)).lower()}"


def _salary(raw: dict[str, Any]) -> dict[str, Any]:
    """Use the summary salary component only when there is exactly one with a value."""
    components = (raw.get("compensation") or {}).get("summaryComponents") or []
    salaries = [c for c in components if c.get("compensationType") == "Salary"]
    if len(salaries) != 1:
        return {}
    salary = salaries[0]
    if salary.get("minValue") is None and salary.get("maxValue") is None:
        return {}
    period = _INTERVAL.match(salary.get("interval") or "")
    return {
        "salary_min": salary.get("minValue"),
        "salary_max": salary.get("maxValue"),
        "salary_currency": clean(salary.get("currencyCode")),
        "salary_period": period.group(1).lower() if period else None,
    }


def _to_job(raw: Any, company: Company) -> Job:
    if not isinstance(raw, dict):
        raise TypeError(f"posting is {type(raw).__name__}, not an object")
    title = clean(raw["title"])
    if not title:
        raise ValueError("posting has no title")
    names = [raw.get("location")]
    names += [extra.get("location") for extra in raw.get("secondaryLocations") or []]
    return Job(
        source=SOURCE,
        external_id=str(raw["id"]),
        company_slug=company.slug,
        company_name=company.name,
        title=title,
        url=raw["jobUrl"],
        locations=list(dict.fromkeys(name for value in names if (name := clean(value)))),
        remote_raw=_remote_raw(raw),
        department=clean(raw.get("department")),
        employment_type=clean(raw.get("employmentType")),
        posted_at=parse_iso(raw.get("publishedAt")),
        description_text=html_to_text(raw.get("descriptionHtml") or raw.get("descriptionPlain")),
        **_salary(raw),
    )


def parse(payload: Any, company: Company) -> list[Job]:
    """Map a job-board response to Jobs. Unlisted postings are hidden by the company: skipped."""
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise AdapterError(f"{SOURCE}: expected an object with a 'jobs' list")
    jobs: list[Job] = []
    for raw in payload["jobs"]:
        if isinstance(raw, dict) and raw.get("isListed") is False:
            continue
        try:
            jobs.append(_to_job(raw, company))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            log.warning(
                "adapter.skip_posting", source=SOURCE, company=company.slug, reason=repr(exc)
            )
    return jobs


async def fetch(http: HttpClient, company: Company, ref: AtsRef) -> list[Job]:
    return parse(await http.get_json(endpoint(ref)), company)
