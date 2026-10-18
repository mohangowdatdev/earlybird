# 0003. No Docker: uv, SQLite, honcho, Makefile

- Status: Accepted
- Date: 2026-10-18

## Context

The project is a single-user Python app on a Mac, plus GitHub Actions. Docker adds weight (Docker Desktop, volumes, rebuilds) without solving a real problem here.

## Decision

- **Python 3.13 managed by `uv`**, with a lockfile.
- **SQLite** at `var/earlybird.db`, accessed via SQLAlchemy Core with Alembic migrations, keeping the SQL portable to Postgres.
- A **`Makefile`** front-end: `make up` starts a **honcho** process group from the `Procfile` in the background (pidfile + logs in `var/`), and `make down` stops it. `make logs`, `make sync` and a guarded `make reset` complete the set.

## Consequences

- One-command setup, fast iteration, and data that survives `up`/`down`.
- Process supervision is basic (no auto-restart). Acceptable now; launchd can add start-at-login later.

## Alternatives considered

- **Docker Compose:** heavy for this use, and Docker Desktop licensing and resource costs.
- **overmind:** needs tmux.
- **supervisord:** more config than two processes justify.
