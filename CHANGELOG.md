# Changelog

All notable changes are recorded here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow SemVer (see [docs/roadmap.md](docs/roadmap.md#versioning)).

## [Unreleased]

### Added
- Public ingestion: Greenhouse, Lever, Ashby, RemoteOK, We Work Remotely adapters (verified, with real fixtures); Himalayas and Remotive on the private plane (ADR 0015).
- Pipeline: normalize, canonical-key dedupe, rule-based extraction (remote type, YOE, seniority, stack, summary), job closing, health checks.
- Publishing to the `data-latest` release with a privacy guard; `ingest.yml` every 2h, `keepalive.yml`, Dependabot.
- Private plane: `make sync`, scheduler, profile model + **profile builder**, rule scoring with fail-open buckets.
- Portal (FastAPI + HTMX): Dawn with keyboard triage and dismiss reasons, excluded view, Nest, All jobs, `/health`.
- `make db/up/down/restart/status/logs/sync/ingest`; `earlybird` CLI.
- Phase 0a: documentation set (CLAUDE.md, CONTEXT.md, README, docs/, ADRs 0001–0014), project skeleton, tooling (uv, ruff, mypy, pytest, import-linter, pre-commit, gitleaks), CI.
