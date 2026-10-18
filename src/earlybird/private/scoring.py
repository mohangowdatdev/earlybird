"""Personal scoring: hard filters first, then AI fit where available, rules otherwise.

Order (docs/matching.md): filters (scope, experience, seniority, location & setup, languages,
title excludes) can exclude a job, with a reason. Jobs that pass are bucketed by their AI fit
(0-100) when scored, else by the rule score (0-10). Dream companies (Perch): a relevant role there
(role-family match, or partial match plus a must-have skill) is promoted to strong. Ranking blends
fit with freshness so today's 90 beats last week's 85.
"""

import re
from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from earlybird.enrich.rules import canonical_skill
from earlybird.private.filtering import exclusion_reason
from earlybird.private.profile import Profile

STRONG_AT = 8.0
ROLE_MATCH = 2.5  # every specific word of a role family is in the title
MAYBE_AT = 5.0
FIT_STRONG, FIT_MAYBE = 75, 50
FRESHNESS_DECAY = 0.93  # per day since first seen
YOE_TOLERANCE_BELOW = 1
YOE_TOLERANCE_ABOVE = 2
_GENERIC_TOKENS = frozenset({"engineer", "engineering", "developer", "specialist", "and", "of"})
_TOKEN = re.compile(r"[a-z0-9+#.]+")


class Bucket(StrEnum):
    STRONG = "strong"
    MAYBE = "maybe"
    EXCLUDED = "excluded"


# Maximum points per component, for showing the breakdown.
PART_MAX = {"role": 4.0, "skills": 3.0, "experience": 1.5, "location": 1.5}


class Score(BaseModel):
    value: float  # 0-10 for display (AI fit / 10 when scored)
    bucket: Bucket
    reasons: list[str] = Field(default_factory=list)
    excluded_reason: str | None = None
    watchlist: bool = False
    parts: dict[str, float] = Field(default_factory=dict)
    skill_hits: list[str] = Field(default_factory=list)
    fit: int | None = None
    fit_reason: str | None = None
    matched: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    rank: float = 0.0


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


# Phrases that share words with real role families but mean something else entirely.
_FALSE_FRIENDS = re.compile(
    r"\bdata ?cent(?:er|re)s?\b|\bdata entry\b|\bdata protection officer\b|\bai trainer\b",
    re.IGNORECASE,
)


def _role_points(title: str, families: list[str]) -> tuple[float, str | None]:
    if not families:
        return 2.0, None  # no preference stated: neutral
    title = _FALSE_FRIENDS.sub(" ", title)
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
    must_hits = [s for s in profile.skills_must if canonical_skill(s) in have or s in have]
    nice_hits = [s for s in profile.skills_nice if canonical_skill(s) in have or s in have]
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


def _rank(base: float, first_seen: datetime | None, now: datetime | None) -> float:
    if first_seen is None or now is None:
        return base
    days = max(0.0, (now - first_seen).total_seconds() / 86400)
    return round(float(base * FRESHNESS_DECAY**days), 2)


def score_job(
    job: Mapping[str, Any],
    profile: Profile,
    fit: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> Score:
    """Score one job row (a mapping with the `jobs` table's columns)."""
    if reason := exclusion_reason(job, profile):
        return Score(value=0.0, bucket=Bucket.EXCLUDED, excluded_reason=reason)

    title: str = job["title"]
    role, family = _role_points(title, profile.role_families)
    skills, skill_hits = _skill_points(job["stack"] or [], title, profile)
    yoe, yoe_known = _yoe_points(job["yoe_min"], job["yoe_max"], profile.yoe)
    location = 1.5  # it passed the location filter
    value = role + skills + yoe + location
    reasons = [f"role:{family}"] if family else []
    reasons += [f"skill:{s}" for s in skill_hits[:4]]
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
    parts = {"role": role, "skills": skills, "experience": yoe, "location": location}
    ai = {
        "fit": fit["fit"],
        "fit_reason": fit["reason"],
        "matched": list(fit["matched"] or []),
        "missing": list(fit["missing"] or []),
    } if fit else {}  # fmt: skip
    first_seen = job.get("first_seen_at")
    base = float(fit["fit"]) if fit else value * 10

    must_hit = any(s in profile.skills_must for s in skill_hits)
    relevant = family is not None and (role >= ROLE_MATCH or (role > 0 and must_hit))
    if job["company_slug"] in profile.watchlist and relevant:
        return Score(
            value=max(value, STRONG_AT), bucket=Bucket.STRONG, reasons=["watchlist", *reasons],
            watchlist=True, parts=parts, skill_hits=skill_hits,
            rank=_rank(max(base, 100.0), first_seen, now), **ai,
        )  # fmt: skip

    if fit:
        bucket = (
            Bucket.STRONG
            if fit["fit"] >= FIT_STRONG
            else Bucket.MAYBE
            if fit["fit"] >= FIT_MAYBE
            else Bucket.EXCLUDED
        )
        excluded = "low AI fit" if bucket is Bucket.EXCLUDED else None
        display = round(fit["fit"] / 10, 1)
    else:
        display = value
        if value >= STRONG_AT:
            bucket = Bucket.STRONG
        elif value >= MAYBE_AT:
            bucket = Bucket.MAYBE
        elif role > 0 and not yoe_known:
            bucket = Bucket.MAYBE  # unknown facts keep a plausible job alive
            reasons.append("kept:unknowns")
        else:
            bucket = Bucket.EXCLUDED
        excluded = "low match" if bucket is Bucket.EXCLUDED else None
    return Score(
        value=display, bucket=bucket, reasons=reasons, excluded_reason=excluded,
        parts=parts, skill_hits=skill_hits, rank=_rank(base, first_seen, now), **ai,
    )  # fmt: skip
