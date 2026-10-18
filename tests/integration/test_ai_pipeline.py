import json
from collections.abc import AsyncIterator, Callable
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import Engine, select

from earlybird.core.config import Settings
from earlybird.core.models import Company, Job
from earlybird.db.schema import ai_batches, ai_usage, jobs
from earlybird.enrich import pipeline
from earlybird.enrich.ai import AI_VERSION
from earlybird.ingest import FetchOutcome, store
from earlybird.private import fit
from earlybird.private.profile import Profile
from tests.conftest import NOW

ANSWER = {
    "domain": "data", "subdomain": "data engineering", "seniority": "senior", "yoe_min": 5,
    "yoe_max": None, "work_setup": "remote", "eligible_countries": ["IN"], "eligible_regions": [],
    "office_cities": [], "required_languages": [], "visa_sponsorship": "unknown",
    "skills_required": ["python"], "skills_preferred": [], "responsibilities": [],
    "salary": None, "summary": "Data engineering role.",
}  # fmt: skip
USAGE = SimpleNamespace(
    input_tokens=1000, output_tokens=400, cache_read_input_tokens=0, cache_creation_input_tokens=0
)


def message(answer: dict[str, Any] = ANSWER) -> SimpleNamespace:
    return SimpleNamespace(
        usage=USAGE, content=[SimpleNamespace(type="text", text=json.dumps(answer))]
    )


class FakeBatches:
    def __init__(self) -> None:
        self.created: list[Any] = []

    async def create(self, requests: list[dict[str, Any]]) -> SimpleNamespace:
        self.created.append(requests)
        return SimpleNamespace(id="msgbatch_1", processing_status="in_progress")

    async def retrieve(self, batch_id: str) -> SimpleNamespace:
        return SimpleNamespace(processing_status="ended")

    async def results(self, batch_id: str) -> AsyncIterator[SimpleNamespace]:
        async def gen() -> AsyncIterator[SimpleNamespace]:
            for request in self.created[-1]:
                yield SimpleNamespace(
                    custom_id=request["custom_id"],
                    result=SimpleNamespace(type="succeeded", message=message()),
                )

        return gen()


class FakeClient:
    def __init__(self) -> None:
        self.calls = 0
        self.messages = SimpleNamespace(create=self._create, batches=FakeBatches())

    async def _create(self, **params: Any) -> SimpleNamespace:
        self.calls += 1
        return message()

    async def close(self) -> None:
        return None


@pytest.fixture
def setup(
    engine: Engine, company: Company, make_job: Callable[..., Job], monkeypatch: pytest.MonkeyPatch
) -> tuple[Engine, list[Job], FakeClient]:
    fetched = [
        make_job(external_id="1", title="Data Engineer"),
        make_job(external_id="2", title="Enterprise Account Executive"),
        make_job(external_id="3", title="ML Engineer"),
    ]
    store(engine, [FetchOutcome("greenhouse", fetched, company, company.ats[0])],
          run_id="r", started_at=NOW, now=NOW)  # fmt: skip
    client = FakeClient()
    monkeypatch.setattr(pipeline.anthropic, "AsyncAnthropic", lambda **_: client)
    return engine, fetched, client


def settings(**kw: Any) -> Settings:
    return Settings(anthropic_api_key="test-key", **kw)  # type: ignore[arg-type]


async def test_direct_enrichment_and_prefilter(setup: tuple[Engine, list[Job], FakeClient]) -> None:
    engine, fetched, client = setup
    result = await pipeline.enrich(engine, fetched, settings(), NOW)
    assert result == {"collected": 0, "prefiltered": 1, "direct": 2, "batched": 0}
    assert client.calls == 2  # the account executive never reached the model
    with engine.connect() as conn:
        rows = {r.title: r for r in conn.execute(select(jobs))}
        spent = conn.execute(select(ai_usage.c.cost_usd)).scalar_one()
    assert rows["Data Engineer"].domain == "data"
    assert rows["Data Engineer"].ai_version == AI_VERSION
    assert rows["Data Engineer"].eligible_countries == ["IN"]
    assert rows["Enterprise Account Executive"].domain == "other"
    assert spent > 0
    # idempotent: nothing left to do on the next run
    assert (await pipeline.enrich(engine, fetched, settings(), NOW))["direct"] == 0


async def test_batch_submit_then_collect(setup: tuple[Engine, list[Job], FakeClient]) -> None:
    engine, fetched, client = setup
    first = await pipeline.enrich(engine, fetched, settings(ai_batch_threshold=0), NOW)
    assert first["batched"] == 2 and client.calls == 0
    with engine.connect() as conn:
        assert conn.execute(select(ai_batches.c.status)).scalar_one() == "in_progress"
    second = await pipeline.enrich(engine, fetched, settings(ai_batch_threshold=0), NOW)
    assert second["collected"] == 2 and second["batched"] == 0
    with engine.connect() as conn:
        assert conn.execute(select(ai_batches.c.status)).scalar_one() == "ended"
        mode = conn.execute(select(ai_usage.c.mode)).scalar_one()
    assert mode == "batch"


async def test_stale_results_are_not_applied(
    setup: tuple[Engine, list[Job], FakeClient],
) -> None:
    engine, _fetched, _client = setup
    with engine.begin() as conn:
        job_id = conn.execute(select(jobs.c.job_id).limit(1)).scalar_one()
        applied = pipeline.apply_result(
            conn, job_id, json.dumps(ANSWER), expected_hash="changed-since",
            model="m", now=NOW,
        )  # fmt: skip
    assert applied is False


async def test_budget_caps_spend(setup: tuple[Engine, list[Job], FakeClient]) -> None:
    engine, fetched, client = setup
    result = await pipeline.enrich(engine, fetched, settings(ai_monthly_budget_usd=0.0), NOW)
    assert result["direct"] == 0 and client.calls == 0


async def test_no_key_means_rules_only(setup: tuple[Engine, list[Job], FakeClient]) -> None:
    engine, fetched, client = setup
    assert await pipeline.enrich(engine, fetched, Settings(anthropic_api_key=None), NOW) == {}
    assert client.calls == 0


async def test_fit_scoring_only_scores_filtered_enriched_jobs(
    setup: tuple[Engine, list[Job], FakeClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, fetched, client = setup
    await pipeline.enrich(engine, fetched, settings(), NOW)  # 2 enriched, 1 out of scope

    async def fit_reply(**params: Any) -> SimpleNamespace:
        client.calls += 1
        answer = {"fit": 88, "reason": "Strong DE match", "matched_skills": ["python"],
                  "missing_skills": []}  # fmt: skip
        return SimpleNamespace(
            usage=USAGE, content=[SimpleNamespace(type="text", text=json.dumps(answer))]
        )

    client.messages.create = fit_reply
    monkeypatch.setattr(fit.anthropic, "AsyncAnthropic", lambda **_: client)
    profile = Profile(yoe=6, countries=["IN"])
    before = client.calls
    result = await fit.score_pending(engine, profile, settings(), NOW)
    assert result["scored"] == 2 and client.calls - before == 2
    scored = fit.fit_lookup(engine, profile)
    assert {s["fit"] for s in scored.values()} == {88}
    again = await fit.score_pending(engine, profile, settings(), NOW)
    assert again["scored"] == 0  # one score per job per profile version
