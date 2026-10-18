from collections.abc import Callable

import pytest

from earlybird.core.models import Job, RemoteType, Seniority
from earlybird.enrich.rules import (
    detect_remote,
    detect_seniority,
    extract,
    extract_stack,
    extract_yoe,
)


@pytest.mark.parametrize(
    ("locations", "remote_raw", "expected"),
    [
        (["Remote - India"], None, RemoteType.REMOTE_INDIA_OK),
        (["Remote, Worldwide"], None, RemoteType.REMOTE_INDIA_OK),
        (["Remote - US"], None, RemoteType.REMOTE_RESTRICTED),
        (["United States"], "true", RemoteType.REMOTE_RESTRICTED),
        (["Bangalore, India"], "Remote", RemoteType.REMOTE_INDIA_OK),
        (["Remote"], None, RemoteType.REMOTE_UNSPECIFIED),
        (["NAMER"], "Remote", RemoteType.REMOTE_RESTRICTED),
        ([], "Worldwide", RemoteType.REMOTE_INDIA_OK),
        ([], "USA Only", RemoteType.REMOTE_RESTRICTED),
        (["Bangalore (Hybrid)"], None, RemoteType.HYBRID),
        (["San Francisco, CA"], None, RemoteType.ONSITE),
        ([], None, RemoteType.UNKNOWN),
    ],
)
def test_detect_remote(
    make_job: Callable[..., Job],
    locations: list[str],
    remote_raw: str | None,
    expected: RemoteType,
) -> None:
    job = make_job(locations=locations, remote_raw=remote_raw, description_text=None)
    assert detect_remote(job) is expected


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("This role is open to candidates in India and Singapore.", RemoteType.REMOTE_INDIA_OK),
        ("We are hiring across APAC for this position.", RemoteType.REMOTE_INDIA_OK),
        ("You must be based in the US to be considered.", RemoteType.REMOTE_RESTRICTED),
        (
            "Candidates must be authorized to work in the United States.",
            RemoteType.REMOTE_RESTRICTED,
        ),
        ("Remote - US. Occasional travel.", RemoteType.REMOTE_RESTRICTED),
        ("We value curiosity and kindness.", RemoteType.REMOTE_UNSPECIFIED),
    ],
)
def test_description_eligibility_refines_bare_remote(
    make_job: Callable[..., Job], description: str, expected: RemoteType
) -> None:
    job = make_job(locations=["Remote"], description_text=description)
    assert detect_remote(job) is expected


def test_location_line_in_description(make_job: Callable[..., Job]) -> None:
    job = make_job(locations=[], description_text="About us\nLocation: Bengaluru, India\nHybrid")
    assert detect_remote(job) is RemoteType.ONSITE


def test_remote_from_description_when_locations_silent(make_job: Callable[..., Job]) -> None:
    job = make_job(locations=["New York"], description_text="This is a fully remote role.")
    assert detect_remote(job) is RemoteType.REMOTE_UNSPECIFIED


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("5+ years of experience in data engineering", (5, None)),
        ("3-5 years of relevant experience", (3, 5)),
        ("3 to 6 yrs experience building pipelines", (3, 6)),
        ("Minimum of 4 years experience; 2+ years with Spark experience", (2, None)),
        ("five years of professional experience", (5, None)),
        ("We were founded 10 years ago and have 500 customers.", (None, None)),
        ("40+ years combined team history", (None, None)),
        (None, (None, None)),
    ],
)
def test_extract_yoe(text: str | None, expected: tuple[int | None, int | None]) -> None:
    assert extract_yoe(text) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Senior Data Engineer", Seniority.SENIOR),
        ("Sr. ML Engineer", Seniority.SENIOR),
        ("Staff Software Engineer, Data", Seniority.STAFF_PLUS),
        ("Engineering Manager, Data Platform", Seniority.LEAD_MANAGER),
        ("Director of Data", Seniority.EXECUTIVE),
        ("Data Engineering Intern", Seniority.INTERN),
        ("Data Engineer II", Seniority.MID),
        ("Data Engineer", Seniority.UNKNOWN),
    ],
)
def test_detect_seniority(title: str, expected: Seniority) -> None:
    assert detect_seniority(title) is expected


def test_extract_stack_uses_aliases_and_frequency() -> None:
    text = "PySpark and Spark SQL on Databricks. Apache Airflow. Some k8s. Go is fun. Golang!"
    tags = extract_stack(text)
    assert tags[0] in {"spark", "go"}
    assert {"spark", "databricks", "airflow", "kubernetes", "go"} <= set(tags)
    assert "django" not in tags


def test_everyday_words_are_not_stack() -> None:
    text = "We go above and beyond, react quickly, spark joy, avoid red flags."
    assert extract_stack(text) == []
    assert set(extract_stack("We use Go, React and Spark; some golang too.")) == {
        "go", "react", "spark",
    }  # fmt: skip


def test_extract_builds_summary(make_job: Callable[..., Job]) -> None:
    facts = extract(make_job())
    assert facts.remote_type is RemoteType.REMOTE_INDIA_OK
    assert facts.yoe_min == 5
    assert facts.summary.startswith("Senior · Remote (India OK) · 5+ yrs")
