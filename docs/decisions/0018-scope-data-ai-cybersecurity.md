# 0018. Scope: data, AI and cybersecurity roles only

- Status: Accepted
- Date: 2026-10-19

## Context

Mohan wants a niche tool for the three hottest spaces, not general software engineering, full-stack or other roles.

## Decision

- Every posting is classified into `data`, `ai`, `cybersecurity` or `other` by the AI enrichment step ([ADR 0017](0017-claude-haiku-enrichment-with-budget.md)), with a subdomain. Classification is by the work the person will do, not the company's product.
- A profile picks **at most two** of the three spaces (none = all three). `other` never reaches Dawn.
- Collection stays broad (whole company boards), because classification needs the posting.

## Consequences

- Much less noise. Most of the registry's 11k jobs are `other`.
- Borderline roles (forward-deployed engineers, solutions architects at data companies) follow the model's reading of the actual work. The excluded review shows them, with the reason.
