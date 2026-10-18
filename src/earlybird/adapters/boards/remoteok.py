"""RemoteOK board adapter: one GET of `https://remoteok.com/api`, newest jobs first.

Attribution (RemoteOK API terms, repeated in the payload's first element): any page that shows
these jobs must link back to the job's RemoteOK URL with a followed link (no `rel="nofollow"`)
and name "Remote OK" as the source, or API access is suspended. Do not use the Remote OK logo.
"""

from typing import Any

import structlog
from pydantic import HttpUrl

from earlybird.core.errors import AdapterError
from earlybird.core.http import HttpClient
from earlybird.core.models import Job
from earlybird.core.text import clean, html_to_text, parse_iso, slugify

SOURCE = "remoteok"
MIN_INTERVAL_MINUTES = 0
# Public dataset allowed? Allowed with attribution: link back, credit "Remote OK".
PUBLIC_OK = True
API_URL = "https://remoteok.com/api"

log = structlog.get_logger()


def parse(payload: Any) -> list[Job]:
    """Turn the API's JSON array into Jobs, skipping the leading legal notice."""
    if not isinstance(payload, list):
        raise AdapterError(f"{SOURCE}: expected a JSON array, got {type(payload).__name__}")
    jobs: list[Job] = []
    for item in payload:
        if isinstance(item, dict) and "legal" in item:
            continue
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
    company = _required(item, "company")
    location = _text(item, "location")
    return Job(
        source=SOURCE,
        external_id=_required(item, "id"),
        company_slug=slugify(company),
        company_name=company,
        title=_required(item, "position"),
        url=HttpUrl(_required(item, "url")),
        locations=[location] if location else [],
        remote_raw=location or "remote",
        posted_at=parse_iso(item.get("date")),
        description_text=html_to_text(_unmangle(item.get("description"))),
        salary_min=_salary(item.get("salary_min")),
        salary_max=_salary(item.get("salary_max")),
    )


def _text(item: dict[str, Any], key: str) -> str | None:
    value = item.get(key)
    return clean(_unmangle(str(value))) if isinstance(value, str | int) else None


def _required(item: dict[str, Any], key: str) -> str:
    text = _text(item, key)
    if not text:
        raise ValueError(f"missing {key}")
    return text


def _unmangle(value: Any) -> str | None:
    """Most RemoteOK text is UTF-8 that was decoded as Latin-1 (`MÃ©xico`); undo that."""
    if not isinstance(value, str):
        return None
    try:
        return value.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return value


def _salary(value: Any) -> float | None:
    """RemoteOK sends 0 for "not stated". Currency and period are not given, so not guessed."""
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        return None
    return float(value)
