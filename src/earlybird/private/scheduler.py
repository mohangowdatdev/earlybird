"""Background loop run by `make up`: sync the public dataset, then fetch private-only boards."""

import asyncio
from datetime import UTC, datetime

import structlog

from earlybird.core.config import Settings
from earlybird.core.errors import EarlybirdError
from earlybird.core.models import Visibility
from earlybird.db.engine import make_engine, upgrade
from earlybird.ingest import run as ingest
from earlybird.private.sync import sync

log = structlog.get_logger()


async def run_forever(settings: Settings) -> None:
    upgrade(settings.db_url)
    engine = make_engine(settings.db_url)
    while True:
        try:
            await sync(
                engine,
                repo=settings.dataset_repo,
                tag=settings.dataset_tag,
                cache_dir=settings.data_dir / "cache",
                timeout=settings.http_timeout_seconds,
                now=datetime.now(UTC),
            )
        except EarlybirdError as exc:
            log.warning("scheduler.sync_failed", error=str(exc))
        await ingest(
            engine,
            [],
            sources=None,
            now_fn=lambda: datetime.now(UTC),
            timeout=settings.http_timeout_seconds,
            concurrency=4,
            visibility=Visibility.PRIVATE,
        )
        await asyncio.sleep(settings.sync_interval_minutes * 60)
