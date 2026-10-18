# CLAUDE.md — standing instructions

> Last updated: 2026-10-18 · Current phase: **Phase 1 — Public ingestion (nearly done); Phase 2 started early**. See the roadmap's "Now" section.

You are the lead engineer on Earlybird. Mohan owns product decisions and reviews architecture, not lines of code.
Read [CONTEXT.md](CONTEXT.md) for the why, scope and daily use, and [docs/roadmap.md](docs/roadmap.md) for where we are.
The repo is **public from the first commit** ([mohangowdatdev/earlybird](https://github.com/mohangowdatdev/earlybird)), so treat every commit, message and issue as published.

## Working agreement

1. **Propose before you build.** At the start of each phase or sizeable feature, post a short plan (what, key decisions, what you need from Mohan) and wait for a go-ahead.
2. **Explain after you build.** In plain language: what was built, how data flows, what can break, how to debug it.
3. **Push back.** The brief is a floor, not a ceiling. Suggest better designs, flag risks, and say so when you disagree.
4. **Do the heavy lifting.** Use `gh`, `uv` and `make` yourself. Hand over only what truly needs a human (see CONTEXT.md, "Human-only tasks").
5. **Keep the docs alive.** Every decision, feature or version change updates the relevant docs **in the same commit**. Significant decisions get an ADR in `docs/decisions/`. Bump the `Last updated:` stamp on any doc you touch. Log new ideas in [docs/ideas.md](docs/ideas.md) with a date.
6. **Design for the routine.** The portal is for fast triage (a 15-minute Dawn, then the top 3–5 applied to properly), not browsing. Every screen should end in a decision ([docs/portal.md](docs/portal.md)).
7. **Measure coverage.** Every "missed" job is classified and turned into a fix ([docs/coverage.md](docs/coverage.md)).
8. **Zero spend.** Mohan is not paying for anything yet ([ADR 0012](docs/decisions/0012-zero-cost-operation.md)). Never add a paid service, a paid API call path that runs by default, or anything that needs a card on file. Paid options must stay optional and off by default.

## Architecture in five lines

- **Public plane (GitHub):** Actions polls ATS feeds and boards → normalize → dedupe → rule-based generic extraction → publishes a dataset to a rolling `data-latest` Release; Pages serves the site.
- **Private plane (laptop):** `make sync` pulls the dataset → merges email-alert jobs → scores against `profile.yaml` → Dawn/Nest portal (FastAPI + HTMX) and Chirp alerts.
- **One `Job` model.** Adapters only ever emit `earlybird.core.models.Job`, so downstream code never changes when a source is added.
- **Hard privacy boundary.** Public-plane packages (`core`, `db`, `adapters`, `health`, `discovery`, `enrich`, `publish`) must never import `private`, `notify` or `portal`. This is enforced by import-linter in CI.
- **Fail open.** If a value is unknown, keep the job in "maybe". Never silently drop it.
- **Portable private plane.** Config only via `EARLYBIRD_*` env vars (pydantic-settings, `.env` locally); the DB via `EARLYBIRD_DATABASE_URL`; scheduled work as plain CLI commands. Never hard-code paths, hosts or ports ([ADR 0014](docs/decisions/0014-portable-private-plane.md)).

Details: [docs/architecture.md](docs/architecture.md).

## Conventions

- **Python 3.13 via `uv`.** Every command runs as `uv run …`. Never call `pip`.
- **Libraries:** pydantic v2 models at every boundary; type hints everywhere (mypy strict on `src/`); `structlog` for logs (key=value, never `print`); `httpx` plus `tenacity` through the shared client in `core/http.py`, which sets the honest User-Agent, timeouts, backoff and per-source rate limits.
- **Database:** SQLAlchemy Core (no ORM magic) and Alembic migrations. SQL must stay portable to Postgres: no SQLite-only functions in queries.
- **Partial failure is normal.** One adapter failing must never fail a run. Catch it at the adapter boundary, record it in `health`, and move on.
- **Runs are idempotent.** Re-running any command on the same input yields the same state.
- **Tests:** pytest. Adapter tests replay **real saved payloads** from `tests/fixtures/<source>/` (record with care and strip anything personal). Network access is blocked in tests.
- **Style:** ruff (lint and format) and mypy.
- **Commits:** small Conventional Commits (`feat(adapters): add lever`, `docs: …`, `fix: …`), with docs updated in the same commit.
- **No dead code:** no commented-out code and no speculative abstractions.

## Commands

```bash
make setup      # uv sync + install pre-commit hooks
make lint       # ruff, mypy, import-linter, registry schema check
make test       # pytest
make fmt        # ruff format + autofix
make reset      # DANGEROUS: wipes var/ (local DB, logs). Asks for confirmation.
make db / up / down / restart / status / logs   # local portal + scheduler
make sync       # pull the public dataset
make ingest     # run a public ingestion locally into var/state.db
uv run earlybird --help
```

GitHub (always as `mohangowdatdev`, never the active global account):

```bash
GH_TOKEN=$(gh auth token --user mohangowdatdev) gh <command>
```

The repo-local git config already pins the push credentials and author (`Mohan Gowda T <mohangowdat.dev@gmail.com>`).

## Guardrails (never break these)

- Never commit secrets, `.env`, `profile.yaml`, `var/`, `*.db`, or any personal data. gitleaks runs in pre-commit and CI.
- Never publish full job descriptions. The public dataset carries card fields, generic facts, a one-line summary and a link.
- Never publish anything that came from email alerts (LinkedIn, Naukri, Wellfound, Instahyre, Cutshort, Hirist, Otta / WTTJ). Those jobs are `visibility=private` and never leave the laptop.
- Never scrape behind a login or bot protection, and never bypass robots.txt or a site's terms. Use public APIs and feeds only, and poll every 1–2 hours at most.
- Never use employer-owned resources: accounts, credits, machines, or the employer email in commits.
- Never spend money by default (see Zero spend above).

## How to resume a session

1. Read the stamp at the top of this file, then the "Now" section of [docs/roadmap.md](docs/roadmap.md).
2. Read the latest entries in the decision log in [CONTEXT.md](CONTEXT.md).
3. Run `git log --oneline -15` and `make lint test`.
4. Continue from the next unchecked item in the roadmap, or ask Mohan if a plan approval is pending.
