# Data model

> Last updated: 2026-10-18 · Related: [architecture](architecture.md) · [matching](matching.md) · [privacy-and-ethics](privacy-and-ethics.md)

This is a draft. Concrete types land with the code in Phase 0b/1, and this doc is updated in the same commits.

## Job

`Job` is the normalized model every adapter emits (`earlybird.core.models.Job`, pydantic v2).

| Field | Type | Notes |
| --- | --- | --- |
| `source` | str | Adapter id, e.g. `greenhouse` |
| `external_id` | str | The source's own id for the posting |
| `company_slug` | str | Registry key |
| `company_name` | str | Display name |
| `title` | str | As posted |
| `url` | str | Link to the original posting (always the canonical apply/listing URL) |
| `locations` | list[str] | As posted, normalized whitespace |
| `remote_raw` | str \| None | The source's own remote flag or wording |
| `department` | str \| None | |
| `employment_type` | str \| None | full-time, contract, … |
| `posted_at` | datetime \| None | From the source, when provided; often actually "updated at" |
| `description_text` | str \| None | Plain text. **Used for extraction only; never published.** |
| `salary_raw` | str \| None | If stated |
| `raw` | dict | Original payload fragment. Local/debug only, never published. |

## Derived fields

| Field | Type | Set by |
| --- | --- | --- |
| `job_id` | str | Stable hash of `(source, external_id)` |
| `canonical_key` | str | Normalized `company + title + primary location` hash, for merging across sources |
| `first_seen_at` / `last_seen_at` | datetime | Dedupe. **Dawn ranks by `first_seen_at`** because `posted_at` is unreliable. |
| `closed_at` | datetime \| None | Set when a job disappears from its source for 2 consecutive runs |
| `seen_on` | list[{source, url, first_seen_at}] | All sources this job appeared on |
| `remote_type` | enum | `onsite`, `hybrid`, `remote_india_ok`, `remote_restricted`, `remote_unspecified`, `unknown` |
| `yoe_min` / `yoe_max` | int \| None | Generic extraction |
| `seniority` | enum \| None | `junior`, `mid`, `senior`, `staff_plus`, `lead_manager`, `unknown` |
| `stack` | list[str] | Normalized skill tags |
| `salary` | {min, max, currency, period} \| None | When stated |
| `summary` | str | One line, built from facts by template (no LLM needed) |
| `extraction_method` | enum | `rules`, `llm`, `mixed` |
| `visibility` | enum | `public` (ATS and boards) or `private` (email-derived). **Private never leaves the private plane.** |

## Public dataset (Release assets, [ADR 0009](decisions/0009-public-state-in-release-assets.md))

| Asset | Contents | Consumer |
| --- | --- | --- |
| `state.db.zst` | Full public-plane SQLite (public fields only, no `description_text` beyond 90 days, no `raw`) | Next Actions run; `make sync` |
| `jobs.json` | Slim card fields for open jobs only: `job_id, title, company_name, url, locations, remote_type, yoe_min, yoe_max, seniority, stack, summary, first_seen_at, sources` | Earlybird Board (client-side filter) |
| `health.json` | Per-source last runs, statuses, counts, `generated_at` | Portal health banner; landing page counts |
| `checksums.txt` | SHA-256 of each asset | Integrity check on download |

> Whether `description_text` should be stored in the public state at all is an open design point. It helps re-extraction, but it is content we must not republish. The current position: store it compressed inside `state.db` for extraction only, never in `jobs.json`, and never rendered on the site. Revisit at Phase 1 review.

## Local database (`var/earlybird.db`)

The tables mirror the public schema, plus private tables:

| Table | Purpose |
| --- | --- |
| `jobs` | All jobs, public (from sync) and private (from email), with `visibility` |
| `job_sources` | `seen_on` rows |
| `adapter_runs` | `run_id, source, started_at, finished_at, status, jobs_found, jobs_new, error` |
| `scores` | `job_id, profile_version, rule_score, llm_score, fit_score, bucket, reason, excluded_reason, scored_at, method` |
| `tracker` | `job_id, status (new, seen, saved, shortlisted*, applied, interviewing, rejected, offer, dismissed), dismiss_reason, checklist (cv_tailored, referral, applied_url), updated_at`. *`shortlisted` is proposed ([portal.md](portal.md#nest-from-triage-to-real-applications)).* |
| `notes` | `job_id, body, created_at` |
| `feedback` | Save/dismiss events used as scoring examples |
| `watchlist` | Perch companies (mirrors the profile; editable in the portal) |
| `audit_misses` | "Missed it" URLs: `url, found_via, logged_at, job_id?, outcome_class, detail, fix_status` ([coverage.md](coverage.md#outcome-classes)) |
| `notifications` | Chirp sends, for the daily cap and dedupe |

**Portability:** use SQLAlchemy Core types only; timestamps as UTC ISO; no SQLite-specific SQL in queries. Alembic owns all schema changes.
