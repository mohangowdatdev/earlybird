# Contributing

> Last updated: 2026-10-18 · Related: [sources](sources.md) · [data-model](data-model.md)

## Setup

```bash
brew install uv gitleaks
make setup
make lint test
```

## Adding a company

Add an entry to [`registry/companies.yaml`](../registry/companies.yaml):

```yaml
- slug: acme
  name: Acme
  ats:
    - {type: greenhouse, id: acme}
  tags: [ai]
```

Run `make lint`, which validates the file against `registry/schema.json`.

## Adding an adapter

1. **Check the source is allowed:** public, unauthenticated, no bot protection, and the terms permit it. Note any legal points in [sources.md](sources.md).
2. **Verify the endpoint shape** against a live response. Save 1–3 real payloads to `tests/fixtures/<source>/`, trimmed and with nothing personal.
3. Create `src/earlybird/adapters/<ats|boards>/<source>.py` implementing the `Adapter` protocol. It must:
   - take a registry entry and the shared HTTP client
   - yield `Job` models
   - raise only `AdapterError` on failure
   - do no storage, no scoring, and no global state
4. **Tests:** parse each fixture; cover missing optional fields, an empty listing and a malformed response.
5. Register the adapter and add its rows to [sources.md](sources.md) with status `verified`.
6. Update docs and stamps in the same commit.

## Code standards

- Type hints everywhere; mypy strict on `src/`.
- pydantic models at boundaries; structlog for logs; no `print`.
- Network access only through `core/http.py`.
- Public-plane code never imports `private`, `notify` or `portal` (CI fails if it does).
- No dead code and no commented-out code.

## Commits and PRs

- Use Conventional Commits: `feat(adapters): add lever`, `fix(dedupe): …`, `docs: …`.
- Keep PRs small, with tests and doc updates included. CI must be green.
- Significant design changes need an ADR in [`decisions/`](decisions/), copied from [`template.md`](decisions/template.md).
