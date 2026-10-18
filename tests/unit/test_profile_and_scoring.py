from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from earlybird.core.models import Domain, RemoteType, Seniority, WorkSetup
from earlybird.private.profile import Profile, load_profile, save_profile
from earlybird.private.scoring import Bucket, score_job
from tests.conftest import NOW

PROFILE = Profile(
    name="Test",
    yoe=7,
    domains=[Domain.DATA, Domain.AI],
    countries=["India"],
    cities=["bangalore"],
    role_families=["Data Engineer", "ml engineer"],
    skills_must=["python", "spark"],
    skills_nice=["airflow"],
    watchlist=["perchco"],
)


def row(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title": "Senior Data Engineer",
        "company_slug": "acme",
        "domain": "data",
        "work_setup": "remote",
        "remote_type": RemoteType.REMOTE_INDIA_OK.value,
        "eligible_countries": ["IN"],
        "eligible_regions": [],
        "office_cities": [],
        "required_languages": [],
        "seniority": Seniority.SENIOR.value,
        "yoe_min": 5,
        "yoe_max": 8,
        "stack": ["python", "spark", "airflow"],
        "locations": ["Remote - India"],
        "salary_max": None,
        "salary_currency": None,
        "first_seen_at": NOW,
    }
    data.update(overrides)
    return data


def test_profile_normalises_places_and_round_trips(tmp_path: Path) -> None:
    assert PROFILE.countries == ["IN"]
    assert PROFILE.cities == ["Bengaluru"]
    assert PROFILE.remote_countries == {"IN"}
    path = tmp_path / "profile.yaml"
    save_profile(PROFILE, path)
    assert load_profile(path) == PROFILE
    assert PROFILE.model_copy(update={"yoe": 8}).version != PROFILE.version


def test_at_most_two_domains() -> None:
    with pytest.raises(ValueError, match="at most 2"):
        Profile(domains=[Domain.DATA, Domain.AI, Domain.CYBERSECURITY])
    assert Profile(domains=[Domain.OTHER]).domains == []


def test_old_profile_files_still_load(tmp_path: Path) -> None:
    path = tmp_path / "profile.yaml"
    path.write_text(
        "yoe: 6\nremote_types: [remote_india_ok]\ncities: [bangalore]\n"
        "seniorities: [senior, staff_plus, executive]\n"
    )
    loaded = load_profile(path)
    assert loaded is not None and loaded.cities == ["Bengaluru"]
    assert loaded.seniorities == [Seniority.SENIOR, Seniority.STAFF_PRINCIPAL, Seniority.DIRECTOR]


def test_great_match_is_strong_without_ai() -> None:
    score = score_job(row(), PROFILE)
    assert score.bucket is Bucket.STRONG
    assert score.fit is None


def test_ai_fit_decides_bucket_and_freshness_ranks() -> None:
    fit = {"fit": 62, "reason": "Good stack, light on ML", "matched": ["spark"], "missing": ["k8s"]}
    score = score_job(row(), PROFILE, fit, NOW)
    assert score.bucket is Bucket.MAYBE and score.fit == 62 and score.missing == ["k8s"]
    older = score_job(row(first_seen_at=NOW - timedelta(days=3)), PROFILE, fit, NOW)
    assert older.rank < score.rank
    low = score_job(row(), PROFILE, {**fit, "fit": 30}, NOW)
    assert low.bucket is Bucket.EXCLUDED and low.excluded_reason == "low AI fit"


def test_filters_run_before_scoring() -> None:
    fit = {"fit": 99, "reason": "x", "matched": [], "missing": []}
    score = score_job(row(domain="cybersecurity"), PROFILE, fit)
    assert score.bucket is Bucket.EXCLUDED
    assert score.excluded_reason == "cybersecurity role, not in your spaces"


def test_watchlist_promotes_relevant_jobs_only() -> None:
    weak = row(company_slug="perchco", stack=["python"], yoe_min=8, yoe_max=None)
    promoted = score_job(weak, PROFILE)
    assert promoted.bucket is Bucket.STRONG and promoted.watchlist
    loose = row(company_slug="perchco", title="Software Engineer, Platform", stack=["go"])
    assert not score_job(loose, PROFILE).watchlist
    intern = score_job(row(company_slug="perchco", title="Data Engineering Intern"), PROFILE)
    assert intern.bucket is Bucket.EXCLUDED


def test_skill_aliases_match_canonical_tags() -> None:
    aliased = PROFILE.model_copy(update={"skills_must": ["pyspark", "postgres"]})
    score = score_job(row(stack=["spark", "postgresql"]), aliased)
    assert score.skill_hits == ["pyspark", "postgres"]


def test_false_friend_titles_do_not_match_roles() -> None:
    score = score_job(row(title="Data Center Engineer", stack=[]), PROFILE)
    assert score.parts.get("role", 0) < 1


def test_setup_preference_is_respected() -> None:
    remote_only = PROFILE.model_copy(update={"work_setups": [WorkSetup.REMOTE]})
    onsite = row(work_setup="onsite", remote_type="onsite", office_cities=[
        {"city": "Bengaluru", "country": "IN"}])  # fmt: skip
    assert score_job(onsite, remote_only).excluded_reason == "onsite role"
