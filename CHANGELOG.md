# Changelog

All notable changes are recorded here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow SemVer (see [docs/roadmap.md](docs/roadmap.md#versioning)).

## [Unreleased]

### Added
- AI pipeline (ADR 0017): Claude Haiku enrichment of every posting into one schema (space, seniority, experience, setup, eligibility, offices, languages, visa, skills, responsibilities); Batch API for bulk; budget ledger with hard monthly caps; title prefilter.
- Scope narrowed to data / AI / cybersecurity (ADR 0018); hard filters in a fixed order; AI fit scoring (0–100) of filtered jobs; ranking by fit × freshness.
- Profile: 8-level seniority, countries and city picker, work setups, languages, expectations; detail view shows the AI's reading and fit reasoning.

### Removed
- Ollama/Qwen refinement (ADR 0016, superseded).
- Skills taxonomy (182 skills, 18 categories) with grouped suggestions and alias-aware matching; existing jobs re-tagged via `EXTRACTOR_VERSION`.
- Description-aware eligibility and location rules, plus small-model refinement (Ollama, qwen2.5:3b) with grounding checks, a time budget and a cached queue.
- Dream companies (Perch): searchable company grid, ☆ Watch on every job, relevance-gated promotion.
- Portal redesign: sunrise-yellow design system (light/dark), adaptive layout (sidebar / rail / bottom tabs), Overview dashboard, two-pane Dawn with bottom sheet on mobile, drag-and-drop Nest with drawer, Explore, Sources with registry, rebuilt profile editor (tag inputs with autocomplete, option cards, live preview, sticky save bar), toasts with undo, keyboard shortcuts with help overlay, Sync-now button.
- Public ingestion: Greenhouse, Lever, Ashby, RemoteOK, We Work Remotely adapters (verified, with real fixtures); Himalayas and Remotive on the private plane (ADR 0015).
- Pipeline: normalize, canonical-key dedupe, rule-based extraction (remote type, YOE, seniority, stack, summary), job closing, health checks.
- Publishing to the `data-latest` release with a privacy guard; `ingest.yml` every 2h, `keepalive.yml`, Dependabot.
- Private plane: `make sync`, scheduler, profile model + **profile builder**, rule scoring with fail-open buckets.
- Portal (FastAPI + HTMX): Dawn with keyboard triage and dismiss reasons, excluded view, Nest, All jobs, `/health`.
- `make db/up/down/restart/status/logs/sync/ingest`; `earlybird` CLI.
- Phase 0a: documentation set (CLAUDE.md, CONTEXT.md, README, docs/, ADRs 0001–0014), project skeleton, tooling (uv, ruff, mypy, pytest, import-linter, pre-commit, gitleaks), CI.
