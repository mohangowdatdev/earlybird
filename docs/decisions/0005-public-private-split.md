# 0005. Public vs private data split

- Status: Accepted
- Date: 2026-10-18

## Context

The public board is useful to others, but republishing full job descriptions or content obtained via LinkedIn/Naukri/Wellfound emails would break terms and trust. Personal data must never be published.

## Decision

- **Public:** job card fields, generic extracted facts, a one-line templated summary, and a link to the original posting. **Never** full descriptions.
- **Private and never committed:** the profile, fit scores, statuses, notes, the audit log, and **every job that came from email alerts**.

Details are in [privacy-and-ethics.md](../privacy-and-ethics.md).

## Consequences

- Publishing is defined by an allow-list of fields, guarded by a test.
- Email-derived jobs carry `visibility=private`.

## Alternatives considered

- Publishing descriptions for better search: rejected on legal and ethical grounds.
