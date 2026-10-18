"""AI enrichment: Claude Haiku reads each posting into one unified, filterable schema (ADR 0017).

Generic facts only (what the job *is*), never anything personal, so it runs on the public plane.
Strict JSON-schema output, validated again with pydantic. Bulk work goes through the Batch API
(half price); small increments use direct calls. Spend is metered and capped per month.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from earlybird.core.geo import COUNTRIES, REGIONS, canonical_city
from earlybird.core.models import Domain, Job, RemoteType, Seniority, WorkSetup
from earlybird.enrich.models import ExtractionMethod, Facts
from earlybird.enrich.rules import canonical_skill, stack_tags, summarize

# Bump when the prompt or schema changes: every job is re-enriched on its next fetch.
AI_VERSION = 1
DEFAULT_MODEL = "claude-haiku-5-5"
MAX_DESCRIPTION_CHARS = 16_000
MAX_OUTPUT_TOKENS = 1_500

# USD per million tokens (Claude Haiku 5.5, prompts <=100K). Batch API halves everything.
PRICES = {"input": 0.10, "output": 0.50, "cache_read": 0.01, "cache_write": 0.125}
BATCH_DISCOUNT = 0.5
EST_OUTPUT_TOKENS = 450
EST_SYSTEM_TOKENS = 1_700
JUNIOR_BELOW, SENIOR_FROM = 2, 5

_OUT_OF_SCOPE_TITLE = re.compile(
    r"\b(account executive|account manager|sales|business development|\bsdr\b|\bbdr\b|"
    r"development representative|renewals|"
    r"recruit\w*|talent acquisition|sourcer|legal|counsel|attorney|paralegal|lawyer|"
    r"marketing|brand|communications|public relations|content writer|copywriter|"
    r"event|payroll|accountant|accounting|tax\b|procurement|office manager|"
    r"executive assistant|facilities|chef|cook|barista|receptionist|hr business partner|"
    r"people partner|customer success|customer support|support specialist)\b",
    re.IGNORECASE,
)


def obviously_out_of_scope(title: str) -> bool:
    """Cheap, conservative pre-filter: clearly non-technical titles skip the model."""
    return bool(_OUT_OF_SCOPE_TITLE.search(title)) and not re.search(
        r"\b(data|ai|ml|security|analytics) (engineer|scientist|analyst)", title, re.I
    )


SYSTEM_PROMPT = """You read job postings and extract facts into a fixed JSON schema. Use only what \
the posting says or clearly implies; when something is not stated, use null, [] or "unknown". \
Never guess locations, years or languages.

domain - the space this job belongs to:
- "data": data engineering, analytics engineering, data platform/infrastructure, data analysis, \
BI, data science focused on analytics, data governance/quality, database engineering
- "ai": machine learning engineering, applied/research science in ML, LLM/GenAI engineering, \
MLOps/ML platform, NLP, computer vision, AI product engineering
- "cybersecurity": security engineering, AppSec, cloud/network/infrastructure security, SOC, \
detection & response, threat intel, IAM, GRC, offensive security, privacy engineering
- "other": everything else (general software/full-stack/frontend/mobile/backend roles without a \
data, AI or security focus, sales, marketing, recruiting, legal, finance, ops, design, support)
Classify by the work the person will do, not by the company's product: a backend engineer at an \
AI or database company is "other"; a security engineer at a data company is "cybersecurity". \
SRE, DevOps, platform, infrastructure and networking roles are "other" unless the work is mainly \
security, data platforms or ML platforms.
subdomain: a short label such as "data engineering", "analytics engineering", "ml engineering", \
"llm engineering", "mlops", "appsec", "cloud security", "detection & response".

seniority - map the level the posting asks for:
intern | junior (0-2 yrs, associate) | mid (2-5 yrs) | senior (5+ yrs, "Senior") | \
staff_principal (Staff, Principal, Architect) | lead_manager (Lead, Engineering/Team Manager) | \
director (Director, Senior Director) | head_plus (Head of, VP, Chief, CTO/CISO) | unknown.
If the title has no level, infer it from the required years: under 2 junior, 2-4 mid, 5 or more \
senior. Use unknown only when neither the title nor the years say anything.

work_setup: "remote", "hybrid", "onsite" or "unknown". Trust the description over the location \
field when they disagree (e.g. field says "Hybrid" but the text says "this role is based in Dubai").
If remote is offered for any listed location, use "remote" (and list where). If only office \
cities are given and nothing mentions remote or hybrid, use "onsite".

eligible_countries: ISO 3166-1 alpha-2 codes of the countries where the hire may live and work \
(for onsite/hybrid: the office countries; for remote: the countries named as allowed). \
eligible_regions: only when the posting names a broad area: worldwide, north_america, americas, \
latam, europe, emea, middle_east, africa, apac, asia, oceania. "Remote" with no area named means \
both lists are empty.
office_cities: the cities of the offices this role works from, each with its ISO country code.
required_languages: human languages the job strictly requires besides English (e.g. "Arabic"); \
leave out languages described as a plus, preferred or nice to have.
visa_sponsorship: "yes", "no" or "unknown".
skills_required / skills_preferred: technical skills and tools, short canonical names \
(e.g. "python", "spark", "azure data factory", "terraform"), at most 15 and 10.
responsibilities: up to 5 very short phrases (max 12 words each) in your own words.
salary: only if the posting states numbers.
summary: one sentence of at most 20 words, in your own words."""

_REGION_ENUM = sorted(REGIONS)
_SENIORITY_ENUM = [s.value for s in Seniority]


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [schema, {"type": "null"}]}


def _obj(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


INSIGHT_SCHEMA: dict[str, Any] = _obj(
    {
        "domain": {"type": "string", "enum": [d.value for d in Domain]},
        "subdomain": {"type": "string"},
        "seniority": {"type": "string", "enum": _SENIORITY_ENUM},
        "yoe_min": _nullable({"type": "integer"}),
        "yoe_max": _nullable({"type": "integer"}),
        "work_setup": {"type": "string", "enum": [w.value for w in WorkSetup]},
        "eligible_countries": {"type": "array", "items": {"type": "string"}},
        "eligible_regions": {"type": "array", "items": {"type": "string", "enum": _REGION_ENUM}},
        "office_cities": {
            "type": "array",
            "items": _obj({"city": {"type": "string"}, "country": {"type": "string"}}),
        },
        "required_languages": {"type": "array", "items": {"type": "string"}},
        "visa_sponsorship": {"type": "string", "enum": ["yes", "no", "unknown"]},
        "skills_required": {"type": "array", "items": {"type": "string"}},
        "skills_preferred": {"type": "array", "items": {"type": "string"}},
        "responsibilities": {"type": "array", "items": {"type": "string"}},
        "salary": _nullable(
            _obj(
                {
                    "min": _nullable({"type": "number"}),
                    "max": _nullable({"type": "number"}),
                    "currency": _nullable({"type": "string"}),
                    "period": _nullable(
                        {"type": "string", "enum": ["year", "month", "day", "hour"]}
                    ),
                }
            )
        ),
        "summary": {"type": "string"},
    }
)


class Salary(BaseModel):
    min: float | None = None
    max: float | None = None
    currency: str | None = None
    period: Literal["year", "month", "day", "hour"] | None = None


class OfficeCity(BaseModel):
    city: str
    country: str


class JobInsight(BaseModel):
    """What the model returns, re-validated and normalised."""

    domain: Domain
    subdomain: str = ""
    seniority: Seniority = Seniority.UNKNOWN
    yoe_min: int | None = Field(default=None, ge=0, le=30)
    yoe_max: int | None = Field(default=None, ge=0, le=40)
    work_setup: WorkSetup = WorkSetup.UNKNOWN
    eligible_countries: list[str] = Field(default_factory=list)
    eligible_regions: list[str] = Field(default_factory=list)
    office_cities: list[OfficeCity] = Field(default_factory=list)
    required_languages: list[str] = Field(default_factory=list)
    visa_sponsorship: Literal["yes", "no", "unknown"] = "unknown"
    skills_required: list[str] = Field(default_factory=list)
    skills_preferred: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    salary: Salary | None = None
    summary: str = ""

    @field_validator("eligible_countries")
    @classmethod
    def _known_countries(cls, values: list[str]) -> list[str]:
        return sorted({v.upper() for v in values if v.upper() in COUNTRIES})

    @field_validator("eligible_regions")
    @classmethod
    def _known_regions(cls, values: list[str]) -> list[str]:
        return sorted({v for v in values if v in REGIONS})

    @field_validator("office_cities")
    @classmethod
    def _canonical_cities(cls, values: list[OfficeCity]) -> list[OfficeCity]:
        out: dict[str, OfficeCity] = {}
        for item in values:
            name, country = canonical_city(item.city)
            out[name.lower()] = OfficeCity(city=name, country=(country or item.country).upper())
        return list(out.values())[:15]

    @field_validator("required_languages")
    @classmethod
    def _drop_english(cls, values: list[str]) -> list[str]:
        return sorted({v.strip().title() for v in values if v.strip().lower() != "english"})

    @field_validator("skills_required", "skills_preferred", "responsibilities")
    @classmethod
    def _trim_lists(cls, values: list[str]) -> list[str]:
        return [v.strip()[:80] for v in values if v.strip()][:15]

    @field_validator("yoe_max")
    @classmethod
    def _max_not_below_min(cls, value: int | None, info: Any) -> int | None:
        low = info.data.get("yoe_min")
        return None if value is not None and low is not None and value < low else value


def user_prompt(job: Job) -> str:
    description = (job.description_text or "")[:MAX_DESCRIPTION_CHARS]
    return (
        f"Title: {job.title}\nCompany: {job.company_name}\n"
        f"Location field: {', '.join(job.locations) or 'not given'}\n"
        f"Remote field: {job.remote_raw or 'not given'}\n"
        f"Department: {job.department or 'not given'}\n\n"
        f"Posting:\n{description or '(no description provided)'}"
    )


def request_params(job: Job, model: str) -> dict[str, Any]:
    """Messages API parameters for one posting (shared by direct calls and batches)."""
    return {
        "model": model,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "thinking": {"type": "disabled"},
        "output_config": {
            "effort": "low",
            "format": {"type": "json_schema", "schema": INSIGHT_SCHEMA},
        },
        "system": [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user_prompt(job)}],
    }


def parse_insight(text: str) -> JobInsight | None:
    try:
        return JobInsight.model_validate(json.loads(text))
    except (ValueError, ValidationError):
        return None


@dataclass
class Usage:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def add(self, usage: Any) -> None:
        self.requests += 1
        self.input_tokens += usage.input_tokens or 0
        self.output_tokens += usage.output_tokens or 0
        self.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0

    def cost(self, *, batch: bool) -> float:
        dollars = (
            self.input_tokens * PRICES["input"]
            + self.output_tokens * PRICES["output"]
            + self.cache_read_tokens * PRICES["cache_read"]
            + self.cache_write_tokens * PRICES["cache_write"]
        ) / 1_000_000
        return dollars * (BATCH_DISCOUNT if batch else 1.0)


def estimate_cost(jobs: list[Job], *, batch: bool) -> float:
    """Upper-ish estimate before spending: ~4 chars per token, system uncached."""
    tokens_in = sum(len(user_prompt(j)) / 4 + EST_SYSTEM_TOKENS for j in jobs)
    dollars = tokens_in * PRICES["input"] + len(jobs) * EST_OUTPUT_TOKENS * PRICES["output"]
    return dollars / 1_000_000 * (BATCH_DISCOUNT if batch else 1.0)


# ---------- turning an insight into stored facts ----------

_INDIA_OK_REGIONS = {"worldwide", "apac", "asia"}


def remote_type_from(insight: JobInsight) -> RemoteType:
    """Keep the coarse remote_type column meaningful for older views and the public board."""
    match insight.work_setup:
        case WorkSetup.ONSITE:
            return RemoteType.ONSITE
        case WorkSetup.HYBRID:
            return RemoteType.HYBRID
        case WorkSetup.REMOTE:
            if "IN" in insight.eligible_countries or _INDIA_OK_REGIONS & set(
                insight.eligible_regions
            ):
                return RemoteType.REMOTE_INDIA_OK
            if insight.eligible_countries or insight.eligible_regions:
                return RemoteType.REMOTE_RESTRICTED
            return RemoteType.REMOTE_UNSPECIFIED
        case _:
            return RemoteType.UNKNOWN


@dataclass
class Enrichment:
    facts: Facts
    columns: dict[str, Any] = field(default_factory=dict)


def seniority_from_years(yoe_min: int | None) -> Seniority:
    """Last-resort level when a title has none: years asked for."""
    if yoe_min is None:
        return Seniority.UNKNOWN
    if yoe_min < JUNIOR_BELOW:
        return Seniority.JUNIOR
    return Seniority.MID if yoe_min < SENIOR_FROM else Seniority.SENIOR


def apply_insight(rules: Facts, insight: JobInsight, *, model: str) -> Enrichment:
    """The model's reading wins where it has one; rules fill whatever it left unknown."""
    yoe = (
        (insight.yoe_min, insight.yoe_max)
        if insight.yoe_min is not None
        else (rules.yoe_min, rules.yoe_max)
    )
    seniority = next(
        (s for s in (insight.seniority, rules.seniority, seniority_from_years(yoe[0]))
         if s is not Seniority.UNKNOWN),
        Seniority.UNKNOWN,
    )  # fmt: skip
    remote_type = remote_type_from(insight)
    if remote_type is RemoteType.UNKNOWN:
        remote_type = rules.remote_type
    known = set(stack_tags())
    ai_skills = [canonical_skill(s) for s in [*insight.skills_required, *insight.skills_preferred]]
    stack = list(dict.fromkeys([*(s for s in ai_skills if s in known), *rules.stack]))[:20]
    facts = Facts(
        remote_type=remote_type,
        yoe_min=yoe[0],
        yoe_max=yoe[1],
        seniority=seniority,
        stack=stack,
        summary=summarize(seniority, remote_type, yoe, stack),
        method=ExtractionMethod.AI,
    )
    columns: dict[str, Any] = {
        "domain": insight.domain.value,
        "subdomain": insight.subdomain[:80] or None,
        "work_setup": insight.work_setup.value,
        "eligible_countries": insight.eligible_countries,
        "eligible_regions": insight.eligible_regions,
        "office_cities": [c.model_dump() for c in insight.office_cities],
        "required_languages": insight.required_languages,
        "visa_sponsorship": insight.visa_sponsorship,
        "skills_required": insight.skills_required,
        "skills_preferred": insight.skills_preferred[:10],
        "responsibilities": insight.responsibilities[:5],
        "ai_summary": insight.summary[:300] or None,
        "ai_model": model,
    }
    if insight.salary and (insight.salary.min or insight.salary.max):
        columns |= {
            "salary_min": insight.salary.min,
            "salary_max": insight.salary.max,
            "salary_currency": insight.salary.currency,
            "salary_period": insight.salary.period,
        }
    return Enrichment(facts=facts, columns=columns)


def out_of_scope_columns() -> dict[str, Any]:
    """Columns for a title the pre-filter rules out (no model call, no cost)."""
    return {"domain": Domain.OTHER.value, "subdomain": None, "ai_model": "prefilter"}
