# 0013. Privacy boundary enforced by import-linter

- Status: Accepted
- Date: 2026-10-18

## Context

The most damaging possible bug is personal or email-derived data reaching the public dataset. Convention alone won't prevent it as the code grows.

## Decision

An import-linter **forbidden** contract in CI and pre-commit: the packages `earlybird.core`, `db`, `adapters`, `health`, `discovery`, `enrich` and `publish` may not import `earlybird.private`, `notify` or `portal`. In addition:
- the publisher writes only allow-listed fields (tested)
- public workflows never receive private secrets

## Consequences

The boundary is visible and enforced. Shared code must live in public-plane packages. That's the right direction anyway, and it doubles as the open-core seam.

## Alternatives considered

- **Separate repos for private code:** stronger, but slows development. Revisit for the hosted version.
