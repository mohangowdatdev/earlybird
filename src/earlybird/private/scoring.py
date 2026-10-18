"""Rule-based personal fit scoring (docs/matching.md). Fail-open: unknowns never push a job out.

Score out of 10: role family 0-4, skills 0-3, experience 0-1.5, location 0-1.5,
minus penalties for a seniority or salary mismatch. Watchlist (Perch) jobs bypass everything.
"""

import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from earlybird.core.models import RemoteType, Seniority
from earlybird.private.profile import Profile

STRONG_AT = 8.0
MAYBE_AT = 5.0
YOE_TOLERANCE_BELOW = 1
YOE_TOLERANCE_ABOVE = 2
_GENERIC_TOKENS = frozenset({"engineer", "engineering", "developer", "specialist", "and", "of"})
_TOKEN = re.compile(r"[a-z0-9+#.]+")


class Bucket(StrEnum):
    STRONG = "strong"
    MAYBE = "maybe"
    EXCLUDED = "excluded"


class Score(BaseModel):
    value: float
    bucket: Bucket
    reasons: list[str] = Field(default_factory=list)
    excluded_reason: str | None = None
    watchlist: bool = False


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


def _role_points(title: str, families: list[str]) -> tuple[float, str | None]:
    if not families:
        return 2.0, None  # no preference stated: neutral
    lowered = " ".join(_TOKEN.findall(title.lower()))
    title_tokens = _tokens(title)
    best = 0.0
    matched = None
    for family in families:
        family_tokens = _tokens(family)
        specific = family_tokens - _GENERIC_TOKENS
        if f" {family} " in f" {lowered} ":
            points = 4.0
        elif family_tokens <= title_tokens:
            points = 3.5
        elif specific and specific <= title_tokens:
            points = 2.5
        elif specific & title_tokens:
            points = 1.0
        else:
            points = 0.0
        if points > best:
            best, matched = points, family
    return best, matched


def _skill_points(stack: list[str], title: str, profile: Profile) -> tuple[float, list[str]]:
    have = {s.lower() for s in stack} | _tokens(title)
    must_hits = [s for s in profile.skills_must if s in have]
    nice_hits = [s for s in profile.skills_nice if s in have]
    if not profile.skills_must and not profile.skills_nice:
        return 1.5, []
    must = 2.0 * len(must_hits) / len(profile.skills_must) if profile.skills_must else 1.0
    nice = min(1.0, 0.5 * len(nice_hits))
    return min(3.0, must + nice), must_hits + nice_hits


def _yoe_points(yoe_min: int | None, yoe_max: int | None, yoe: int) -> tuple[float, bool]:
    """Returns (points, known). Overlap with [yoe-1, yoe+2] scores full; unknown is neutral."""
    if yoe_min is None and yoe_max is None:
        return 0.75, False
    low = yoe_min if yoe_min is not None else 0
    high = yoe_max if yoe_max is not None else low + 3
    fits = low <= yoe + YOE_TOLERANCE_ABOVE and high >= yoe - YOE_TOLERANCE_BELOW
    return (1.5 if fits else 0.0), True


def _location_points(remote_type: RemoteType, locations: list[str], profile: Profile) -> float:
    if remote_type in profile.remote_types:
        return 1.5
    if remote_type in (RemoteType.HYBRID, RemoteType.ONSITE):
        places = " ".join(locations).lower()
        return 1.5 if any(city in places for city in profile.cities) else 0.0
    if remote_type in (RemoteType.UNKNOWN, RemoteType.REMOTE_UNSPECIFIED):
        return 0.75  # fail open
    return 0.0


def _excluded_by_title(title: str, patterns: list[str]) -> str | None:
    lowered = title.lower()
    for pattern in patterns:
        if re.search(rf"(?<![a-z0-9]){re.escape(pattern)}(?![a-z0-9])", lowered):
            return f"title:{pattern}"
    return None


def score_job(job: Mapping[str, Any], profile: Profile) -> Score:
    """Score one job row (a mapping with the `jobs` table's columns)."""
    if job["company_slug"] in profile.watchlist:
        return Score(value=10.0, bucket=Bucket.STRONG, reasons=["watchlist"], watchlist=True)
    title: str = job["title"]
    if reason := _excluded_by_title(title, profile.exclude_title_patterns):
        return Score(value=0.0, bucket=Bucket.EXCLUDED, excluded_reason=reason)

    remote_type = RemoteType(job["remote_type"])
    seniority = Seniority(job["seniority"])
    role, family = _role_points(title, profile.role_families)
    skills, skill_hits = _skill_points(job["stack"] or [], title, profile)
    yoe, yoe_known = _yoe_points(job["yoe_min"], job["yoe_max"], profile.yoe)
    location = _location_points(remote_type, job["locations"] or [], profile)

    value = role + skills + yoe + location
    reasons = [f"role:{family}"] if family else []
    reasons += [f"skill:{s}" for s in skill_hits[:4]]
    if (
        profile.seniorities
        and seniority is not Seniority.UNKNOWN
        and seniority not in profile.seniorities
    ):
        value -= 2.0
        reasons.append(f"level:{seniority.value}")
    salary_max = job.get("salary_max")
    if (
        profile.min_salary_usd
        and salary_max
        and job.get("salary_currency") == "USD"
        and salary_max < profile.min_salary_usd
    ):
        value -= 1.0
        reasons.append("salary:below_min")
    value = round(max(0.0, min(10.0, value)), 1)

    if value >= STRONG_AT:
        bucket = Bucket.STRONG
    elif value >= MAYBE_AT:
        bucket = Bucket.MAYBE
    elif role > 0 and (not yoe_known or remote_type is RemoteType.UNKNOWN):
        bucket = Bucket.MAYBE  # unknown facts keep a plausible job alive
        reasons.append("kept:unknowns")
    else:
        bucket = Bucket.EXCLUDED
    return Score(
        value=value,
        bucket=bucket,
        reasons=reasons,
        excluded_reason="low_score" if bucket is Bucket.EXCLUDED else None,
    )
