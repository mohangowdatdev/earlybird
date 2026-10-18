# Data model

> Last updated: 2026-10-18 · Related: [architecture](architecture.md) · [matching](matching.md) · [privacy-and-ethics](privacy-and-ethics.md)

Implemented in `earlybird.core.models`, `earlybird.enrich.models` and `earlybird.db.schema` (migration `0001`).

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
| `salary_min` / `salary_max` / `salary_currency` / `salary_period` | | From structured source fields only; never guessed |

## Derived fields

| Field | Type | Set by |
| --- | --- | --- |
| `job_id` | str | Stable hash of `(source, external_id)` |
| `canonical_key` | str | Normalized `company + title + primary location` hash, for merging across sources |
| `first_seen_at` / `last_seen_at` | datetime | Dedupe. **Dawn ranks by `first_seen_at`** because `posted_at` is unreliable. |
| `closed_at` | datetime \| None | Set when a job disappears from its source for 2 consecutive runs |
| *seen on* | derived | Each `(source, external_id)` is its own row; rows sharing a `canonical_key` are one job seen on several sources. Grouping happens at read time (Dawn), so a bad merge is never destructive. |
| `remote_type` | enum | `onsite`, `hybrid`, `remote_india_ok`, `remote_restricted`, `remote_unspecified`, `unknown` |
| `yoe_min` / `yoe_max` | int \| None | Generic extraction |
| `seniority` | enum \| None | `junior`, `mid`, `senior`, `staff_plus`, `lead_manager`, `unknown` |
| `stack` | list[str] | Normalized skill tags |
| `summary` | str | One line, built from facts by template (no LLM needed) |
| `content_hash` | str | Hash of the source content; a change triggers re-extraction |
| `missed_runs` | int | Consecutive successful company fetches that didn't list the job (2 → closed) |
| `extraction_method` | enum | `rules`, `llm`, `mixed` |
| `visibility` | enum | `public` (ATS and boards) or `private` (email-derived). **Private never leaves the private plane.** |

## Public dataset (Release assets, [ADR 0009](decisions/0009-public-state-in-release-assets.md))

| Asset | Contents | Consumer |
| --- | --- | --- |
| `state.db.gz` | Full public-plane SQLite: `jobs` (with `description_text` always NULL), `adapter_runs`, `company_status`. Private tables exist but are empty, and the publish guard enforces that. | Next Actions run; `make sync` |
| `state.prev.db.gz` | The previous snapshot (one-step rollback) | Recovery |
| `jobs.json` | Slim card fields for open jobs only: `job_id, title, company_name, url, locations, remote_type, yoe_min, yoe_max, seniority, stack, summary, first_seen_at, sources` | Earlybird Board (client-side filter) |
| `health.json` | Per-source last runs, statuses, counts, `generated_at` | Portal health banner; landing page counts |
| `checksums.txt` | SHA-256 of each asset | Integrity check on download |

> **Decided (2026-10-18):** descriptions are **never stored in the public state**. A downloadable `state.db` containing them would be republishing. Extraction runs on the fresh fetch, then the text is dropped. The public dataset carries the extracted `stack` and facts instead. When the private plane needs full text (e.g. LLM scoring), it fetches the posting on demand and keeps it locally only. `publish` refuses to run if any `description_text` is present.

## Local database (`var/earlybird.db`)

The tables mirror the public schema, plus private tables:

| Table | Purpose |
| --- | --- |
| `jobs` | All jobs, public (from sync) and private (from email), with `visibility` |
| `adapter_runs` | `run_id, source, started_at, finished_at, status (ok/partial/error), companies_total, companies_failed, jobs_found, jobs_new, error` |
| `company_status` | Per registry company and ATS: `status (ok/not_found/error), last_checked_at, consecutive_failures, open_jobs`. Dead slugs come from here. |
| `app_state` | Small key/value store: `last_sync_at`, `last_visit_at` (for Dawn's "new" badges) |
| `scores` *(Phase 2, with the LLM)* | Rule scores are computed on the fly today (fast, never stale); persisted scores arrive with LLM scoring: `job_id, profile_version, rule_score, llm_score, fit_score, bucket, reason, excluded_reason, scored_at, method` |
| `tracker` | `job_id, status (new, seen, saved, shortlisted*, applied, interviewing, rejected, offer, dismissed), reason (one-word dismiss reason), note, updated_at`. *`shortlisted` is proposed ([portal.md](portal.md#nest-from-triage-to-real-applications)); the checklist arrives with it.* |
| `notes` | `job_id, body, created_at` |
| `feedback` | Save/dismiss events used as scoring examples |
| `watchlist` | Perch companies (mirrors the profile; editable in the portal) |
| `audit_misses` | "Missed it" URLs: `url, found_via, logged_at, job_id?, outcome_class, detail, fix_status` ([coverage.md](coverage.md#outcome-classes)) |
| `notifications` | Chirp sends, for the daily cap and dedupe |

**Portability:** use SQLAlchemy Core types only; timestamps as UTC ISO; no SQLite-specific SQL in queries. Alembic owns all schema changes.
