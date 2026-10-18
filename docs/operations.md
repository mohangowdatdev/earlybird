# Operations

> Last updated: 2026-10-18 · Related: [architecture](architecture.md) · [roadmap](roadmap.md)

## Daily and weekly routine

This is how Earlybird is meant to be used; the portal is designed around it ([portal.md](portal.md)).

**Every morning (about 15 minutes):**
1. Open Dawn. Check the **health banner**: are all sources fresh, and did anything break?
2. Triage the queue until it's empty. For each job: **save**, **dismiss** with a one-word reason, or **mark applied**.
3. Pick the **top 3–5** (shortlist) to apply to properly, with a tailored CV and a referral or message. That's the real work, and it happens outside the portal.

**Once a week:**
1. Sweep YC (Work at a Startup) and LinkedIn by hand.
2. Log every good job Earlybird missed with **Missed it**. Each is auto-classified ([coverage.md](coverage.md)).
3. Review the **excluded sample** and mark mistakes.
4. Skim the coverage report: recall, miss classes, registry growth.

## Local setup

```bash
brew install uv gitleaks           # one-time (macOS)
make setup                         # uv sync + pre-commit install
cp .env.example .env               # every value is optional; features switch on when present
cp profile.example.yaml profile.yaml
```

## Make targets

| Target | What it does | Available |
| --- | --- | --- |
| `make setup` | Install dependencies and git hooks | now |
| `make lint` | ruff, mypy, import-linter, registry schema check | now |
| `make fmt` | Format and autofix | now |
| `make test` | pytest (network blocked) | now |
| `make up` | Start the portal and scheduler in the background (honcho; pidfile in `var/run/`) | Phase 0b |
| `make down` | Stop everything; data persists in `var/` | Phase 0b |
| `make logs` | Tail `var/logs/*.log` | Phase 0b |
| `make sync` | Pull the latest public dataset into the local DB | Phase 1 |
| `make reset` | **DANGEROUS.** Deletes `var/` (local DB, tracker, notes, logs). Asks you to type `earlybird` to confirm. | now |

## GitHub

- **Repo:** [`mohangowdatdev/earlybird`](https://github.com/mohangowdatdev/earlybird), public from the first commit.
- **Account:** all `gh` calls use `GH_TOKEN=$(gh auth token --user mohangowdatdev)` so that the global active account (used for other work) is never switched. The repo-local git config pins the author and a credential helper that reads `mohangowdatdev`'s token from the keychain at push time (`gh auth token --user mohangowdatdev`). No token is ever stored in the repo or on disk in plain text.

### Workflows

| Workflow | Trigger | Does | Phase |
| --- | --- | --- | --- |
| `ci.yml` | push, PR | lint, type-check, import contracts, tests, gitleaks | 0 |
| `ingest.yml` | cron every 2h + manual | adapters → dataset → `data-latest` Release | 1 |
| `site.yml` | after ingest + manual | build and deploy Pages from an artifact | 4 |
| `keepalive.yml` | monthly cron | prevents GitHub from disabling cron after 60 days of inactivity | 1 |

**Free-tier notes ([ADR 0012](decisions/0012-zero-cost-operation.md)):**
- Actions minutes are unlimited for standard runners on public repos (this repo is public).
- Pages is free for public repos.

### Secrets

Set with `gh secret set NAME`. Never commit them.

| Secret | Used by | Required |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Public-plane LLM fallback | No (off by default) |

The private plane's secrets live only in the local `.env`.

## Health checks

Every adapter run writes an `adapter_runs` row. A source is flagged when any of these holds:
- the latest run errored
- zero results three runs in a row
- `jobs_found` dropped more than 70% against its 7-day average

The whole dataset is flagged **stale** when `health.json.generated_at` is more than 4 hours old. Flags appear in `health.json`, the portal's health banner, and later as a Chirp to the owner.

## Backups

- **Public state:** the Release keeps `state.db.zst` and `state.prev.db.zst`; the public state can be rebuilt from sources at any time.
- **Private DB:** `make backup` (Phase 2) writes a timestamped copy of `var/earlybird.db` to `var/backups/`, keeping the last 14. Copy that folder somewhere safe yourself; it is personal data, so not to the repo.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Dawn is empty | Is `make up` running? Run `make logs`, then `earlybird health`, then check the age of the last sync. |
| Stale-dataset banner | `gh run list -w ingest.yml`. Was it disabled or did it fail? Re-run with `gh workflow run ingest.yml`. |
| A source shows 0 jobs | Run `earlybird ingest --source <name> --company <slug> --dry-run -v` and diff the payload against the fixture. |
| Email jobs missing | Check the IMAP login (app password revoked?), the label name, and `earlybird email --dry-run -v`. |
| Push rejected for workflow files | The token lacks the `workflow` scope: `gh auth switch -u mohangowdatdev && gh auth refresh -h github.com -s workflow; gh auth switch -u mohangowdat-sail` (gh only refreshes the active account) |
