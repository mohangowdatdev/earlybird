# 0002. Two planes: public on GitHub, private on the laptop

- Status: Accepted
- Date: 2026-10-18

## Context

Collecting public postings is the same work for everyone and can run unattended on free infrastructure. Scoring, tracking and email ingestion involve personal data and must stay private.

## Decision

- **Public plane:** GitHub Actions polls, normalizes, dedupes and does generic extraction, then publishes a public dataset. GitHub Pages hosts the board and landing page.
- **Private plane:** the laptop syncs that dataset, ingests email alerts, scores against the private profile, and hosts the tracker and portal.

## Consequences

- Free, always-on collection without a server. Personal data never leaves the laptop.
- One public dataset can serve many private planes later (the multi-user path).
- Freshness depends on the cron cadence and the laptop being awake for alerts.
- Two environments to operate; their contract is the dataset format ([ADR 0009](0009-public-state-in-release-assets.md)).

## Alternatives considered

- **Everything on the laptop:** misses polls while the laptop sleeps, and has no public board.
- **Everything in the cloud:** costs money and puts personal data on a server.
