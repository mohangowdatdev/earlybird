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


def detect_remote(job: Job) -> RemoteType:
    raw = (job.remote_raw or "").strip()
    # Any other remote_raw is a remote signal: boards put their region restriction there.
    flag_remote = raw.lower() not in _NON_REMOTE_FLAGS and not _HYBRID.search(raw)
    texts = [*job.locations, raw, job.title]
    joined = " | ".join(t for t in texts if t)

    if _HYBRID.search(joined):
        return RemoteType.HYBRID if not flag_remote else RemoteType.REMOTE_UNSPECIFIED
    if flag_remote or _REMOTE.search(joined):
        # Region evidence: the remote_raw text itself, plus the listed locations.
        region_text = " | ".join([raw if raw.lower() not in _REMOTE_FLAGS else "", *job.locations])
        if _INDIA_OK.search(region_text):
            return RemoteType.REMOTE_INDIA_OK
        if _RESTRICTED.search(region_text):
            return RemoteType.REMOTE_RESTRICTED
        return RemoteType.REMOTE_UNSPECIFIED
    if job.description_text and _DESCRIPTION_REMOTE.search(job.description_text):
        return RemoteType.REMOTE_UNSPECIFIED
    return RemoteType.ONSITE if job.locations else RemoteType.UNKNOWN


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
        Seniority.EXECUTIVE,
        re.compile(r"\b(director|vp|vice president|head of|chief|cto|ceo|cfo|coo)\b", re.I),
    ),
    (Seniority.LEAD_MANAGER, re.compile(r"\b(manager|lead|team lead|tech lead)\b", re.I)),
    (Seniority.STAFF_PLUS, re.compile(r"\b(staff|principal|distinguished|architect)\b", re.I)),
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


@cache
def _stack_matcher() -> tuple[re.Pattern[str], dict[str, str]]:
    """One alternation over every alias (longest first), mapping each alias to its tag.

    Aliases prefixed with `=` are case-sensitive (e.g. `=Go`), for names that are also
    everyday words; a tag with such an alias is not matched by its bare lowercase name.
    """
    raw = yaml.safe_load(resources.files("earlybird.enrich").joinpath("stack.yaml").read_text())
    insensitive: dict[str, str] = {}
    sensitive: dict[str, str] = {}
    for tag, aliases in raw.items():
        names = list(aliases or [])
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
    pattern = re.compile(rf"(?<![\w/.-])(?:{'|'.join(branches)})(?![\w/-])", re.I)
    return pattern, {**{k.lower(): v for k, v in sensitive.items()}, **insensitive}


def extract_stack(text: str, *, limit: int = 12) -> list[str]:
    """Stack tags ordered by how often they're mentioned (one regex pass)."""
    pattern, alias_to_tag = _stack_matcher()
    counts = Counter(alias_to_tag[m.group(0).lower()] for m in pattern.finditer(text))
    return [tag for tag, _ in counts.most_common(limit)]


def stack_tags() -> list[str]:
    """All canonical stack tags, for suggestions in the profile builder."""
    return list(dict.fromkeys(_stack_matcher()[1].values()))


# ---------- summary ----------

_REMOTE_LABELS = {
    RemoteType.ONSITE: "Onsite",
    RemoteType.HYBRID: "Hybrid",
    RemoteType.REMOTE_INDIA_OK: "Remote (India OK)",
    RemoteType.REMOTE_RESTRICTED: "Remote (restricted)",
    RemoteType.REMOTE_UNSPECIFIED: "Remote",
    RemoteType.UNKNOWN: "Location unclear",
}
_SENIORITY_LABELS = {
    Seniority.INTERN: "Intern",
    Seniority.JUNIOR: "Junior",
    Seniority.MID: "Mid",
    Seniority.SENIOR: "Senior",
    Seniority.STAFF_PLUS: "Staff+",
    Seniority.LEAD_MANAGER: "Lead/Manager",
    Seniority.EXECUTIVE: "Executive",
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
    if seniority in _SENIORITY_LABELS:
        parts.append(_SENIORITY_LABELS[seniority])
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
