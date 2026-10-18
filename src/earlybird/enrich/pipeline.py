"""The enrichment stage of an ingest run: collect finished batches, then enrich what's new.

Selection: every fetched job whose stored AI reading is missing, from an older AI_VERSION, or for
different content. Newest first, so a tight budget is spent on fresh postings. Obvious non-tech
titles are marked out of scope without a model call. Small sets go direct; bulk goes to the
Batch API (half price, results collected on a later run). Results apply only if the posting is
unchanged since submission. Spend is metered in `ai_usage` and capped per calendar month.
"""

import asyncio
from collections.abc import Iterable
from datetime import datetime
from typing import Any, cast

import anthropic
import structlog
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from sqlalchemy import Connection, Engine, func, select

from earlybird.core.config import Settings
from earlybird.core.models import Job, RemoteType, Seniority
from earlybird.core.normalize import canonical_key, location_bucket
from earlybird.db.schema import ai_batches, ai_usage, jobs
from earlybird.enrich.ai import (
    AI_VERSION,
    Usage,
    apply_insight,
    estimate_cost,
    obviously_out_of_scope,
    out_of_scope_columns,
    parse_insight,
    request_params,
)
from earlybird.enrich.models import Facts

log = structlog.get_logger()
KIND = "enrich"
_REMOTE = {RemoteType.REMOTE_INDIA_OK, RemoteType.REMOTE_RESTRICTED, RemoteType.REMOTE_UNSPECIFIED}


def month_of(now: datetime) -> str:
    return f"{now:%Y-%m}"


def month_spend(conn: Connection, now: datetime, kind: str = KIND) -> float:
    """Recorded spend this month, plus estimates for batches still running."""
    spent = conn.execute(
        select(func.coalesce(func.sum(ai_usage.c.cost_usd), 0.0)).where(
            ai_usage.c.month == month_of(now), ai_usage.c.kind == kind
        )
    ).scalar_one()
    reserved = conn.execute(
        select(func.coalesce(func.sum(ai_batches.c.estimated_cost_usd), 0.0)).where(
            ai_batches.c.status != "ended"
        )
    ).scalar_one()
    return float(spent) + (float(reserved) if kind == KIND else 0.0)


def record_usage(
    conn: Connection, usage: Usage, *, now: datetime, kind: str, mode: str, model: str
) -> float:
    cost = usage.cost(batch=mode == "batch")
    if usage.requests:
        conn.execute(
            ai_usage.insert().values(
                month=month_of(now),
                kind=kind,
                mode=mode,
                model=model,
                requests=usage.requests,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=usage.cache_read_tokens,
                cache_write_tokens=usage.cache_write_tokens,
                cost_usd=cost,
                recorded_at=now,
            )
        )
    return cost


def _facts_from_row(row: Any) -> Facts:
    return Facts(
        remote_type=RemoteType(row.remote_type),
        yoe_min=row.yoe_min,
        yoe_max=row.yoe_max,
        seniority=Seniority(row.seniority),
        stack=list(row.stack or []),
        summary=row.summary,
    )


def apply_result(
    conn: Connection,
    job_id: str,
    text: str,
    *,
    expected_hash: str | None,
    model: str,
    now: datetime,
) -> bool:
    """Store one model answer. Skipped if the posting changed since it was sent."""
    row = conn.execute(select(jobs).where(jobs.c.job_id == job_id)).first()
    if row is None or (expected_hash is not None and row.content_hash != expected_hash):
        return False
    insight = parse_insight(text)
    if insight is None:
        log.warning("ai.parse_failed", job_id=job_id)
        return False
    enriched = apply_insight(_facts_from_row(row), insight, model=model)
    facts = enriched.facts
    locations = list(row.locations or []) or [
        f"{c['city']}, {c['country']}" for c in enriched.columns["office_cities"]
    ]
    bucket = location_bucket(locations, is_remote=facts.remote_type in _REMOTE)
    conn.execute(
        jobs.update()
        .where(jobs.c.job_id == job_id)
        .values(
            **enriched.columns,
            remote_type=facts.remote_type.value,
            yoe_min=facts.yoe_min,
            yoe_max=facts.yoe_max,
            seniority=facts.seniority.value,
            stack=facts.stack,
            summary=facts.summary,
            locations=locations,
            canonical_key=canonical_key(row.company_name, row.title, bucket),
            extraction_method=facts.method.value,
            ai_version=AI_VERSION,
            ai_content_hash=row.content_hash,
            enriched_at=now,
        )
    )
    return True


def mark_out_of_scope(conn: Connection, job_ids: Iterable[str], now: datetime) -> int:
    count = 0
    for job_id in job_ids:
        content_hash = conn.execute(
            select(jobs.c.content_hash).where(jobs.c.job_id == job_id)
        ).scalar_one()
        conn.execute(
            jobs.update()
            .where(jobs.c.job_id == job_id)
            .values(
                **out_of_scope_columns(),
                ai_version=AI_VERSION,
                ai_content_hash=content_hash,
                enriched_at=now,
            )
        )
        count += 1
    return count


def select_for_enrichment(conn: Connection, fetched: list[Job]) -> list[Job]:
    """Fetched, open jobs without a current AI reading (and not already in a running batch)."""
    by_id = {j.job_id: j for j in fetched if j.description_text}
    if not by_id:
        return []
    in_flight: set[str] = set()
    for items in conn.execute(
        select(ai_batches.c.job_hashes).where(ai_batches.c.status != "ended")
    ):
        in_flight |= set(items[0])
    needed: list[tuple[datetime, Job]] = []
    ids = list(by_id)
    for start in range(0, len(ids), 500):
        rows = conn.execute(
            select(
                jobs.c.job_id, jobs.c.content_hash, jobs.c.ai_version,
                jobs.c.ai_content_hash, jobs.c.closed_at, jobs.c.first_seen_at,
            ).where(jobs.c.job_id.in_(ids[start : start + 500]))
        )  # fmt: skip
        for row in rows:
            stale = row.ai_version != AI_VERSION or row.ai_content_hash != row.content_hash
            if stale and row.closed_at is None and row.job_id not in in_flight:
                needed.append((row.first_seen_at, by_id[row.job_id]))
    needed.sort(key=lambda pair: pair[0], reverse=True)
    return [job for _, job in needed]


def _within_budget(todo: list[Job], remaining: float, *, batch: bool) -> list[Job]:
    chosen: list[Job] = []
    for job in todo:
        if estimate_cost([*chosen, job], batch=batch) > remaining:
            break
        chosen.append(job)
    return chosen


async def _direct(
    client: anthropic.AsyncAnthropic, engine: Engine, todo: list[Job], settings: Settings,
    now: datetime,
) -> int:  # fmt: skip
    usage = Usage()
    done = 0
    semaphore = asyncio.Semaphore(settings.ai_concurrency)

    async def one(job: Job) -> None:
        nonlocal done
        async with semaphore:
            try:
                message = await client.messages.create(**request_params(job, settings.ai_model))
            except anthropic.APIError as exc:
                log.warning("ai.request_failed", job_id=job.job_id, error=str(exc)[:200])
                return
        usage.add(message.usage)
        text = next((b.text for b in message.content if b.type == "text"), "")
        with engine.begin() as conn:
            done += apply_result(
                conn, job.job_id, text, expected_hash=None, model=settings.ai_model, now=now
            )

    if todo:
        await one(todo[0])  # warm the prompt cache before going parallel
        await asyncio.gather(*(one(job) for job in todo[1:]))
    with engine.begin() as conn:
        cost = record_usage(conn, usage, now=now, kind=KIND, mode="direct", model=settings.ai_model)
    log.info("ai.direct_done", enriched=done, requests=usage.requests, cost_usd=round(cost, 4))
    return done


async def _submit_batch(
    client: anthropic.AsyncAnthropic, engine: Engine, todo: list[Job], settings: Settings,
    now: datetime,
) -> None:  # fmt: skip
    with engine.connect() as conn:
        hashes = dict(
            conn.execute(
                select(jobs.c.job_id, jobs.c.content_hash).where(
                    jobs.c.job_id.in_([j.job_id for j in todo])
                )
            ).all()
        )
    batch = await client.messages.batches.create(
        requests=[
            {
                "custom_id": job.job_id,
                "params": cast(
                    "MessageCreateParamsNonStreaming", request_params(job, settings.ai_model)
                ),
            }
            for job in todo
        ]
    )
    estimate = estimate_cost(todo, batch=True)
    with engine.begin() as conn:
        conn.execute(
            ai_batches.insert().values(
                batch_id=batch.id,
                submitted_at=now,
                status=batch.processing_status,
                request_count=len(todo),
                job_hashes=hashes,
                estimated_cost_usd=estimate,
            )
        )
    log.info("ai.batch_submitted", batch_id=batch.id, requests=len(todo), estimate_usd=estimate)


async def collect_batches(
    client: anthropic.AsyncAnthropic, engine: Engine, settings: Settings, now: datetime
) -> int:
    """Apply results of every batch that has finished since the last run."""
    with engine.connect() as conn:
        open_batches = conn.execute(
            select(ai_batches.c.batch_id, ai_batches.c.job_hashes).where(
                ai_batches.c.status != "ended"
            )
        ).all()
    applied = 0
    for batch_id, items in open_batches:
        batch = await client.messages.batches.retrieve(batch_id)
        if batch.processing_status != "ended":
            with engine.begin() as conn:
                conn.execute(
                    ai_batches.update()
                    .where(ai_batches.c.batch_id == batch_id)
                    .values(status=batch.processing_status)
                )
            continue
        usage = Usage()
        with engine.begin() as conn:
            async for result in await client.messages.batches.results(batch_id):
                if result.result.type != "succeeded":
                    continue
                message = result.result.message
                usage.add(message.usage)
                text = next((b.text for b in message.content if b.type == "text"), "")
                applied += apply_result(
                    conn, result.custom_id, text, expected_hash=items.get(result.custom_id),
                    model=settings.ai_model, now=now,
                )  # fmt: skip
            cost = record_usage(
                conn, usage, now=now, kind=KIND, mode="batch", model=settings.ai_model
            )
            conn.execute(
                ai_batches.update()
                .where(ai_batches.c.batch_id == batch_id)
                .values(status="ended", finished_at=now, estimated_cost_usd=0.0)
            )
        log.info("ai.batch_collected", batch_id=batch_id, applied=applied, cost_usd=round(cost, 4))
    return applied


async def enrich(
    engine: Engine, fetched: list[Job], settings: Settings, now: datetime
) -> dict[str, int]:
    """Run the whole enrichment stage. Without an API key it does nothing (rules only)."""
    if settings.anthropic_api_key is None:
        log.info("ai.disabled", reason="no ANTHROPIC_API_KEY")
        return {}
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value())
    try:
        collected = await collect_batches(client, engine, settings, now)
        with engine.begin() as conn:
            todo = select_for_enrichment(conn, fetched)
            skipped = mark_out_of_scope(
                conn, [j.job_id for j in todo if obviously_out_of_scope(j.title)], now
            )
            todo = [j for j in todo if not obviously_out_of_scope(j.title)]
            remaining = settings.ai_monthly_budget_usd - month_spend(conn, now)
        use_batch = len(todo) > settings.ai_batch_threshold
        if use_batch:
            todo = todo[: settings.ai_max_batch_size]
        affordable = _within_budget(todo, max(remaining, 0.0), batch=use_batch)
        if len(affordable) < len(todo):
            log.warning("ai.budget_limited", wanted=len(todo), affordable=len(affordable),
                        remaining_usd=round(remaining, 4))  # fmt: skip
        direct = 0
        if affordable and use_batch:
            await _submit_batch(client, engine, affordable, settings, now)
        elif affordable:
            direct = await _direct(client, engine, affordable, settings, now)
    finally:
        await client.close()
    return {"collected": collected, "prefiltered": skipped, "direct": direct,
            "batched": len(affordable) if use_batch else 0}  # fmt: skip
