"""Small-LLM extraction for what rules can't settle (remote eligibility, YOE, stack, seniority).

Runs a tiny open model through Ollama (free, local or on the Actions runner). Rules run first;
only uncertain tech roles reach the model, and its answer can only fill gaps or widen what the
rules found (fail-open). Strict JSON schema output, validated with pydantic; any failure keeps
the rule result.
"""

import re
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, Field, ValidationError, field_validator

from earlybird.core.models import Job, RemoteType, Seniority
from earlybird.enrich.models import ExtractionMethod, Facts
from earlybird.enrich.rules import canonical_skill, stack_tags, summarize

log = structlog.get_logger()

# qwen2.5:1.5b was benchmarked and rejected: it labelled US/EU-only roles "India OK".
DEFAULT_MODEL = "qwen2.5:3b"

MAX_DESCRIPTION_CHARS = 3000
MAX_YOE = 25
_KEEP_LINE = re.compile(
    r"remote|hybrid|on-?site|office|locat|based|reside|relocat|countr|region|time ?zone|"
    r"eligib|authori[sz]|visa|citizen|years?|experience|qualif|require|skills?|stack|"
    r"proficien|familiar|india|apac|emea|united states|\bu\.s\.|europe|anywhere|worldwide",
    re.IGNORECASE,
)
_TECH_TITLE = re.compile(
    r"engineer|developer|data|scien|analyst|architect|\bml\b|\bai\b|machine learning|devops|"
    r"\bsre\b|platform|analytics|infrastructure|software|backend|cloud|mlops|research",
    re.IGNORECASE,
)

_DATA_TITLE = re.compile(
    r"\bdata\b|\bml\b|\bai\b|machine learning|analytics|scien|\bllm|mlops", re.IGNORECASE
)

SYSTEM_PROMPT = """You extract facts from a job posting. Reply with JSON only, matching the schema.
Use only what the posting states. If something is not stated, use null, [] or "unknown".

remote_type:
- "remote_india_ok": remote, and people in India may apply (India, APAC/Asia, or anywhere/worldwide)
- "remote_restricted": remote, but only from regions that exclude India (e.g. US-only, Europe-only,
  "must be authorized to work in the US", "must live in Canada")
- "remote_unspecified": remote, but the posting never says where people must be
- "hybrid": part-time in an office
- "onsite": fully in an office
- "unknown": the posting does not say
eligible_regions: countries/regions people may work from (e.g. ["India"], ["United States"]).
office_locations: office cities for this role.
yoe_min / yoe_max: required years of professional experience, as integers.
seniority: one of intern, junior, mid, senior, staff_plus, lead_manager, executive, unknown.
skills: technical skills and tools the role asks for, short names (max 15)."""


class LLMFacts(BaseModel):
    remote_type: RemoteType = RemoteType.UNKNOWN
    eligible_regions: list[str] = Field(default_factory=list, max_length=20)
    office_locations: list[str] = Field(default_factory=list, max_length=20)
    yoe_min: int | None = Field(default=None, ge=0, le=30)
    yoe_max: int | None = Field(default=None, ge=0, le=40)
    seniority: Seniority = Seniority.UNKNOWN
    skills: list[str] = Field(default_factory=list, max_length=40)

    @field_validator("yoe_max")
    @classmethod
    def _max_not_below_min(cls, value: int | None, info: Any) -> int | None:
        low = info.data.get("yoe_min")
        return None if value is not None and low is not None and value < low else value


def is_candidate(job: Job, facts: Facts) -> bool:
    """Worth a model call: a tech-ish role whose key facts the rules couldn't settle."""
    if not job.description_text or not _TECH_TITLE.search(job.title):
        return False
    ambiguous_remote = facts.remote_type in (RemoteType.UNKNOWN, RemoteType.REMOTE_UNSPECIFIED)
    data_role = bool(_DATA_TITLE.search(job.title))
    return ambiguous_remote or (data_role and (facts.yoe_min is None or not facts.stack))


def priority(facts: Facts) -> int:
    """Lower runs first: unclear remote eligibility matters most, then experience, then stack."""
    if facts.remote_type in (RemoteType.UNKNOWN, RemoteType.REMOTE_UNSPECIFIED):
        return 0
    return 1 if facts.yoe_min is None else 2


def trim_description(text: str, limit: int = MAX_DESCRIPTION_CHARS) -> str:
    """The opening plus every line about location, eligibility, experience or skills."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    head = " ".join(lines[:3])[:500]
    relevant = [ln for ln in lines[3:] if _KEEP_LINE.search(ln)]
    return (head + "\n" + "\n".join(relevant))[:limit]


def evidence_text(job: Job) -> str:
    """Everything the model was shown: claims are checked against this."""
    return " | ".join([job.title, *job.locations, job.remote_raw or "", job.description_text or ""])


def build_prompt(job: Job) -> str:
    return (
        f"Title: {job.title}\nCompany: {job.company_name}\n"
        f"Location field: {', '.join(job.locations) or 'not given'}\n"
        f"Remote field: {job.remote_raw or 'not given'}\n\n"
        f"Posting:\n{trim_description(job.description_text or '')}"
    )


_UPGRADES = {
    RemoteType.UNKNOWN: set(RemoteType) - {RemoteType.UNKNOWN},
    RemoteType.REMOTE_UNSPECIFIED: {RemoteType.REMOTE_INDIA_OK, RemoteType.REMOTE_RESTRICTED},
    RemoteType.ONSITE: {
        RemoteType.HYBRID,
        RemoteType.REMOTE_INDIA_OK,
        RemoteType.REMOTE_UNSPECIFIED,
    },
    RemoteType.REMOTE_RESTRICTED: {RemoteType.REMOTE_INDIA_OK},
    RemoteType.HYBRID: {RemoteType.REMOTE_INDIA_OK},
}


_INDIA_EVIDENCE = re.compile(
    r"\b(india|bangalore|bengaluru|hyderabad|pune|chennai|mumbai|gurgaon|gurugram|noida|delhi|"
    r"apac|asia|anywhere|worldwide|globally|global)\b",
    re.IGNORECASE,
)
_REMOTE_EVIDENCE = re.compile(r"\bremote|work from home|distributed team", re.IGNORECASE)
_HYBRID_EVIDENCE = re.compile(r"\bhybrid\b|days? (?:a|per) week in", re.IGNORECASE)


def _grounded_remote(value: RemoteType, text: str) -> bool:
    """Small models hallucinate: accept a remote claim only if the text supports it."""
    if value is RemoteType.REMOTE_INDIA_OK:
        return bool(_INDIA_EVIDENCE.search(text) and _REMOTE_EVIDENCE.search(text))
    if value in (RemoteType.REMOTE_RESTRICTED, RemoteType.REMOTE_UNSPECIFIED):
        return bool(_REMOTE_EVIDENCE.search(text))
    if value is RemoteType.HYBRID:
        return bool(_HYBRID_EVIDENCE.search(text))
    return True


def _grounded_years(value: int | None, text: str) -> bool:
    return value is not None and bool(
        re.search(rf"\b{value}\s*\+?\s*(?:-|–|to|\+)?\s*\d*\s*\+?\s*(?:years?|yrs?)", text, re.I)
    )


def merge(rules: Facts, llm: LLMFacts, evidence: str) -> Facts:
    """Fill gaps and widen (fail-open), never narrow, and only with claims the text supports."""
    remote = None
    if llm.remote_type in _UPGRADES.get(rules.remote_type, set()) and _grounded_remote(
        llm.remote_type, evidence
    ):
        remote = llm.remote_type
    remote_type = remote or rules.remote_type
    yoe = (rules.yoe_min, rules.yoe_max)
    if rules.yoe_min is None and _grounded_years(llm.yoe_min, evidence):
        high = llm.yoe_max if llm.yoe_max is not None and llm.yoe_max <= MAX_YOE else None
        yoe = (llm.yoe_min, high)
    seniority = rules.seniority if rules.seniority is not Seniority.UNKNOWN else llm.seniority
    known = set(stack_tags())
    lowered = evidence.lower()
    extra = [canonical_skill(s) for s in llm.skills if s.lower() in lowered]
    stack = list(dict.fromkeys([*rules.stack, *(s for s in extra if s in known)]))[:20]
    return Facts(
        remote_type=remote_type,
        yoe_min=yoe[0],
        yoe_max=yoe[1],
        seniority=seniority,
        stack=stack,
        summary=summarize(seniority, remote_type, yoe, stack),
        method=ExtractionMethod.MIXED,
    )


class OllamaExtractor:
    """Calls a local Ollama server with a JSON-schema-constrained chat request."""

    def __init__(self, base_url: str, model: str, *, timeout: float = 120.0) -> None:
        self.model = model
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)
        self._schema = LLMFacts.model_json_schema()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def available(self) -> bool:
        try:
            response = await self._client.get("/api/tags")
        except httpx.HTTPError:
            return False
        names = {m.get("name", "") for m in response.json().get("models", [])}
        return response.is_success and any(n.split(":latest")[0] == self.model for n in names)

    async def extract(self, job: Job) -> LLMFacts | None:
        payload = {
            "model": self.model,
            "stream": False,
            "format": self._schema,
            "options": {"temperature": 0, "num_ctx": 4096},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_prompt(job)},
            ],
        }
        try:
            response = await self._client.post("/api/chat", json=payload)
            response.raise_for_status()
            return LLMFacts.model_validate_json(response.json()["message"]["content"])
        except (httpx.HTTPError, KeyError, ValidationError, ValueError) as exc:
            log.warning("llm.extract_failed", job_id=job.job_id, error=str(exc)[:200])
            return None
