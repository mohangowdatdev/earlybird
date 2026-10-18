from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import Engine, select

from earlybird.core.models import Company, Job, RemoteType, Seniority
from earlybird.db.schema import jobs
from earlybird.enrich import queue as llm_queue
from earlybird.enrich.llm import (
    LLMFacts,
    build_prompt,
    evidence_text,
    is_candidate,
    merge,
    trim_description,
)
from earlybird.enrich.rules import extract
from earlybird.ingest import FetchOutcome, Refiner, refine, store
from tests.conftest import NOW


class FakeExtractor:
    model = "fake"

    def __init__(self, answer: LLMFacts | None) -> None:
        self.answer = answer
        self.calls = 0

    async def extract(self, job: Job) -> LLMFacts | None:
        self.calls += 1
        return self.answer

    async def aclose(self) -> None:
        return None


def test_india_upgrade_requires_evidence(make_job: Callable[..., Job]) -> None:
    job = make_job(locations=["Remote"], description_text="Fully remote team. Great benefits.")
    rules = extract(job)
    assert rules.remote_type is RemoteType.REMOTE_UNSPECIFIED
    claim = LLMFacts(remote_type=RemoteType.REMOTE_INDIA_OK)
    assert merge(rules, claim, evidence_text(job)).remote_type is RemoteType.REMOTE_UNSPECIFIED

    grounded = make_job(locations=["Remote"], description_text="Remote. We hire across APAC.")
    facts = merge(extract(grounded), claim, evidence_text(grounded))
    assert facts.remote_type is RemoteType.REMOTE_INDIA_OK


def test_merge_never_narrows(make_job: Callable[..., Job]) -> None:
    job = make_job()  # rules: remote_india_ok, 5+ yrs
    narrowed = LLMFacts(remote_type=RemoteType.REMOTE_RESTRICTED, yoe_min=9)
    facts = merge(extract(job), narrowed, evidence_text(job))
    assert facts.remote_type is RemoteType.REMOTE_INDIA_OK
    assert facts.yoe_min == 5


def test_yoe_and_skills_must_appear_in_text(make_job: Callable[..., Job]) -> None:
    job = make_job(description_text="We use Snowflake. Seasoned engineers welcome.")
    answer = LLMFacts(yoe_min=7, skills=["snowflake", "kubernetes"], seniority=Seniority.SENIOR)
    facts = merge(extract(job), answer, evidence_text(job))
    assert facts.yoe_min is None  # "7 years" isn't in the text
    assert "snowflake" in facts.stack and "kubernetes" not in facts.stack

    stated = make_job(description_text="You bring 6+ years of data engineering experience.")
    assert merge(extract(stated), LLMFacts(yoe_min=6), evidence_text(stated)).yoe_min == 6


def test_candidates_are_uncertain_tech_roles(make_job: Callable[..., Job]) -> None:
    unsure = make_job(locations=["Remote"], description_text="Fully remote. Python, Spark.")
    assert is_candidate(unsure, extract(unsure))
    sales = make_job(title="Account Executive", locations=["Remote"], description_text="Quota.")
    assert not is_candidate(sales, extract(sales))
    no_text = make_job(description_text=None)
    assert not is_candidate(no_text, extract(no_text))


def test_prompt_keeps_relevant_lines() -> None:
    text = "Intro line\nAbout us\nMission\nWe love dogs\nMust be based in the US\n5 years of Python"
    trimmed = trim_description(text)
    assert "Must be based in the US" in trimmed and "5 years" in trimmed
    assert "dogs" not in trimmed


def test_build_prompt_has_fields(make_job: Callable[..., Job]) -> None:
    prompt = build_prompt(make_job())
    assert "Title: Senior Data Engineer" in prompt and "Remote - India" in prompt


@pytest.fixture
def stored(
    engine: Engine, company: Company, make_job: Callable[..., Job]
) -> tuple[Engine, list[tuple[Job, object]]]:
    job = make_job(
        external_id="77", title="Data Engineer", locations=["Remote"],
        description_text="Fully remote. Open to candidates in India. 4+ years of SQL.",
    )  # fmt: skip
    extracted: list[tuple[Job, object]] = []
    store(
        engine,
        [FetchOutcome("greenhouse", [job], company, company.ats[0])],
        run_id="r",
        started_at=NOW,
        now=NOW,
        extracted=extracted,  # type: ignore[arg-type]
    )
    return engine, extracted


async def test_refine_updates_rows_and_drains_queue(
    stored: tuple[Engine, list[tuple[Job, object]]], tmp_path: Path
) -> None:
    engine, extracted = stored
    fake = FakeExtractor(LLMFacts(remote_type=RemoteType.REMOTE_INDIA_OK, seniority=Seniority.MID))
    refiner = Refiner(fake, tmp_path / "q.db", time_budget_seconds=60, max_jobs=10)  # type: ignore[arg-type]
    result = await refine(engine, refiner, extracted, NOW)  # type: ignore[arg-type]
    assert result["done"] == 1 and result["remaining"] == 0
    with engine.connect() as conn:
        row = conn.execute(select(jobs)).one()
    assert row.extraction_method == "mixed"
    assert row.seniority == "mid"
    assert row.description_text is None  # still never stored publicly


async def test_budget_leaves_work_queued(
    stored: tuple[Engine, list[tuple[Job, object]]], tmp_path: Path
) -> None:
    engine, extracted = stored
    fake = FakeExtractor(None)
    refiner = Refiner(fake, tmp_path / "q.db", time_budget_seconds=-1, max_jobs=10)  # type: ignore[arg-type]
    result = await refine(engine, refiner, extracted, NOW)  # type: ignore[arg-type]
    assert result == {"done": 0, "remote_changed": 0, "remaining": 1}
    assert fake.calls == 0
    queued = llm_queue.take(llm_queue.open_queue(tmp_path / "q.db"), 5)
    assert queued[0].description_text  # survives for the next run
