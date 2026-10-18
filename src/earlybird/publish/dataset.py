"""Builds the public dataset: state.db.gz, jobs.json, health.json, checksums.txt (ADR 0009).

The guard refuses to publish if the state contains anything that must stay private:
descriptions, private-visibility rows, or tracker/app data.
"""

import gzip
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, func, select

from earlybird.db.schema import app_state, jobs, scores, tracker
from earlybird.health.report import HealthReport

# The only job fields that may appear on the public board. Changing this needs a privacy review.
PUBLIC_JOB_FIELDS: tuple[str, ...] = (
    "job_id",
    "canonical_key",
    "source",
    "company_name",
    "company_slug",
    "title",
    "url",
    "locations",
    "remote_type",
    "yoe_min",
    "yoe_max",
    "seniority",
    "stack",
    "salary_min",
    "salary_max",
    "salary_currency",
    "salary_period",
    "summary",
    "first_seen_at",
    "posted_at",
    "domain",
    "subdomain",
    "work_setup",
    "eligible_countries",
    "eligible_regions",
    "office_cities",
    "required_languages",
    "visa_sponsorship",
    "skills_required",
    "skills_preferred",
    "ai_summary",
)


class PrivacyViolationError(RuntimeError):
    """The state contains data that must never be published."""


def assert_publishable(engine: Engine) -> None:
    with engine.connect() as conn:
        checks = {
            "description_text present": select(func.count()).where(
                jobs.c.description_text.is_not(None)
            ),
            "private-visibility jobs present": select(func.count()).where(
                jobs.c.visibility != "public"
            ),
            "tracker rows present": select(func.count()).select_from(tracker),
            "app_state rows present": select(func.count()).select_from(app_state),
            "personal fit scores present": select(func.count()).select_from(scores),
        }
        for problem, query in checks.items():
            if conn.execute(query).scalar_one():
                raise PrivacyViolationError(problem)


def _jsonable(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def public_jobs(engine: Engine) -> list[dict[str, Any]]:
    columns = [jobs.c[name] for name in PUBLIC_JOB_FIELDS]
    with engine.connect() as conn:
        rows = conn.execute(
            select(*columns)
            .where(jobs.c.closed_at.is_(None), jobs.c.visibility == "public")
            .order_by(jobs.c.first_seen_at.desc(), jobs.c.job_id)
        ).mappings()
        return [{k: _jsonable(v) for k, v in row.items()} for row in rows]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_dataset(
    engine: Engine, sqlite_path: Path, out_dir: Path, report: HealthReport, now: datetime
) -> list[Path]:
    """Write all assets into `out_dir` and return their paths."""
    assert_publishable(engine)
    out_dir.mkdir(parents=True, exist_ok=True)

    jobs_path = out_dir / "jobs.json"
    listed = public_jobs(engine)
    jobs_path.write_text(
        json.dumps(
            {"generated_at": now.isoformat(), "count": len(listed), "jobs": listed},
            separators=(",", ":"),
        )
    )
    health_path = out_dir / "health.json"
    health_path.write_text(report.model_dump_json(indent=2))

    # A compact, consistent copy of the live DB (VACUUM INTO also drops WAL state).
    snapshot = out_dir / "state.db"
    snapshot.unlink(missing_ok=True)
    with sqlite3.connect(sqlite_path) as source:
        source.execute("VACUUM INTO ?", (str(snapshot),))
    state_path = out_dir / "state.db.gz"
    with snapshot.open("rb") as raw, gzip.open(state_path, "wb", compresslevel=9) as packed:
        shutil.copyfileobj(raw, packed)
    snapshot.unlink()

    assets = [state_path, jobs_path, health_path]
    checksums = out_dir / "checksums.txt"
    checksums.write_text("".join(f"{_sha256(p)}  {p.name}\n" for p in assets))
    return [*assets, checksums]
