# 0009. Public dataset and state live in a rolling Release, not git

- Status: Accepted
- Date: 2026-10-18

## Context

Each Actions run needs the previous run's state: seen ids, `first_seen_at`, run history for health. The laptop needs the dataset too.
- Committing data to git bloats history forever.
- Actions cache can be evicted after 7 days unused.
- An orphan data branch works, but force-pushes are awkward and still count against repo size.

## Decision

Publish to a single rolling GitHub Release tagged `data-latest`. Each run overwrites these assets:
- `state.db.gz` (gzip: stdlib, no extra dependency)
- `state.prev.db.gz` (one-step rollback)
- `jobs.json`
- `health.json`
- `checksums.txt`

Actions downloads the state at the start of a run. `make sync` downloads it on the laptop. Pages is built from a workflow artifact, so the site adds nothing to git.

## Consequences

- Zero git growth; assets are public, free and fast to fetch.
- A run-to-run race is possible if two runs overlap. Prevent it with a workflow `concurrency` group.
- Release assets are limited to 2 GB each, which is far above our need.
- History beyond one step back isn't kept. That's acceptable because the state can be rebuilt from sources.

## Alternatives considered

- **Orphan branch, force-pushed:** works, but noisier and git-bound.
- **Actions cache:** can be evicted.
- **External storage (S3/R2):** needs an account and possibly money.
