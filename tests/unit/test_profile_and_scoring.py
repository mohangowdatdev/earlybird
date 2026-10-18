from pathlib import Path
from typing import Any

from earlybird.core.models import RemoteType, Seniority
from earlybird.private.profile import Profile, load_profile, save_profile
from earlybird.private.scoring import Bucket, score_job

PROFILE = Profile(
    name="Test",
    yoe=7,
    role_families=["Data Engineer", "ml engineer"],
    skills_must=["python", "spark"],
    skills_nice=["airflow"],
    watchlist=["perchco"],
)


def row(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title": "Senior Data Engineer",
        "company_slug": "acme",
        "remote_type": RemoteType.REMOTE_INDIA_OK.value,
        "seniority": Seniority.SENIOR.value,
        "yoe_min": 5,
        "yoe_max": 8,
        "stack": ["python", "spark", "airflow"],
        "locations": ["Remote - India"],
        "salary_max": None,
        "salary_currency": None,
    }
    data.update(overrides)
    return data


def test_profile_lists_are_cleaned_and_round_trip(tmp_path: Path) -> None:
    assert PROFILE.role_families == ["data engineer", "ml engineer"]
    path = tmp_path / "profile.yaml"
    save_profile(PROFILE, path)
    loaded = load_profile(path)
    assert loaded == PROFILE
    assert loaded is not None and loaded.version == PROFILE.version
    assert PROFILE.model_copy(update={"yoe": 8}).version != PROFILE.version


def test_load_missing_profile_is_none(tmp_path: Path) -> None:
    assert load_profile(tmp_path / "nope.yaml") is None


def test_great_match_is_strong() -> None:
    score = score_job(row(), PROFILE)
    assert score.bucket is Bucket.STRONG
    assert "role:data engineer" in score.reasons


def test_hard_exclude_records_reason() -> None:
    score = score_job(row(title="Data Engineering Intern"), PROFILE)
    assert score.bucket is Bucket.EXCLUDED
    assert score.excluded_reason == "title:intern"


def test_watchlist_promotes_relevant_jobs_only() -> None:
    weak = row(company_slug="perchco", stack=["python"], yoe_min=15, yoe_max=20,
               remote_type="remote_restricted")  # fmt: skip
    loose = row(company_slug="perchco", title="Software Engineer, Platform", stack=["go"])
    assert not score_job(loose, PROFILE).watchlist  # one shared word is not relevance
    promoted = score_job(weak, PROFILE)
    assert promoted.bucket is Bucket.STRONG and promoted.watchlist
    off_topic = score_job(row(company_slug="perchco", title="Account Executive", stack=[]), PROFILE)
    assert off_topic.bucket is Bucket.EXCLUDED and not off_topic.watchlist
    intern = score_job(row(company_slug="perchco", title="Data Engineering Intern"), PROFILE)
    assert intern.bucket is Bucket.EXCLUDED


def test_skill_aliases_match_canonical_tags() -> None:
    aliased = PROFILE.model_copy(update={"skills_must": ["pyspark", "postgres"]})
    score = score_job(row(stack=["spark", "postgresql"]), aliased)
    assert score.skill_hits == ["pyspark", "postgres"]


def test_unknowns_fail_open_to_maybe() -> None:
    score = score_job(
        row(stack=[], yoe_min=None, yoe_max=None, remote_type="unknown", locations=[]), PROFILE
    )
    assert score.bucket is Bucket.MAYBE


def test_unrelated_role_is_excluded_as_low_score() -> None:
    score = score_job(row(title="Product Designer", stack=[]), PROFILE)
    assert score.bucket is Bucket.EXCLUDED
    assert score.excluded_reason == "low_score"


def test_yoe_outside_tolerance_scores_lower() -> None:
    fits = score_job(row(yoe_min=8, yoe_max=None), PROFILE).value  # 8 <= 7+2
    too_senior = score_job(row(yoe_min=12, yoe_max=15), PROFILE).value
    assert fits > too_senior


def test_restricted_remote_scores_lower_than_india_ok() -> None:
    india = score_job(row(), PROFILE).value
    us_only = score_job(row(remote_type="remote_restricted", locations=["Remote - US"]), PROFILE)
    assert us_only.value < india


def test_false_friend_titles_do_not_match_roles() -> None:
    score = score_job(row(title="Data Center Engineer", stack=[]), PROFILE)
    assert score.parts["role"] < 1
