# 0004. AGPL-3.0, open-core-friendly

- Status: Accepted
- Date: 2026-10-18

## Context

Earlybird is open source now and may become an open-core hosted product. A permissive licence would let a competitor host it without giving anything back.

## Decision

License under AGPL-3.0. Keep the structure open-core-friendly: clean package boundaries and a stable dataset contract, so hosted-only components can sit beside the core later.

## Consequences

- Anyone running a modified version as a network service must publish their changes.
- Some companies avoid AGPL dependencies. That's acceptable for an end-user tool.
- Accepting outside contributions while keeping relicensing options open would need a CLA. Decide that before the first external PR.

## Alternatives considered

- **MIT/Apache:** maximal adoption, no protection.
- **BSL/source-available:** not open source, so it hurts trust and contributions.
