"""The personal profile: everything that makes scoring *yours*. Lives in profile.yaml (gitignored).

Edited through the portal's profile builder or by hand; validated here either way.
"""

import hashlib
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from earlybird.core.models import RemoteType, Seniority

DEFAULT_EXCLUDES = [
    "intern",
    "internship",
    "new grad",
    "graduate program",
    "director",
    "vice president",
    "vp",
    "head of",
    "chief",
    "sales",
    "account executive",
    "recruiter",
    "talent acquisition",
    "legal counsel",
]


class Profile(BaseModel):
    name: str = ""
    yoe: int = Field(default=5, ge=0, le=50)
    role_families: list[str] = Field(default_factory=list)
    skills_must: list[str] = Field(default_factory=list)
    skills_nice: list[str] = Field(default_factory=list)
    remote_types: list[RemoteType] = Field(
        default_factory=lambda: [
            RemoteType.REMOTE_INDIA_OK,
            RemoteType.REMOTE_UNSPECIFIED,
            RemoteType.UNKNOWN,
        ]
    )
    cities: list[str] = Field(
        default_factory=list, description="Cities where hybrid/onsite roles are acceptable"
    )
    seniorities: list[Seniority] = Field(
        default_factory=list, description="Preferred levels; empty means any"
    )
    exclude_title_patterns: list[str] = Field(default_factory=lambda: list(DEFAULT_EXCLUDES))
    watchlist: list[str] = Field(default_factory=list, description="Perch: company slugs")
    min_salary_usd: int | None = Field(default=None, ge=0)
    chirp_daily_cap: int = Field(default=5, ge=0, le=50)

    @field_validator(
        "role_families", "skills_must", "skills_nice", "cities", "exclude_title_patterns",
        "watchlist",
    )  # fmt: skip
    @classmethod
    def _clean_list(cls, values: list[str]) -> list[str]:
        seen: dict[str, None] = {}
        for value in values:
            cleaned = " ".join(value.strip().lower().split())
            if cleaned:
                seen.setdefault(cleaned, None)
        return list(seen)

    @property
    def version(self) -> str:
        """Changes whenever anything that affects scoring changes."""
        return hashlib.sha1(self.model_dump_json().encode()).hexdigest()[:10]  # noqa: S324


def load_profile(path: Path) -> Profile | None:
    if not path.exists():
        return None
    return Profile.model_validate(yaml.safe_load(path.read_text()) or {})


def save_profile(profile: Profile, path: Path) -> None:
    data = profile.model_dump(mode="json")
    header = "# Earlybird profile. Personal: never commit (gitignored). Edit in the portal.\n"
    path.write_text(header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
