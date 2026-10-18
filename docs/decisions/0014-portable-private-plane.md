# 0014. Portable private plane; hosting candidates for later

- Status: Accepted
- Date: 2026-10-18

## Context

GitHub (public plane) and the laptop (private plane) are the defaults. Later, the private plane may need to run somewhere always-on: for alerts while the laptop sleeps, for a hosted product, or as a deliberate portfolio upgrade. Moving should be a deploy, not a rewrite.

## Decision

**Portability rules, effective now:**
- All configuration comes from environment variables via pydantic-settings (prefix `EARLYBIRD_`), with `.env` for local use. Nothing is hard-coded: not paths, hosts, ports, the DB location, credentials or the dataset repo.
- The database is reached only through `EARLYBIRD_DATABASE_URL` (SQLAlchemy). SQLite locally; Postgres when hosted. The SQL stays portable ([ADR 0003](0003-no-docker.md)).
- Every scheduled task is a plain CLI command (`earlybird sync`, `earlybird email`, `earlybird score`, `earlybird chirp`). Locally the honcho scheduler runs them; elsewhere any cron or job runner can.
- Processes are stateless apart from the DB and the data dir (`EARLYBIRD_DATA_DIR`). Logs go to stdout (JSON when not a TTY); files under `var/logs` are a local convenience only.
- The portal binds to `EARLYBIRD_PORTAL_HOST`, `127.0.0.1` by default.

**Hosting candidates, for later:**

| Option | Cost | Notes |
| --- | --- | --- |
| Oracle Cloud Always Free (ARM VM) | Free | Generous, but free ARM capacity is often unavailable and idle instances can be reclaimed |
| Hetzner VPS | Paid (a few € a month) | Simple and reliable; breaks zero spend |
| Railway | Paid after a trial | Easy deploys; no lasting free tier |
| Azure-native: Container Apps Jobs (one job per CLI command) + Azure Database for PostgreSQL | Free grants and new-account credits, then paid | A deliberate portfolio upgrade. Must be a **personal** subscription ([ADR 0008](0008-no-company-resources.md)). Verify the free-grant terms at the time. |

**A Dockerfile is added only when we move.** It isn't needed before ([ADR 0003](0003-no-docker.md)).

## Consequences

- Config discipline from day one costs little, and makes both the move and the tests easier.
- **Moving off the laptop changes the security model.** Personal data and email credentials would sit on a server, and the portal (unauthenticated on localhost today) would **need authentication** and TLS before being exposed. The move needs its own ADR covering auth, secrets management and backups.
- Only Oracle Always Free keeps zero spend; every other candidate needs a budget decision first.

## Alternatives considered

- **Design for one host now (e.g. Azure-first):** premature, and costs money.
- **Container-first now:** contradicts ADR 0003 and adds no value on a laptop.
