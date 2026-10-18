# Roadmap

> Last updated: 2026-10-18 · No dates or timelines, by design. Phases end when their done-criteria are met.

## Now

**Phase 0 is built; Phase 1 is nearly done** (2026-10-18). Remaining for Phase 1: the first scheduled runs on GitHub, Mohan's seed companies, and 7 consecutive clean days. Phase 2 has started early: rule scoring, Dawn/Nest triage and the profile builder. **Waiting on:** Mohan's review, the seed list, and confirmation of [ADR 0015](decisions/0015-terms-restricted-sources-and-descriptions.md).

## Versioning

SemVer, pre-1.0. Each phase that meets its done-criteria cuts a minor version and updates `CHANGELOG.md`.

| Version | Phase |
| --- | --- |
| 0.1.0 | Phase 0, Foundation |
| 0.2.0 | Phase 1, Public ingestion |
| 0.3.0 | Phase 2, Private plane |
| 0.4.0 | Phase 3, Coverage |
| 0.5.0 | Phase 4, Growth |
| 1.0.0 | Stable for other individuals to self-host |

## Phase 0 — Foundation

**0a: docs + skeleton** (done, in review)
- [x] Folder structure, CLAUDE.md, CONTEXT.md, README, docs set (incl. portal, coverage), ADRs 0001–0014
- [x] `pyproject.toml` (uv), ruff, mypy, pytest, pre-commit, gitleaks, import-linter
- [x] Makefile skeleton, `.gitignore`, `.env.example`, `profile.example.yaml`, LICENSE
- [x] Public GitHub repo and CI workflow
- [ ] Mohan's review of the docs

**0b: running skeleton**
- [x] SQLAlchemy Core schema + first Alembic migration; `earlybird db upgrade`
- [x] Portal (FastAPI + HTMX) with a health banner and `/health`
- [x] `Procfile`, and `make up` / `down` / `logs` / `status` with a pidfile; data persists across both
- [x] Dependabot for pinned actions and Python deps

**Done when:** Mohan has reviewed the docs, and `make up` and `make down` work with the schema live locally.

## Phase 1 — Public ingestion

- [x] `Job` model, shared HTTP client (UA, retries, per-host pacing), normalize, dedupe (canonical key, read-time grouping)
- [x] Adapters: Greenhouse, Lever, Ashby; RemoteOK, Himalayas, WWR, Remotive (each verified live, with real fixtures)
- [x] Verified starter registry + schema validation
- [ ] Registry seeded from Mohan's company list
- [x] Rules-based generic extraction (YOE, remote type, stack, seniority, summary)
- [x] `health`: adapter run records, company status, anomaly rules
- [x] Publish `state.db.gz`, `jobs.json`, `health.json` (with a privacy guard) to the `data-latest` Release
- [x] `ingest.yml` cron + `keepalive.yml`
- [x] `make sync` (checksum-verified)
- [x] Terms-restricted boards routed to the private plane ([ADR 0015](decisions/0015-terms-restricted-sources-and-descriptions.md))

**Done when:** scheduled runs publish a clean, deduped dataset reliably (e.g. 7 consecutive days without a failed run or a corrupted snapshot).

## Phase 2 — Private plane

- [x] `profile.yaml` schema and loading; profile versioning; **profile builder** in the portal
- [x] Hard excludes, rule score, buckets, watchlist bypass, fail-open unknowns
- [ ] Remaining safety nets (feedback loop, weekly sample cadence)
- [ ] Optional LLM layer (provider decided by then, see CONTEXT open question 4)
- [ ] Email ingestion via IMAP: one parser per sender (LinkedIn, Naukri, Wellfound; then Instahyre, Cutshort, Hirist, Otta / WTTJ); private visibility; merge with public twins
- [x] Dawn: finite queue, health banner, keyboard triage, one-word dismiss reasons, excluded view, filters
- [x] Nest: status columns + notes
- [ ] Nest `shortlisted` checklist (pending open question 5)
- [ ] Missed it capture (logging starts early so the Phase 3 audit has data)
- [ ] Chirp (Telegram), with a daily cap
- [ ] `make backup`

**Done when:** Mohan can triage every morning from the portal in about 15 minutes.

## Phase 3 — Coverage

- [ ] Expanded ATS adapters (Workable, SmartRecruiters, Workday, Recruitee, BambooHR, Personio, Teamtailor, Breezy, Eightfold)
- [ ] Health alerts via Chirp
- [ ] Weekly excluded-sample review
- [ ] Feedback learning (save/dismiss → examples and weights)
- [ ] Recall audit with miss classification and suggested fixes ([coverage.md](coverage.md))
- [ ] Weekly registry growth report
- [ ] HN "Who is hiring" benchmark (free external recall sample)

**Done when:** the audit shows at least 90% recall on jobs Mohan would apply to.

## Phase 4 — Growth

- [ ] Flock discovery (board-derived, Common Crawl, YC, slug probing) → candidates → auto-promotion
- [ ] Earlybird Board + landing page with live counts on Pages
- [ ] Optional big tech adapters (if in scope)
- [ ] A write-up of the architecture and coverage numbers

**Done when:** the registry grows on its own and the public board is live.

## Beyond

See [ideas.md](ideas.md).
