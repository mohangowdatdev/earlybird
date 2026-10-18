"""Rule-based generic extraction. Deterministic, free, and fail-open: unsure means `unknown`."""

import re
from collections import Counter
from functools import cache
from importlib import resources

import yaml

from earlybird.core.models import Job, RemoteType, Seniority
from earlybird.enrich.models import Facts

# ---------- remote type ----------

_REMOTE = re.compile(r"\b(remote|anywhere|distributed|work from home|wfh)\b", re.IGNORECASE)
_HYBRID = re.compile(r"\bhybrid\b", re.IGNORECASE)
_INDIA_OK = re.compile(
    r"\b(india|bangalore|bengaluru|hyderabad|pune|chennai|mumbai|delhi|gurgaon|gurugram|noida|"
    r"apac|asia|asia[- ]pacific|anywhere|worldwide|global|globally|international)\b",
    re.IGNORECASE,
)
_RESTRICTED = re.compile(
    r"\b(us|usa|u\.s\.a?|united states|north america|americas|canada|uk|united kingdom|"
    r"europe|eu|emea|namer|amer|apj|latam|latin america|germany|france|spain|netherlands|"
    r"poland|portugal|ireland|australia|new zealand|brazil|mexico|argentina|colombia|"
    r"japan|singapore|"
    r"[a-z ]+ only)\b",
    re.IGNORECASE,
)
_REMOTE_FLAGS = frozenset({"true", "remote", "fully remote", "yes"})
# remote_raw values that are *not* a remote signal (e.g. Lever/Ashby workplace types).
_NON_REMOTE_FLAGS = frozenset(
    {"", "false", "no", "onsite", "on-site", "on site", "in-office", "office", "unspecified"}
)
_DESCRIPTION_REMOTE = re.compile(
    r"\b(fully remote|100% remote|remote[- ]first|work remotely|remote position|remote role)\b",
    re.IGNORECASE,
)


# Eligibility language inside descriptions ("open to candidates in India", "must be authorized
# to work in the US"). Location fields often just say "Remote"; the truth is in the text.
_GAP = r"\W+(?:[\w'’-]+\W+){0,6}?"
_ELIGIBLE_VERB = (
    r"(?:open to|hiring (?:in|from|across)|based in|located in|reside in|residing in|"
    r"live in|living in|candidates (?:in|from|across)|work from|remote (?:in|from|within|across)|"
    r"anywhere in|eligible to work in|team in|offices? in)"
)
_INDIA_PLACES = (
    r"(?:india|bangalore|bengaluru|hyderabad|pune|chennai|mumbai|gurgaon|gurugram|noida|delhi|"
    r"apac|asia|asia[- ]pacific|anywhere in the world|worldwide|globally)"
)
_DESC_INDIA = re.compile(
    _ELIGIBLE_VERB + _GAP + _INDIA_PLACES + r"\b"
    r"|\bremote\W{1,3}(?:india|apac)\b|\b(?:india|apac)\W{1,3}remote\b",
    re.IGNORECASE,
)
_US_EU = r"(?:the )?(?:us|u\.s\.a?|usa|united states|canada|uk|united kingdom|europe|eu|emea)"
_DESC_RESTRICTED = re.compile(
    r"(?:must|should|need to|required to|will need to)\s+(?:be\s+)?(?:based|located|reside|"
    r"residing|live|living)\s+(?:in|within)\s+" + _US_EU + r"\b"
    r"|authori[sz]ed to work in\s+" + _US_EU + r"\b"
    r"|\b(?:us|u\.s\.) (?:citizens?|persons?) only\b|\bsecurity clearance\b"
    r"|\bremote\W{1,3}(?:us|usa|united states|canada|uk|europe|eu|emea|latam)\b"
    r"|\bwithin (?:the )?(?:us|united states|eu|uk)\b",
    re.IGNORECASE,
)
_LOCATION_LINE = re.compile(r"^\s*(?:job\s+)?locations?\s*[:\-–]\s*(.{3,80})$", re.I | re.M)


def description_eligibility(text: str | None) -> RemoteType | None:
    """Region eligibility stated in the description, if any (India/APAC wins: fail-open)."""
    if not text:
        return None
    if _DESC_INDIA.search(text):
        return RemoteType.REMOTE_INDIA_OK
    if _DESC_RESTRICTED.search(text):
        return RemoteType.REMOTE_RESTRICTED
    return None


def description_locations(text: str | None) -> list[str]:
    """`Location: Bengaluru, India` style lines, for postings with empty location fields."""
    if not text:
        return []
    found = [m.group(1).strip(" .") for m in _LOCATION_LINE.finditer(text)]
    return list(dict.fromkeys(found))[:3]


def _remote_region(raw: str, locations: list[str], description: str | None) -> RemoteType:
    """For a remote job: who may apply? Fields first, then the description's own words."""
    region_text = " | ".join([raw if raw.lower() not in _REMOTE_FLAGS else "", *locations])
    if _INDIA_OK.search(region_text):
        return RemoteType.REMOTE_INDIA_OK
    stated = description_eligibility(description)
    if stated is RemoteType.REMOTE_INDIA_OK:
        return stated
    if _RESTRICTED.search(region_text):
        return RemoteType.REMOTE_RESTRICTED
    return stated or RemoteType.REMOTE_UNSPECIFIED


def detect_remote(job: Job) -> RemoteType:
    raw = (job.remote_raw or "").strip()
    # Any other remote_raw is a remote signal: boards put their region restriction there.
    flag_remote = raw.lower() not in _NON_REMOTE_FLAGS and not _HYBRID.search(raw)
    locations = job.locations or description_locations(job.description_text)
    texts = [*locations, raw, job.title]
    joined = " | ".join(t for t in texts if t)

    if _HYBRID.search(joined):
        return RemoteType.HYBRID if not flag_remote else RemoteType.REMOTE_UNSPECIFIED
    if flag_remote or _REMOTE.search(joined):
        return _remote_region(raw, locations, job.description_text)
    if job.description_text and _DESCRIPTION_REMOTE.search(job.description_text):
        return description_eligibility(job.description_text) or RemoteType.REMOTE_UNSPECIFIED
    return RemoteType.ONSITE if locations else RemoteType.UNKNOWN


# ---------- years of experience ----------

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
}  # fmt: skip
_NUM = r"(\d{1,2}|" + "|".join(_NUMBER_WORDS) + r")"
_YEARS = r"\s*(?:\+\s*)?(?:years?|yrs?)"
_RANGE = re.compile(r"\b" + _NUM + r"\s*\+?\s*(?:-|–|—|to)\s*" + _NUM + _YEARS, re.IGNORECASE)
_SINGLE = re.compile(r"\b" + _NUM + r"\s*(\+)?" + _YEARS, re.IGNORECASE)
_EXPERIENCE = re.compile(r"experience|exp\b|background|track record", re.IGNORECASE)
_MAX_SANE_YOE = 20
_CONTEXT_CHARS = 120


def _num(token: str) -> int:
    return int(token) if token.isdigit() else _NUMBER_WORDS[token.lower()]


def _near_experience(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 40) : end + _CONTEXT_CHARS]
    return bool(_EXPERIENCE.search(window))


def extract_yoe(text: str | None) -> tuple[int | None, int | None]:
    """Lowest stated minimum and highest stated maximum, from experience-related mentions."""
    if not text:
        return None, None
    lows: list[int] = []
    highs: list[int] = []
    consumed: list[tuple[int, int]] = []
    for match in _RANGE.finditer(text):
        low, high = _num(match.group(1)), _num(match.group(2))
        if low <= high <= _MAX_SANE_YOE and _near_experience(text, *match.span()):
            lows.append(low)
            highs.append(high)
            consumed.append(match.span())
    for match in _SINGLE.finditer(text):
        if any(s <= match.start() < e for s, e in consumed):
            continue
        value = _num(match.group(1))
        if 0 < value <= _MAX_SANE_YOE and _near_experience(text, *match.span()):
            lows.append(value)
    return (min(lows) if lows else None), (max(highs) if highs else None)


# ---------- seniority ----------

_SENIORITY_RULES: tuple[tuple[Seniority, re.Pattern[str]], ...] = (
    (Seniority.INTERN, re.compile(r"\b(intern|internship|trainee|apprentice)\b", re.I)),
    (
        Seniority.HEAD_PLUS,
        re.compile(r"\b(head of|vp|vice president|chief|cto|ceo|cfo|coo|ciso|svp|evp)\b", re.I),
    ),
    (Seniority.DIRECTOR, re.compile(r"\bdirector\b", re.I)),
    (Seniority.LEAD_MANAGER, re.compile(r"\b(manager|lead|team lead|tech lead)\b", re.I)),
    (
        Seniority.STAFF_PRINCIPAL,
        re.compile(r"\b(staff|principal|distinguished|architect)\b", re.I),
    ),
    (Seniority.SENIOR, re.compile(r"\b(senior|sr\.?|iii|iv|level 3)\b", re.I)),
    (
        Seniority.JUNIOR,
        re.compile(r"\b(junior|jr\.?|entry[- ]level|new grad|graduate|associate)\b", re.I),
    ),
    (Seniority.MID, re.compile(r"\b(ii|mid[- ]level|intermediate)\b", re.I)),
)


def detect_seniority(title: str) -> Seniority:
    for level, pattern in _SENIORITY_RULES:
        if pattern.search(title):
            return level
    return Seniority.UNKNOWN


# ---------- stack ----------


# Bump when extraction rules or the taxonomy change: existing jobs are re-extracted on next fetch.
EXTRACTOR_VERSION = 3

POPULAR_SKILLS = (
    "python", "sql", "spark", "databricks", "airflow", "dbt", "snowflake", "bigquery",
    "aws", "azure", "gcp", "kafka", "terraform", "docker", "kubernetes", "llm", "rag",
    "pytorch", "mlflow", "langchain",
)  # fmt: skip


@cache
def _taxonomy() -> dict[str, dict[str, list[str]]]:
    """category -> canonical tag -> aliases, from stack.yaml."""
    raw = yaml.safe_load(resources.files("earlybird.enrich").joinpath("stack.yaml").read_text())
    return {category: {tag: list(aliases or []) for tag, aliases in tags.items()}
            for category, tags in raw.items()}  # fmt: skip


@cache
def _stack_matcher() -> tuple[re.Pattern[str], dict[str, str]]:
    """One alternation over every alias (longest first), mapping each alias to its tag.

    Aliases prefixed with `=` are case-sensitive (e.g. `=Go`), for names that are also
    everyday words; a tag with such an alias is not matched by its bare lowercase name.
    """
    insensitive: dict[str, str] = {}
    sensitive: dict[str, str] = {}
    for tags in _taxonomy().values():
        for tag, aliases in tags.items():
            names = list(aliases)
            if not any(n.startswith("=") and n[1:].lower() == tag for n in names):
                names.append(tag)
            for name in names:
                if name.startswith("="):
                    sensitive[name[1:]] = tag
                else:
                    insensitive[name.lower()] = tag
    branches = [f"(?-i:{re.escape(n)})" for n in sensitive]
    branches += [re.escape(n) for n in insensitive]
    branches.sort(key=len, reverse=True)
    pattern = re.compile(rf"(?<![\w/.#+-])(?:{'|'.join(branches)})(?![\w/#+-])", re.I)
    return pattern, {**{k.lower(): v for k, v in sensitive.items()}, **insensitive}


# Platform services imply their cloud, so a profile skill like "azure" matches "Azure Databricks".
_IMPLIES = {
    "azure": {
        "azure data factory", "synapse", "adls", "purview", "event hubs", "cosmos db", "aks",
        "azure functions", "azure ml", "azure openai", "microsoft fabric", "azure devops",
    },
    "aws": {
        "s3", "aws glue", "emr", "athena", "redshift", "kinesis", "sagemaker", "bedrock",
        "aws lambda", "eks", "ecs", "ec2", "dynamodb", "step functions", "cloudformation",
    },
    "gcp": {
        "bigquery", "dataflow", "dataproc", "pub/sub", "gcs", "gke", "vertex ai",
        "cloud composer", "cloud run", "bigtable",
    },
}  # fmt: skip


def extract_stack(text: str, *, limit: int = 20) -> list[str]:
    """Stack tags ordered by how often they're mentioned (one regex pass)."""
    pattern, alias_to_tag = _stack_matcher()
    counts = Counter(alias_to_tag[m.group(0).lower()] for m in pattern.finditer(text))
    if "azure databricks" in text.lower():
        counts["azure"] += 1
    for parent, children in _IMPLIES.items():
        if parent not in counts and children & counts.keys():
            counts[parent] = 1
    return [tag for tag, _ in counts.most_common(limit)]


def canonical_skill(name: str) -> str:
    """Map any alias a person types (\"pyspark\", \"postgres\") to its canonical tag."""
    key = name.strip().lower()
    return _stack_matcher()[1].get(key, key)


def stack_catalog() -> list[dict[str, str]]:
    """Every canonical tag with its category, popular ones first (for suggestions)."""
    catalog = [{"value": tag, "label": tag, "group": "Popular for data & AI"}
               for tag in POPULAR_SKILLS]  # fmt: skip
    seen = set(POPULAR_SKILLS)
    for category, tags in _taxonomy().items():
        catalog += [{"value": t, "label": t, "group": category} for t in tags if t not in seen]
    return catalog


def stack_tags() -> list[str]:
    """All canonical stack tags."""
    return [tag for tags in _taxonomy().values() for tag in tags]


# ---------- summary ----------

_REMOTE_LABELS = {
    RemoteType.ONSITE: "Onsite",
    RemoteType.HYBRID: "Hybrid",
    RemoteType.REMOTE_INDIA_OK: "Remote (India OK)",
    RemoteType.REMOTE_RESTRICTED: "Remote (restricted)",
    RemoteType.REMOTE_UNSPECIFIED: "Remote",
    RemoteType.UNKNOWN: "Location unclear",
}
SENIORITY_LABELS = {
    Seniority.INTERN: "Intern",
    Seniority.JUNIOR: "Junior",
    Seniority.MID: "Mid",
    Seniority.SENIOR: "Senior",
    Seniority.STAFF_PRINCIPAL: "Staff / Principal",
    Seniority.LEAD_MANAGER: "Lead / Manager",
    Seniority.DIRECTOR: "Director",
    Seniority.HEAD_PLUS: "Head of+",
}


def remote_label(remote_type: RemoteType) -> str:
    return _REMOTE_LABELS[remote_type]


def summarize(
    seniority: Seniority,
    remote_type: RemoteType,
    yoe: tuple[int | None, int | None],
    stack: list[str],
) -> str:
    parts = []
    if seniority in SENIORITY_LABELS:
        parts.append(SENIORITY_LABELS[seniority])
    parts.append(_REMOTE_LABELS[remote_type])
    low, high = yoe
    if low is not None and high is not None and high != low:
        parts.append(f"{low}–{high} yrs")
    elif low is not None:
        parts.append(f"{low}+ yrs")
    if stack:
        parts.append(", ".join(stack[:3]))
    return " · ".join(parts)


def extract(job: Job) -> Facts:
    text = "\n".join(t for t in (job.title, job.description_text) if t)
    remote_type = detect_remote(job)
    yoe = extract_yoe(job.description_text)
    seniority = detect_seniority(job.title)
    stack = extract_stack(text)
    return Facts(
        remote_type=remote_type,
        yoe_min=yoe[0],
        yoe_max=yoe[1],
        seniority=seniority,
        stack=stack,
        summary=summarize(seniority, remote_type, yoe, stack),
    )
