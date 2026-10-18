# 0008. Nothing company-owned

- Status: Accepted
- Date: 2026-10-18

## Context

This is a personal project that may become a company. Any use of employer resources would create IP and policy risk.

## Decision

Use no employer cloud credits, accounts, machines, API keys or email addresses. The repo lives under the personal GitHub account `mohangowdatdev`, and commits use the personal address `mohangowdat.dev@gmail.com`, set in the repo-local git config because the machine's global identity is an employer address.

## Consequences

Every new account or key must be personal. Check `git config user.email` before the first commit in any new clone.

## Alternatives considered

None acceptable.
