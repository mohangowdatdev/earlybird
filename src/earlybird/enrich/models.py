"""Generic, public-safe facts derived from a Job (true for every reader)."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from earlybird.core.models import RemoteType, Seniority


class ExtractionMethod(StrEnum):
    RULES = "rules"
    AI = "ai"
    MIXED = "mixed"


class Facts(BaseModel):
    model_config = ConfigDict(frozen=True)

    remote_type: RemoteType
    yoe_min: int | None = None
    yoe_max: int | None = None
    seniority: Seniority = Seniority.UNKNOWN
    stack: list[str] = Field(default_factory=list)
    summary: str
    method: ExtractionMethod = ExtractionMethod.RULES
