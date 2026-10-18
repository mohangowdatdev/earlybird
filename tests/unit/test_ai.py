import json
from collections.abc import Callable

from earlybird.core.models import Domain, Job, RemoteType, Seniority, WorkSetup
from earlybird.enrich.ai import (
    INSIGHT_SCHEMA,
    JobInsight,
    Usage,
    apply_insight,
    estimate_cost,
    obviously_out_of_scope,
    parse_insight,
    remote_type_from,
    request_params,
)
from earlybird.enrich.rules import extract

ANSWER = {
    "domain": "data", "subdomain": "data engineering", "seniority": "unknown", "yoe_min": 6,
    "yoe_max": None, "work_setup": "hybrid", "eligible_countries": ["ae", "XX"],
    "eligible_regions": ["middle_east", "mars"],
    "office_cities": [{"city": "dubai", "country": "AE"}],
    "required_languages": ["English", "arabic"], "visa_sponsorship": "yes",
    "skills_required": ["PySpark", "Azure Data Factory", "Kubernetes"], "skills_preferred": ["dbt"],
    "responsibilities": ["Build lakehouse pipelines"], "salary": None,
    "summary": "Senior data engineer building pipelines in Dubai.",
}  # fmt: skip


def test_schema_is_strict() -> None:
    assert INSIGHT_SCHEMA["additionalProperties"] is False
    assert set(INSIGHT_SCHEMA["required"]) == set(INSIGHT_SCHEMA["properties"])


def test_parse_normalises_places_and_languages() -> None:
    insight = parse_insight(json.dumps(ANSWER))
    assert insight is not None
    assert insight.eligible_countries == ["AE"]
    assert insight.eligible_regions == ["middle_east"]
    assert insight.office_cities[0].city == "Dubai"
    assert insight.required_languages == ["Arabic"]
    assert parse_insight("not json") is None


def test_apply_insight_merges_with_rules(make_job: Callable[..., Job]) -> None:
    rules = extract(make_job(title="Data Engineer"))
    insight = JobInsight.model_validate(ANSWER)
    enriched = apply_insight(rules, insight, model="claude-haiku-5-5")
    assert enriched.facts.remote_type is RemoteType.HYBRID  # the description wins
    assert enriched.facts.seniority is Seniority.SENIOR  # inferred from 6 years
    assert {"spark", "azure data factory", "kubernetes"} <= set(enriched.facts.stack)
    assert enriched.columns["domain"] == "data"
    assert enriched.columns["required_languages"] == ["Arabic"]


def test_remote_type_derivation() -> None:
    def make(**kw: object) -> JobInsight:
        return JobInsight.model_validate({**ANSWER, "work_setup": "remote", **kw})

    assert remote_type_from(make(eligible_countries=["IN"])) is RemoteType.REMOTE_INDIA_OK
    assert remote_type_from(make(eligible_countries=[], eligible_regions=["apac"])) is (
        RemoteType.REMOTE_INDIA_OK
    )
    assert remote_type_from(make(eligible_countries=["US"], eligible_regions=[])) is (
        RemoteType.REMOTE_RESTRICTED
    )
    assert remote_type_from(make(eligible_countries=[], eligible_regions=[])) is (
        RemoteType.REMOTE_UNSPECIFIED
    )
    assert (
        JobInsight.model_validate({**ANSWER, "work_setup": "onsite"}).work_setup is WorkSetup.ONSITE
    )
    assert JobInsight.model_validate(ANSWER).domain is Domain.DATA


def test_prefilter_is_conservative() -> None:
    assert obviously_out_of_scope("Enterprise Account Executive")
    assert obviously_out_of_scope("Technical Recruiter")
    assert not obviously_out_of_scope("Data Engineer, Sales Analytics")
    assert not obviously_out_of_scope("Security Analyst")


def test_request_and_cost(make_job: Callable[..., Job]) -> None:
    params = request_params(make_job(), "claude-haiku-5-5")
    assert params["thinking"] == {"type": "disabled"}
    assert params["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert estimate_cost([make_job()], batch=True) < estimate_cost([make_job()], batch=False)

    class U:
        input_tokens, output_tokens = 1_000_000, 0
        cache_read_input_tokens, cache_creation_input_tokens = 0, 0

    usage = Usage()
    usage.add(U())
    assert usage.cost(batch=False) == 0.10 and usage.cost(batch=True) == 0.05
