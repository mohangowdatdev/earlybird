"""Loads the company registry (registry/companies.yaml)."""

from pathlib import Path

import yaml
from pydantic import TypeAdapter

from earlybird.core.models import Company

_companies = TypeAdapter(list[Company])


def load_registry(path: Path, *, include_excluded: bool = False) -> list[Company]:
    data = yaml.safe_load(path.read_text()) or {}
    companies = _companies.validate_python(data.get("companies") or [])
    return companies if include_excluded else [c for c in companies if not c.excluded]
