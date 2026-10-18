"""Small text helpers shared by adapters and normalization."""

import html
import re
from datetime import UTC, datetime

_TAG = re.compile(r"<[^>]+>")
_BLOCK = re.compile(r"</?(p|div|br|li|ul|ol|h[1-6]|tr)[^>]*>", re.IGNORECASE)
_SPACES = re.compile("[ \t\u00a0]+")
_NEWLINES = re.compile(r"\n\s*\n+")


def html_to_text(raw: str | None) -> str | None:
    """Convert (possibly entity-escaped) HTML to readable plain text."""
    if not raw:
        return None
    text = html.unescape(raw)  # some APIs double-escape their HTML
    text = _BLOCK.sub("\n", text)
    text = html.unescape(_TAG.sub(" ", text))
    text = _SPACES.sub(" ", text)
    text = _NEWLINES.sub("\n\n", text)
    return text.strip() or None


def clean(value: str | None) -> str | None:
    """Collapse whitespace; empty becomes None."""
    if value is None:
        return None
    collapsed = _SPACES.sub(" ", value).strip()
    return collapsed or None


def from_epoch_ms(value: float | None) -> datetime | None:
    return datetime.fromtimestamp(value / 1000, tz=UTC) if value else None


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """`Acme AI, Inc.` -> `acme-ai-inc`. Used to key companies seen only on boards."""
    return _NON_SLUG.sub("-", value.lower()).strip("-") or "unknown"
