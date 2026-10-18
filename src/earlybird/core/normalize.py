"""Normalization used for cross-source dedupe (the canonical key)."""

import hashlib
import re

_BRACKETS = re.compile(r"[\(\[][^\)\]]*[\)\]]")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_TITLE_SYNONYMS = (
    (re.compile(r"\bsr\b\.?"), "senior"),
    (re.compile(r"\bjr\b\.?"), "junior"),
    (re.compile(r"\beng\b\.?"), "engineer"),
    (re.compile(r"\bmgr\b\.?"), "manager"),
    (re.compile(r"&"), " and "),
)
_COMPANY_SUFFIXES = re.compile(
    r"\b(inc|llc|ltd|limited|gmbh|corp|corporation|co|pvt|private|plc|bv|ag|sa)\b\.?"
)
# Trailing location/remote qualifiers in titles: "Data Engineer - Remote", "Data Engineer, India"
_TITLE_TAIL = re.compile(r"\s+[-–—|,]\s+(remote|hybrid|onsite|[a-z ]+,? ?(india|us|usa|uk|eu))\s*$")


def normalize_title(title: str) -> str:
    text = title.lower()
    text = _BRACKETS.sub(" ", text)
    text = _TITLE_TAIL.sub("", text)
    for pattern, replacement in _TITLE_SYNONYMS:
        text = pattern.sub(replacement, text)
    return _NON_ALNUM.sub(" ", text).strip()


def normalize_company(name: str) -> str:
    text = _NON_ALNUM.sub(" ", name.lower())
    text = _COMPANY_SUFFIXES.sub(" ", text)
    return " ".join(text.split())


def location_bucket(locations: list[str], *, is_remote: bool) -> str:
    """Remote jobs share one bucket; otherwise the first location's city."""
    if is_remote or not locations:
        return "remote" if is_remote else "unknown"
    city = locations[0].split(",")[0]
    return _NON_ALNUM.sub(" ", city.lower()).strip() or "unknown"


def canonical_key(company_name: str, title: str, bucket: str) -> str:
    raw = f"{normalize_company(company_name)}|{normalize_title(title)}|{bucket}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]  # noqa: S324
