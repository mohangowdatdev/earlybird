# Roadmap

> Last updated: 2026-10-18 · No dates or timelines, by design. Phases end when their done-criteria are met.

## Now

**Phase 0, step 0a:** the docs set, skeleton and repo hygiene are written. **Waiting for Mohan's review.**

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
- [ ] SQLAlchemy Core schema + first Alembic migration; `earlybird db upgrade`
- [ ] Minimal portal (FastAPI) that shows "Dawn: no jobs yet" plus a health endpoint
- [ ] `Procfile`, and `make up` / `down` / `logs` with a pidfile; data persists across both

**Done when:** Mohan has reviewed the docs, and `make up` and `make down` work with the schema live locally.

## Phase 1 — Public ingestion

- [ ] `Job` model, shared HTTP client (UA, retries, rate limits), normalize, dedupe
- [ ] Adapters: Greenhouse, Lever, Ashby; RemoteOK, Himalayas, WWR, Remotive (each verified against live responses, with fixtures)
- [ ] Registry seeded from Mohan's company list, plus schema validation
- [ ] Rules-based generic extraction (YOE, remote type, stack, seniority, summary)
- [ ] `health`: adapter run records and anomaly rules
- [ ] Publish `state.db.zst`, `jobs.json`, `health.json` to the `data-latest` Release
- [ ] `ingest.yml` cron (repo public) + `keepalive.yml`
- [ ] `make sync`

**Done when:** scheduled runs publish a clean, deduped dataset reliably (e.g. 7 consecutive days without a failed run or a corrupted snapshot).

## Phase 2 — Private plane

- [ ] `profile.yaml` schema and loading; profile versioning
- [ ] Hard excludes, rule score, buckets, safety nets
- [ ] Optional LLM layer (provider decided by then, see CONTEXT open question 4)
- [ ] Email ingestion via IMAP: one parser per sender (LinkedIn, Naukri, Wellfound; then Instahyre, Cutshort, Hirist, Otta / WTTJ); private visibility; merge with public twins
- [ ] Portal per [portal.md](portal.md): Dawn (finite queue, health banner, keyboard triage, one-word dismiss reasons), Nest (statuses incl. shortlisted, checklist, notes), Perch (watchlist)
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
