# CONTEXT.md — why Earlybird exists

> Last updated: 2026-10-18

## The problem

Good roles, especially remote AI and data roles, are flooded with applicants within a day or two of opening. Postings are scattered across hundreds of company career pages, applicant-tracking systems (ATS) and job boards. Checking them by hand is slow, and things still get missed. The real advantage is being among the **first** applicants, with a **tailored** application.

## What Earlybird does

It continuously collects new postings from public ATS feeds and open job boards, plus (privately) job-alert emails. It deduplicates them, then **an AI model reads each posting into one structured schema**: space (data, AI or cybersecurity), seniority, experience, work setup, where you may work from, required languages, and skills. Hard filters from your profile run on those facts, and the AI scores what's left against your skills and expectations. Every morning it shows a ranked **"new since yesterday"** view (Dawn) for a 15-minute triage, plus a tracker for applications (Nest).

**The goal behind it:** don't miss any good, relevant job from an in-scope source. When unsure, keep the job as "maybe" rather than drop it. Coverage is **measured**, not assumed ([coverage.md](docs/coverage.md)).

## Who it's for

- **First user: Mohan.** A Senior Data Engineer in Bangalore targeting remote AI and data engineering roles, possibly Bangalore hybrid too (open question).
- **Next users:** anyone who wants to be early to new roles. The system is profile-driven and never hard-coded to one person.

## How Mohan uses it (this shapes the product)

1. **Every morning:** open Dawn and check the health banner (are all sources fresh?).
2. **Triage everything new in about 15 minutes:** save, dismiss with a one-word reason, or mark as applied.
3. **Pick the top 3–5** to apply to *properly*, with a tailored CV and a referral or message.
4. **Once a week:**
   - sweep YC and LinkedIn by hand
   - review the excluded sample
   - log any good job Earlybird missed in the audit log

**The portal is for triage; applying is the real work.** Optimize for fast decisions, not endless browsing. UX details: [docs/portal.md](docs/portal.md). The routine: [docs/operations.md](docs/operations.md#daily-and-weekly-routine).

## Scope

### In scope

- **Roles: data, AI and cybersecurity only** ([ADR 0018](docs/decisions/0018-scope-data-ai-cybersecurity.md)). General SDE, full-stack and other roles are classified "other" and never reach you.
- **Public collection:**
  - ATS feeds (Greenhouse, Lever, Ashby first, then Workable, SmartRecruiters, Workday, Recruitee, BambooHR, Personio, Teamtailor, Breezy, Eightfold)
  - open boards (RemoteOK, Himalayas, We Work Remotely, Remotive)
- **Private collection:** job-alert emails from LinkedIn, Naukri, Wellfound, Instahyre, Cutshort, Hirist and Otta / Welcome to the Jungle, via one Gmail label. Never published.
- **Processing:** normalize, dedupe across sources, generic extraction, personal fit scoring with fail-open safety nets.
- **Interfaces:**
  - **Dawn** (triage), **Nest** (tracker), **Perch** (watchlist), **Chirp** (Telegram alerts)
  - weekly reviews and a recall audit
- **Growth:** **Flock** discovery that grows the company registry, and a public **Earlybird Board**.
- **Coverage verification:** a recall audit with classified misses, and a registry growth report.

### Out of scope (for now)

- Scraping LinkedIn, Naukri, Wellfound, Otta, Instahyre, Cutshort, Hirist, Superset, or anything behind a login or bot protection. **Their alert emails are the channel.**
- Auto-applying, or any automated action on third-party sites.
- Big tech custom adapters (pending a decision).
- Multi-user accounts and a hosted service (the "Beyond" phase).
- Anything that costs money.

### Non-goals

- Being a general job board or search engine. Browsing is deliberately secondary to triage.
- Republishing job descriptions.

## Product vision

- **Now:** an open-source tool (AGPL-3.0), public on GitHub from day one, that one person can run for free. GitHub hosts the public plane; the private plane runs on a laptop.
- **Later (maybe):** an open-core hosted product with multi-user profiles, managed email ingestion, hosted alerts and team features. The code is structured so the hosted parts can sit beside the open core, and the private plane can move to a server by deploy, not rewrite ([ADR 0014](docs/decisions/0014-portable-private-plane.md)). See [docs/ideas.md](docs/ideas.md).

## Constraints

- **Small, capped AI budget.** $20 approved for Claude Haiku. Hard monthly caps in code ($8 enrichment on Actions, $2 fit scoring), plus a console limit. Everything else stays on free tiers ([ADR 0017](docs/decisions/0017-claude-haiku-enrichment-with-budget.md)).
- **Nothing company-owned.** All accounts, keys and machines are personal ([ADR 0008](docs/decisions/0008-no-company-resources.md)).
- **Privacy first.** Personal data and email-derived content never leave the private plane ([ADR 0005](docs/decisions/0005-public-private-split.md)).
- **Public repo from day one.** Every commit is public, so nothing personal goes in, ever (gitleaks + `.gitignore` + review).

## Decisions so far

| # | Decision | Status |
| --- | --- | --- |
| [0001](docs/decisions/0001-record-architecture-decisions.md) | Record decisions as ADRs | Accepted |
| [0002](docs/decisions/0002-two-planes.md) | Two planes: public on GitHub, private on the laptop | Accepted |
| [0003](docs/decisions/0003-no-docker.md) | No Docker: uv + SQLite + honcho + Makefile | Accepted |
| [0004](docs/decisions/0004-agpl-open-core.md) | AGPL-3.0 with an open-core-friendly structure | Accepted |
| [0005](docs/decisions/0005-public-private-split.md) | What is public vs private | Accepted |
| [0006](docs/decisions/0006-fail-open-matching.md) | Fail-open matching: rules → LLM → buckets | Accepted |
| [0007](docs/decisions/0007-llm-provider.md) | LLM: Anthropic small model, Batch API, prompt caching. Optional, off by default. | Accepted (deferred) |
| [0008](docs/decisions/0008-no-company-resources.md) | Nothing company-owned | Accepted |
| [0009](docs/decisions/0009-public-state-in-release-assets.md) | Public dataset and state live in a rolling Release, not git | Accepted |
| [0010](docs/decisions/0010-portal-fastapi-htmx.md) | Portal: FastAPI + HTMX instead of Streamlit | Accepted |
| [0011](docs/decisions/0011-email-ingestion-imap.md) | Email ingestion via IMAP app password, Gmail API as fallback | Accepted (verify at build) |
| [0012](docs/decisions/0012-zero-cost-operation.md) | Zero-cost operation | Accepted |
| [0013](docs/decisions/0013-privacy-boundary-import-linter.md) | The privacy boundary is enforced in code | Accepted |
| [0014](docs/decisions/0014-portable-private-plane.md) | Private plane portable via config/env; hosting candidates for later | Accepted |
| [0018](docs/decisions/0018-scope-data-ai-cybersecurity.md) | Scope: data, AI and cybersecurity roles only | Accepted |
| [0017](docs/decisions/0017-claude-haiku-enrichment-with-budget.md) | Claude Haiku enrichment + fit scoring under a hard budget | Accepted |
| [0016](docs/decisions/0016-small-local-model-extraction.md) | Small local model (Ollama, Qwen2.5 3B) refines descriptions, grounded and fail-open | Accepted |
| [0015](docs/decisions/0015-terms-restricted-sources-and-descriptions.md) | Terms-restricted boards (Himalayas, Remotive) run privately; descriptions never published | Accepted (Mohan to confirm) |

## Open questions

1. Is Bangalore hybrid in scope, or remote-only? *(needed by Phase 2)*
2. Are big tech custom adapters (Google, Amazon, Apple, Meta, Microsoft, Uber) in or out? *(needed by Phase 4)*
3. Mohan's exact profile (role families, YOE, skills, location rules) and the seed company list. *(needed by Phase 1 for the registry, Phase 2 for the profile)*
4. ~~Which LLM?~~ Decided: Claude Haiku 5.5 with a $20 budget ([ADR 0017](docs/decisions/0017-claude-haiku-enrichment-with-budget.md)).
5. Should Nest get a `shortlisted` status between saved and applied, for the top 3–5 that get a tailored application? *(proposed in [portal.md](docs/portal.md); needed by Phase 2)*
6. Trademark: "Earlybird" is also a well-known VC firm's name. That's fine for an OSS tool, but check before any commercial launch.

## Human-only tasks

These need Mohan; Claude asks for them in batches when they come up.

- [x] `gh` logged in as `mohangowdatdev`
- [ ] Add the `workflow` scope to the `mohangowdatdev` token: `gh auth switch -u mohangowdatdev && gh auth refresh -h github.com -s workflow; gh auth switch -u mohangowdat-sail` (gh only refreshes the active account) (needed to push `.github/workflows/`)
- [ ] Profile and seed company list
- [ ] A Gmail app password, plus the `earlybird` label and filter (Phase 2)
- [ ] Job alerts on LinkedIn, Naukri, Wellfound and, optionally, Instahyre, Cutshort, Hirist and Otta / Welcome to the Jungle, all delivered to that label (Phase 2)
- [ ] A Telegram bot via BotFather (Phase 2)
- [x] Anthropic API key, as a GitHub secret and in the local `.env`
- [ ] A $20 spend limit set in the Anthropic console

## Decision log

Newest first. Each entry is one line; link the ADR where there is one.

- **2026-10-19:** AI pipeline: Claude Haiku enriches every posting into one schema; filters run in Mohan's order (space → experience → seniority → location & setup → languages); AI fit scoring (0–100) only on what passes; ranking by fit × freshness ([0017](docs/decisions/0017-claude-haiku-enrichment-with-budget.md)). Ollama path removed.
- **2026-10-19:** Scope narrowed to data, AI and cybersecurity; a profile picks up to two ([0018](docs/decisions/0018-scope-data-ai-cybersecurity.md)).
- **2026-10-19:** Profile rebuilt: 8-level seniority (intern … head of+), countries and cities (a city implies its country for remote), work setups, languages, free-text expectations.

- **2026-10-19:** Perch became "Dream companies": only *relevant* roles there are promoted (full role match, or partial match plus a must-have skill); hard excludes still apply. This refines ADR 0006's "bypass scoring entirely", which flooded Dawn (Cloudflare: 434 → 32).
- **2026-10-19:** A small local model (qwen2.5:3b via Ollama) refines unclear jobs from their descriptions, grounded and fail-open. 1.5B was rejected after a benchmark ([0016](docs/decisions/0016-small-local-model-extraction.md)).
- **2026-10-19:** Skills taxonomy rebuilt: 182 skills in 18 categories (cloud services, lakehouse, AI/LLM, MLOps…), cloud implications, and alias-aware profile matching. `EXTRACTOR_VERSION` re-tags existing jobs.

- **2026-10-18:** The portal was redesigned (Mohan: "the UI sucks"): a yellow design system, light and dark themes, adaptive layouts, Overview/Dawn/Nest/Explore/Sources/Profile, a live profile preview, a drag-and-drop Nest, and keyboard triage with undo ([portal.md](docs/portal.md)).

- **2026-10-18:** Phase 0b and most of Phase 1 built: the pipeline, 7 verified adapters, publish, sync, a portal with Dawn/Nest triage and a profile builder, `make up`/`down`, and the ingest workflow.
- **2026-10-18:** Profile builder in the portal (Mohan's request). `profile.yaml` stays the source of truth, edited through a validated form.
- **2026-10-18:** Rule scoring computed on the fly at read time (no stale scores). A persisted `scores` table arrives with LLM scoring.
- **2026-10-18:** Jobs stay one row per `(source, external_id)`; cross-source dedupe groups by `canonical_key` at read time, so merges are never destructive.
- **2026-10-18:** Himalayas and Remotive are private-plane-only because of their terms; descriptions are never in the public state ([0015](docs/decisions/0015-terms-restricted-sources-and-descriptions.md)).

- **2026-10-18:** Added Nest `shortlisted` status as a proposal (open question 5).
- **2026-10-18:** Added two miss classes to the recall audit beyond Mohan's five: `adapter_gap` and `dedupe_merge` ([coverage.md](docs/coverage.md)).
- **2026-10-18:** No paid job-data API for benchmarking. Use free ground truth instead: the weekly manual sweep, HN "Who is hiring", and YC Work at a Startup ([coverage.md](docs/coverage.md#benchmark-against-an-external-dataset)).
- **2026-10-18:** Private plane kept portable via config/env only; hosting candidates recorded; Dockerfile only when we move ([0014](docs/decisions/0014-portable-private-plane.md)).
- **2026-10-18:** Added email-alert parsers for Instahyre, Cutshort, Hirist and Otta / Welcome to the Jungle (private only).
- **2026-10-18:** Daily-use model recorded. The portal optimizes for fast triage decisions, not browsing ([portal.md](docs/portal.md)).
- **2026-10-18:** The repo is **public from day one** at `mohangowdatdev/earlybird`. It also makes Actions minutes and Pages free.
- **2026-10-18:** Commits authored as `Mohan Gowda T <mohangowdat.dev@gmail.com>` (repo-local config), never the machine's global identity.
- **2026-10-18:** Zero spend. The LLM became optional and off by default; discovery uses free sources instead of a paid search API ([0012](docs/decisions/0012-zero-cost-operation.md)).
- **2026-10-18:** Accepted the proposals for release-asset state ([0009](docs/decisions/0009-public-state-in-release-assets.md)), the FastAPI + HTMX portal ([0010](docs/decisions/0010-portal-fastapi-htmx.md)), IMAP email ingestion ([0011](docs/decisions/0011-email-ingestion-imap.md)) and the import-linter boundary ([0013](docs/decisions/0013-privacy-boundary-import-linter.md)).
- **2026-10-18:** Recorded the decisions from the original brief as ADRs 0001–0008.
- **2026-10-18:** Project started from the handoff brief.
