# 0006. Fail-open matching

- Status: Accepted
- Date: 2026-10-18

## Context

The product's promise is to not miss good jobs. A filter that silently drops a good job is worse than one that shows a few extra.

## Decision

Matching runs hard excludes (near-certain only, with a reason stored), then a rule score, then an optional LLM fit score, then buckets: strong (8–10), maybe (5–7 or unknowns), excluded (<5). The safety nets:
- unknown means keep
- YOE tolerance of −1/+2
- Perch watchlist bypass
- a weekly excluded sample
- feedback examples
- Chirp only for strong matches at watchlist companies, with a cap

See [matching.md](../matching.md).

## Consequences

- The maybe bucket will be bigger; Dawn's ranking and keyboard triage must keep that cheap.
- Recall is measured, not assumed (the recall audit in Phase 3).

## Alternatives considered

- **LLM-only scoring:** costly, opaque, and fails closed on errors.
- **Strict rules:** fast, but drops jobs with unusual wording.
