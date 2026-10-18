"""AI fit scoring (private plane): how well each *filtered* job matches your profile.

Runs only on jobs that pass the hard filters and have been enriched, using the structured facts
(not descriptions), so it is cheap. Your profile and the rubric sit in a cached system prompt.
One score per (job, profile version): editing the profile re-scores. Budget-capped per month.
"""

import asyncio
import json
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

import anthropic
import structlog
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import Engine, select

from earlybird.core.config import Settings
from earlybird.core.geo import COUNTRIES
from earlybird.db.schema import jobs, scores, tracker
from earlybird.enrich.ai import Usage
from earlybird.enrich.pipeline import month_spend, record_usage
from earlybird.private.filtering import exclusion_reason
from earlybird.private.profile import Profile

log = structlog.get_logger()
KIND = "fit"
MAX_OUTPUT_TOKENS = 600
EST_COST_PER_JOB = 0.0003  # conservative; real cost is recorded from usage
SCORE_WINDOW = timedelta(days=14)

RUBRIC = """You score how well a job fits one candidate, from 0 to 100.
Use the candidate profile below and the job's structured facts. Weigh, in order:
1. Role and subdomain match with what the candidate does and wants (the biggest factor).
2. Skills: required skills the candidate has (strong signal), required skills they lack
   (penalise core gaps, not minor tools), preferred skills (small bonus).
3. Level and experience: the job's seniority and years against the candidate's.
4. The candidate's stated expectations (what they want next, what they avoid).
Calibration: 85-100 apply today; 70-84 strong; 50-69 plausible but notable gaps; below 50 poor.
Location, work setup and languages were already filtered; ignore them unless the facts show a
clear conflict. Be decisive and specific: the reason must name the decisive factors.
Reply with JSON only."""

FIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "fit": {"type": "integer"},
        "reason": {"type": "string"},
        "matched_skills": {"type": "array", "items": {"type": "string"}},
        "missing_skills": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["fit", "reason", "matched_skills", "missing_skills"],
    "additionalProperties": False,
}


class FitResult(BaseModel):
    fit: int = Field(ge=0, le=100)
    reason: str
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)


def profile_block(profile: Profile) -> str:
    countries = [COUNTRIES.get(c, c) for c in profile.countries]
    lines = [
        f"Years of experience: {profile.yoe}",
        f"Spaces: {', '.join(d.value for d in profile.scope)}",
        f"Target roles: {', '.join(profile.role_families) or 'not stated'}",
        f"Levels wanted: {', '.join(s.value for s in profile.seniorities) or 'any'}",
        f"Must-have skills: {', '.join(profile.skills_must) or 'not stated'}",
        f"Nice-to-have skills: {', '.join(profile.skills_nice) or 'not stated'}",
        f"Locations: {', '.join([*profile.cities, *countries]) or 'any'}",
        f"Work setups: {', '.join(w.value for w in profile.work_setups)}",
        f"What they want next: {profile.expectations.strip() or 'not stated'}",
    ]
    return "Candidate profile:\n" + "\n".join(lines)


def job_facts(job: Mapping[str, Any]) -> str:
    keys = ["title", "company_name", "domain", "subdomain", "seniority", "yoe_min", "yoe_max",
            "work_setup", "eligible_countries", "office_cities", "skills_required",
            "skills_preferred", "responsibilities", "ai_summary", "salary_min", "salary_max",
            "salary_currency", "salary_period"]  # fmt: skip
    return json.dumps({k: job.get(k) for k in keys if job.get(k) not in (None, [], "")})


def request_params(profile: Profile, job: Mapping[str, Any], model: str) -> dict[str, Any]:
    return {
        "model": model,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "thinking": {"type": "disabled"},
        "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": FIT_SCHEMA}},
        "system": [
            {"type": "text", "text": RUBRIC},
            {
                "type": "text",
                "text": profile_block(profile),
                "cache_control": {"type": "ephemeral"},
            },
        ],
        "messages": [{"role": "user", "content": f"Job facts:\n{job_facts(job)}"}],
    }


def candidates(engine: Engine, profile: Profile, now: datetime, limit: int) -> list[dict[str, Any]]:
    """Enriched, untriaged, recent jobs that pass the filters and lack a score for this profile."""
    scored = select(scores.c.job_id).where(scores.c.profile_version == profile.version)
    with engine.connect() as conn:
        rows = conn.execute(
            select(jobs, tracker.c.status)
            .select_from(jobs.outerjoin(tracker, tracker.c.job_id == jobs.c.job_id))
            .where(
                jobs.c.closed_at.is_(None),
                jobs.c.domain.is_not(None),
                jobs.c.first_seen_at >= now - SCORE_WINDOW,
                jobs.c.job_id.not_in(scored),
            )
            .order_by(jobs.c.first_seen_at.desc())
        ).mappings()
        picked = []
        for row in rows:
            job = dict(row)
            if job["status"] in (None, "new", "seen") and exclusion_reason(job, profile) is None:
                picked.append(job)
            if len(picked) >= limit:
                break
    return picked


async def score_pending(
    engine: Engine, profile: Profile, settings: Settings, now: datetime, *, limit: int = 400
) -> dict[str, Any]:
    if settings.anthropic_api_key is None:
        return {"scored": 0, "reason": "no ANTHROPIC_API_KEY"}
    with engine.connect() as conn:
        remaining = settings.ai_fit_monthly_budget_usd - month_spend(conn, now, kind=KIND)
    affordable = max(0, int(remaining / EST_COST_PER_JOB))
    todo = candidates(engine, profile, now, min(limit, affordable))
    if not todo:
        return {"scored": 0, "reason": "nothing to score" if affordable else "budget reached"}
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value())
    usage = Usage()
    semaphore = asyncio.Semaphore(settings.ai_concurrency)
    done = 0

    async def one(job: dict[str, Any]) -> None:
        nonlocal done
        async with semaphore:
            try:
                message = await client.messages.create(
                    **request_params(profile, job, settings.ai_model)
                )
            except anthropic.APIError as exc:
                log.warning("fit.request_failed", job_id=job["job_id"], error=str(exc)[:200])
                return
        usage.add(message.usage)
        text = next((b.text for b in message.content if b.type == "text"), "")
        try:
            result = FitResult.model_validate(json.loads(text))
        except (ValueError, ValidationError):
            log.warning("fit.parse_failed", job_id=job["job_id"])
            return
        with engine.begin() as conn:
            conn.execute(
                scores.insert().values(
                    job_id=job["job_id"],
                    profile_version=profile.version,
                    fit=result.fit,
                    reason=result.reason[:400],
                    matched=result.matched_skills[:12],
                    missing=result.missing_skills[:12],
                    model=settings.ai_model,
                    scored_at=now,
                )
            )
        done += 1

    try:
        await one(todo[0])  # warm the cached profile prompt
        await asyncio.gather(*(one(job) for job in todo[1:]))
    finally:
        await client.close()
    with engine.begin() as conn:
        cost = record_usage(conn, usage, now=now, kind=KIND, mode="direct", model=settings.ai_model)
    log.info("fit.scored", scored=done, cost_usd=round(cost, 4))
    return {"scored": done, "cost_usd": round(cost, 4)}


def fit_lookup(engine: Engine, profile: Profile) -> dict[str, dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            select(scores).where(scores.c.profile_version == profile.version)
        ).mappings()
        return {r["job_id"]: dict(r) for r in rows}
