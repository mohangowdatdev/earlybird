"""`make sync`: pull the public dataset from the data-latest Release into the local DB.

Public rows are upserted; local-only data (descriptions, private email jobs, tracker) is untouched.
"""

import gzip
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import Engine, bindparam, delete, select

from earlybird.core.errors import EarlybirdError
from earlybird.core.http import HttpClient
from earlybird.db.engine import make_engine, upgrade
from earlybird.db.schema import adapter_runs, app_state, company_status, jobs

log = structlog.get_logger()

ASSETS = ("checksums.txt", "state.db.gz", "health.json")
_LOCAL_ONLY_COLUMNS = frozenset({"description_text"})
_CHUNK = 500


class SyncError(EarlybirdError):
    """The dataset could not be downloaded or failed verification."""


def release_url(repo: str, tag: str, asset: str) -> str:
    return f"https://github.com/{repo}/releases/download/{tag}/{asset}"


async def download(repo: str, tag: str, cache_dir: Path, *, timeout: float) -> Path:
    """Download and checksum-verify the assets; returns the decompressed state DB path."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    async with HttpClient(timeout=timeout, concurrency=2) as http:
        for asset in ASSETS:
            response = await http.request("GET", release_url(repo, tag, asset))
            (cache_dir / asset).write_bytes(response.content)
    for line in (cache_dir / "checksums.txt").read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        if name in ASSETS and hashlib.sha256((cache_dir / name).read_bytes()).hexdigest() != digest:
            raise SyncError(f"checksum mismatch for {name}")
    state = cache_dir / "state.db"
    state.write_bytes(gzip.decompress((cache_dir / "state.db.gz").read_bytes()))
    return state


def _upsert_jobs(local: Engine, rows: list[dict[str, Any]]) -> int:
    ids = [r["job_id"] for r in rows]
    with local.begin() as conn:
        existing = set(conn.execute(select(jobs.c.job_id).where(jobs.c.job_id.in_(ids))).scalars())
        new = [r for r in rows if r["job_id"] not in existing]
        updates = [
            {f"b_{k}": v for k, v in r.items() if k not in _LOCAL_ONLY_COLUMNS}
            for r in rows
            if r["job_id"] in existing
        ]
        if new:
            conn.execute(jobs.insert(), new)
        if updates:
            columns = [k.removeprefix("b_") for k in updates[0] if k != "b_job_id"]
            conn.execute(
                jobs.update()
                .where(jobs.c.job_id == bindparam("b_job_id"))
                .values({c: bindparam(f"b_{c}") for c in columns}),
                updates,
            )
    return len(new)


def merge_state(state_path: Path, local: Engine, now: datetime) -> int:
    """Merge the public state into the local DB. Returns the number of new jobs."""
    state = make_engine(f"sqlite:///{state_path}")
    upgrade(f"sqlite:///{state_path}")  # tolerate an older snapshot schema
    new_total = 0
    try:
        with state.connect() as src:
            result = src.execute(select(jobs).where(jobs.c.visibility == "public"))
            while chunk := result.mappings().fetchmany(_CHUNK):
                rows = [{**r, "description_text": None} for r in chunk]
                new_total += _upsert_jobs(local, rows)
            runs = [
                {k: v for k, v in r.items() if k != "id"}
                for r in src.execute(select(adapter_runs)).mappings()
            ]
            statuses = [dict(r) for r in src.execute(select(company_status)).mappings()]
        public_sources = {r["source"] for r in runs}
        with local.begin() as conn:
            # Replace public runs only; private-plane boards keep their local run history.
            conn.execute(delete(adapter_runs).where(adapter_runs.c.source.in_(public_sources)))
            conn.execute(delete(company_status))
            if runs:
                conn.execute(adapter_runs.insert(), runs)
            if statuses:
                conn.execute(company_status.insert(), statuses)
            set_state(conn, "last_sync_at", now.isoformat())
    finally:
        state.dispose()
    return new_total


def set_state(conn: Any, key: str, value: str) -> None:
    updated = conn.execute(app_state.update().where(app_state.c.key == key).values(value=value))
    if updated.rowcount == 0:
        conn.execute(app_state.insert().values(key=key, value=value))


def get_state(conn: Any, key: str) -> str | None:
    value: str | None = conn.execute(
        select(app_state.c.value).where(app_state.c.key == key)
    ).scalar_one_or_none()
    return value


async def sync(
    local: Engine, *, repo: str, tag: str, cache_dir: Path, timeout: float, now: datetime
) -> int:
    state_path = await download(repo, tag, cache_dir, timeout=timeout)
    new = merge_state(state_path, local, now)
    log.info("sync.done", new_jobs=new, repo=repo, tag=tag)
    return new
