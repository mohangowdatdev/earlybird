from earlybird.core.normalize import (
    canonical_key,
    location_bucket,
    normalize_company,
    normalize_title,
)


def test_normalize_title_variants_converge() -> None:
    assert normalize_title("Sr. Data Engineer (Remote)") == normalize_title("Senior Data Engineer")
    assert normalize_title("Senior Data Engineer - Remote") == "senior data engineer"


def test_normalize_company_drops_suffixes() -> None:
    assert normalize_company("Acme AI, Inc.") == normalize_company("Acme AI")


def test_canonical_key_merges_across_sources() -> None:
    a = canonical_key("Acme AI, Inc.", "Sr. Data Engineer", location_bucket([], is_remote=True))
    b = canonical_key("Acme AI", "Senior Data Engineer", location_bucket(["x"], is_remote=True))
    c = canonical_key("Acme AI", "Senior Data Engineer", location_bucket(["Pune"], is_remote=False))
    assert a == b
    assert a != c
