from typing import Any

import pytest

from earlybird.core.geo import canonical_city, countries_in, country_code
from earlybird.core.models import Domain, Seniority
from earlybird.private.filtering import exclusion_reason, location_fit
from earlybird.private.profile import Profile

INDIA = Profile(yoe=7, countries=["IN"])
BLR_ONLY = Profile(yoe=7, cities=["Bengaluru"])


def job(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title": "Data Engineer", "domain": "data", "work_setup": "remote",
        "remote_type": "remote_unspecified", "eligible_countries": [], "eligible_regions": [],
        "office_cities": [], "locations": [], "required_languages": [], "seniority": "senior",
        "yoe_min": None, "yoe_max": None,
    }  # fmt: skip
    data.update(overrides)
    return data


def test_geo_helpers() -> None:
    assert canonical_city("Bangalore, India") == ("Bengaluru", "IN")
    assert canonical_city("Gurgaon") == ("Gurugram", "IN")
    assert country_code("india") == "IN" and country_code("UAE") == "AE"
    assert "IN" in countries_in(["apac"]) and "IN" not in countries_in(["emea"])


@pytest.mark.parametrize(
    ("overrides", "profile", "expected"),
    [
        ({"eligible_countries": ["IN"]}, INDIA, True),
        ({"eligible_regions": ["worldwide"]}, INDIA, True),
        ({"eligible_regions": ["apac"]}, BLR_ONLY, True),  # a city implies its country for remote
        ({"eligible_countries": ["US"]}, INDIA, False),
        ({"eligible_regions": ["emea"]}, INDIA, False),
        ({}, INDIA, None),  # remote, nothing stated: fail open
        (
            {"work_setup": "hybrid", "office_cities": [{"city": "Dubai", "country": "AE"}]},
            INDIA,
            False,
        ),  # the "hybrid" that is really Dubai-only
        (
            {"work_setup": "onsite", "office_cities": [{"city": "Hyderabad", "country": "IN"}]},
            BLR_ONLY,
            False,
        ),
        (
            {"work_setup": "onsite", "office_cities": [{"city": "Hyderabad", "country": "IN"}]},
            INDIA,
            True,
        ),
        ({"work_setup": "hybrid", "locations": ["Bangalore, India"]}, BLR_ONLY, True),
    ],
)
def test_location_fit(overrides: dict[str, Any], profile: Profile, expected: bool | None) -> None:
    assert location_fit(job(**overrides), profile) is expected


def test_exclusion_reasons_in_order() -> None:
    p = Profile(yoe=7, domains=[Domain.DATA], seniorities=[Seniority.SENIOR], countries=["IN"])
    assert exclusion_reason(job(domain="other"), p) == "outside data, AI and security"
    assert exclusion_reason(job(domain="ai"), p) == "ai role, not in your spaces"
    assert exclusion_reason(job(yoe_min=12), p) == "needs 12+ years"
    assert exclusion_reason(job(seniority="director"), p) == "Director level"
    assert exclusion_reason(job(eligible_countries=["US"]), p) == "location doesn't match"
    assert exclusion_reason(job(required_languages=["Arabic"]), p) == "requires Arabic"
    assert exclusion_reason(job(), p) is None
    assert exclusion_reason(job(domain=None, seniority="unknown"), p) is None  # fail open
