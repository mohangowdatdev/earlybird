"""Hard filters, in Mohan's order: scope → experience → seniority → location & setup → languages.

Deterministic, no AI, run on the enriched schema. Fail-open: a value the posting doesn't state
never excludes a job. Every exclusion carries a short reason for the excluded review.
"""

import re
from collections.abc import Mapping
from typing import Any

from earlybird.core.geo import canonical_city, countries_in
from earlybird.core.models import Domain, RemoteType, Seniority, WorkSetup
from earlybird.enrich.rules import SENIORITY_LABELS
from earlybird.private.profile import Profile

YOE_BELOW, YOE_ABOVE = 1, 2  # tolerance around your years: -1 / +2
_SETUP_FROM_REMOTE = {
    RemoteType.REMOTE_INDIA_OK.value: WorkSetup.REMOTE,
    RemoteType.REMOTE_RESTRICTED.value: WorkSetup.REMOTE,
    RemoteType.REMOTE_UNSPECIFIED.value: WorkSetup.REMOTE,
    RemoteType.HYBRID.value: WorkSetup.HYBRID,
    RemoteType.ONSITE.value: WorkSetup.ONSITE,
}


def work_setup(job: Mapping[str, Any]) -> WorkSetup:
    if job.get("work_setup") and job["work_setup"] != WorkSetup.UNKNOWN.value:
        return WorkSetup(job["work_setup"])
    return _SETUP_FROM_REMOTE.get(job.get("remote_type") or "", WorkSetup.UNKNOWN)


def _offices(job: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    """(city names, countries) the job's offices are in."""
    cities: set[str] = set()
    countries: set[str] = set(job.get("eligible_countries") or [])
    for office in job.get("office_cities") or []:
        cities.add(office["city"])
        countries.add(office["country"])
    if not cities:
        for location in job.get("locations") or []:
            name, country = canonical_city(location)
            if country:
                cities.add(name)
                countries.add(country)
    return cities, countries


def location_fit(job: Mapping[str, Any], profile: Profile) -> bool | None:
    """True/False when the job's location is known; None (pass) when the posting doesn't say."""
    setup = work_setup(job)
    remote_ok: bool | None = None
    eligible = set(job.get("eligible_countries") or []) | countries_in(
        job.get("eligible_regions") or []
    )
    if eligible:
        remote_ok = bool(eligible & profile.remote_countries)
    elif job.get("remote_type") == RemoteType.REMOTE_INDIA_OK.value:
        remote_ok = "IN" in profile.remote_countries or None
    cities, countries = _offices(job)
    office_ok: bool | None = None
    if cities or countries:
        office_ok = bool(cities & set(profile.cities)) or bool(countries & set(profile.countries))
    if setup is WorkSetup.REMOTE:
        return remote_ok
    if setup in (WorkSetup.HYBRID, WorkSetup.ONSITE):
        return office_ok
    known = [v for v in (remote_ok, office_ok) if v is not None]
    return any(known) if known else None


def _title_excluded(title: str, patterns: list[str]) -> str | None:
    lowered = title.lower()
    for pattern in patterns:
        if re.search(rf"(?<![a-z0-9]){re.escape(pattern)}(?![a-z0-9])", lowered):
            return f"title contains “{pattern}”"
    return None


def exclusion_reason(job: Mapping[str, Any], profile: Profile) -> str | None:  # noqa: PLR0911
    """Why this job is filtered out for this profile, or None if it passes."""
    if reason := _title_excluded(job["title"], profile.exclude_title_patterns):
        return reason
    domain = job.get("domain")
    if domain == Domain.OTHER.value:
        return "outside data, AI and security"
    if domain and Domain(domain) not in profile.scope:
        return f"{domain} role, not in your spaces"
    low, high = job.get("yoe_min"), job.get("yoe_max")
    if low is not None and low > profile.yoe + YOE_ABOVE:
        return f"needs {low}+ years"
    if high is not None and high < profile.yoe - YOE_BELOW:
        return f"for {high} or fewer years"
    seniority = Seniority(job.get("seniority") or "unknown")
    known_level = seniority is not Seniority.UNKNOWN
    if profile.seniorities and known_level and seniority not in profile.seniorities:
        return f"{SENIORITY_LABELS[seniority]} level"
    setup = work_setup(job)
    if setup is not WorkSetup.UNKNOWN and profile.work_setups and setup not in profile.work_setups:
        return f"{setup.value} role"
    if (profile.countries or profile.cities) and location_fit(job, profile) is False:
        return "location doesn't match"
    spoken = {lang.lower() for lang in profile.languages}
    missing = [lang for lang in job.get("required_languages") or [] if lang.lower() not in spoken]
    if missing:
        return f"requires {missing[0]}"
    return None
