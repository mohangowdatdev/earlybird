# 0012. Zero-cost operation

- Status: Accepted
- Date: 2026-10-18

## Context

Mohan doesn't want to spend money on Earlybird yet. Every component must run free, and paid options must never run by default.

## Decision

| Need | Free choice |
| --- | --- |
| Scheduled compute | GitHub Actions on a **public** repo (unlimited minutes for standard runners; private repos get only 2,000 minutes a month, so cron stays off while private) |
| Hosting | GitHub Pages (needs a public repo on the free plan) |
| Storage | Release assets ([0009](0009-public-state-in-release-assets.md)), local SQLite |
| LLM | Off by default; rules-only matching. Optional local Ollama. Anthropic when there's a budget ([0007](0007-llm-provider.md)). |
| Discovery | Common Crawl CDX index, the open YC dataset, board-derived companies, slug probing. **No paid search API.** |
| Email | IMAP ([0011](0011-email-ingestion-imap.md)) |
| Alerts | Telegram Bot API |

## Consequences

- The repo must go public before cron ingestion starts (Phase 1).
- Matching quality leans on good rules and the fail-open design until an LLM is enabled.
- Any future paid feature must be optional, off by default, and capped.

## Alternatives considered

- Small paid budget for LLM scoring: deferred, not rejected.
