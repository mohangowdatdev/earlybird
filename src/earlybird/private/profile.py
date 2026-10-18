"""The personal profile: everything that makes filtering and scoring *yours*. Lives in profile.yaml
(gitignored). Edited through the portal's profile builder or by hand; validated here either way.
"""

import hashlib
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from earlybird.core.geo import canonical_city, country_code
from earlybird.core.models import IN_SCOPE_DOMAINS, Domain, Seniority, WorkSetup

MAX_DOMAINS = 2

DEFAULT_EXCLUDES = [
    "intern",
    "internship",
    "new grad",
    "graduate program",
    "sales",
    "account executive",
    "recruiter",
    "talent acquisition",
    "legal counsel",
]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(v for v in values if v))


class Profile(BaseModel):
    name: str = ""
    yoe: int = Field(default=5, ge=0, le=50)
    domains: list[Domain] = Field(
        default_factory=list, description="Up to 2 of data, ai, cybersecurity; empty = all three"
    )
    seniorities: list[Seniority] = Field(
        default_factory=list, description="Levels you want; empty means any"
    )
    countries: list[str] = Field(default_factory=list, description="ISO codes, e.g. IN")
    cities: list[str] = Field(default_factory=list, description="Canonical city names")
    work_setups: list[WorkSetup] = Field(
        default_factory=lambda: [WorkSetup.REMOTE, WorkSetup.HYBRID, WorkSetup.ONSITE]
    )
    languages: list[str] = Field(default_factory=lambda: ["English"])
    role_families: list[str] = Field(default_factory=list)
    skills_must: list[str] = Field(default_factory=list)
    skills_nice: list[str] = Field(default_factory=list)
    expectations: str = Field(default="", max_length=1500)
    exclude_title_patterns: list[str] = Field(default_factory=lambda: list(DEFAULT_EXCLUDES))
    watchlist: list[str] = Field(default_factory=list, description="Dream companies: slugs")
    min_salary_usd: int | None = Field(default=None, ge=0)
    chirp_daily_cap: int = Field(default=5, ge=0, le=50)

    @field_validator("domains")
    @classmethod
    def _in_scope(cls, values: list[Domain]) -> list[Domain]:
        chosen = [d for d in dict.fromkeys(values) if d in IN_SCOPE_DOMAINS]
        if len(chosen) > MAX_DOMAINS:
            raise ValueError(f"pick at most {MAX_DOMAINS} of data, ai, cybersecurity")
        return chosen

    @field_validator("countries")
    @classmethod
    def _countries(cls, values: list[str]) -> list[str]:
        return _dedupe([country_code(v) or "" for v in values])

    @field_validator("cities")
    @classmethod
    def _cities(cls, values: list[str]) -> list[str]:
        return _dedupe([canonical_city(v)[0] for v in values if v.strip()])

    @field_validator("languages")
    @classmethod
    def _languages(cls, values: list[str]) -> list[str]:
        return _dedupe([v.strip().title() for v in values]) or ["English"]

    @field_validator("role_families", "skills_must", "skills_nice", "exclude_title_patterns",
                     "watchlist")  # fmt: skip
    @classmethod
    def _clean_list(cls, values: list[str]) -> list[str]:
        return _dedupe([" ".join(v.strip().lower().split()) for v in values])

    @property
    def version(self) -> str:
        """Changes whenever anything that affects filtering or scoring changes."""
        return hashlib.sha1(self.model_dump_json().encode()).hexdigest()[:10]  # noqa: S324

    @property
    def scope(self) -> list[Domain]:
        return self.domains or list(IN_SCOPE_DOMAINS)

    @property
    def remote_countries(self) -> set[str]:
        """Countries you can work remotely from: chosen countries plus your cities' countries."""
        from_cities = {canonical_city(c)[1] for c in self.cities}
        return set(self.countries) | {c for c in from_cities if c}


def load_profile(path: Path) -> Profile | None:
    if not path.exists():
        return None
    return Profile.model_validate(yaml.safe_load(path.read_text()) or {})


def save_profile(profile: Profile, path: Path) -> None:
    data = profile.model_dump(mode="json")
    header = "# Earlybird profile. Personal: never commit (gitignored). Edit in the portal.\n"
    path.write_text(header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
