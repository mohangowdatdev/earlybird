"""The normalized models every part of Earlybird speaks. Adapters emit `Job`; nothing else."""

import hashlib
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class RemoteType(StrEnum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE_INDIA_OK = "remote_india_ok"
    REMOTE_RESTRICTED = "remote_restricted"
    REMOTE_UNSPECIFIED = "remote_unspecified"
    UNKNOWN = "unknown"


class Seniority(StrEnum):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF_PRINCIPAL = "staff_principal"
    LEAD_MANAGER = "lead_manager"
    DIRECTOR = "director"
    HEAD_PLUS = "head_plus"
    UNKNOWN = "unknown"


class Domain(StrEnum):
    """Earlybird's scope: only these three spaces (ADR 0018). Everything else is `other`."""

    DATA = "data"
    AI = "ai"
    CYBERSECURITY = "cybersecurity"
    OTHER = "other"


IN_SCOPE_DOMAINS: tuple[Domain, ...] = (Domain.DATA, Domain.AI, Domain.CYBERSECURITY)


class WorkSetup(StrEnum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class Visibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"


class AtsRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: str
    id: str
    options: dict[str, Any] = Field(default_factory=dict)


class Company(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    name: str
    ats: list[AtsRef]
    tags: list[str] = Field(default_factory=list)
    discovered_by: str | None = None
    added_at: str | None = None
    excluded: bool = False
    excluded_reason: str | None = None


class Job(BaseModel):
    """One posting as a source describes it, lightly cleaned. Facts are derived later."""

    model_config = ConfigDict(frozen=True)

    source: str
    external_id: str
    company_slug: str
    company_name: str
    title: str
    url: HttpUrl
    locations: list[str] = Field(default_factory=list)
    remote_raw: str | None = None
    department: str | None = None
    employment_type: str | None = None
    posted_at: datetime | None = None
    description_text: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None

    @property
    def job_id(self) -> str:
        return hashlib.sha1(f"{self.source}:{self.external_id}".encode()).hexdigest()[:16]  # noqa: S324
