# Sources

> Last updated: 2026-10-18 · Related: [privacy-and-ethics](privacy-and-ethics.md) · [contributing](contributing.md#adding-an-adapter)

Every adapter emits the same normalized `Job` model. **The company registry is the real coverage limit:** an ATS adapter only sees companies listed in [`registry/companies.yaml`](../registry/companies.yaml).

**Status legend:** `planned` → `verified` (endpoint shape checked against a live response and saved as a fixture) → `live` (running in Actions) → `broken` / `paused`.

**Tiers:**
- **T1:** core coverage, must be healthy
- **T2:** expanded coverage
- **T3:** optional or contrib

> **Rule:** endpoint shapes below are from prior knowledge and are **unverified**. Each one is checked against a live response and saved as a fixture before its adapter is written.

## ATS adapters (per company slug)

| Source | Method | Endpoint (to verify) | Tier | Phase | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Greenhouse | GET JSON | `boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true` | T1 | 1 | planned | Official public Job Board API |
| Lever | GET JSON | `api.lever.co/v0/postings/{slug}?mode=json` | T1 | 1 | planned | Official public postings API; EU tenants use `api.eu.lever.co` |
| Ashby | GET JSON | `api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true` | T1 | 1 | planned | Official public posting API |
| Workable | GET JSON | `apply.workable.com/api/v1/widget/accounts/{slug}` | T2 | 3 | planned | Widget API |
| SmartRecruiters | GET JSON | `api.smartrecruiters.com/v1/companies/{slug}/postings` | T2 | 3 | planned | Public postings API, paginated |
| Workday | POST JSON | `{tenant}.wd{n}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` | T2 | 3 | planned | Paginated POST per tenant; the registry needs tenant, wd number and site |
| Recruitee | GET JSON | `{slug}.recruitee.com/api/offers/` | T2 | 3 | planned | |
| BambooHR | GET JSON | `{slug}.bamboohr.com/careers/list` | T2 | 3 | planned | |
| Personio | GET XML | `{slug}.jobs.personio.de/xml` | T2 | 3 | planned | XML feed |
| Teamtailor | GET | `{slug}.teamtailor.com/jobs.rss` | T2 | 3 | planned | RSS; the API needs a key, so use the feed |
| Breezy | GET JSON | `{slug}.breezy.hr/json` | T2 | 3 | planned | |
| Eightfold | GET JSON | `{tenant}.eightfold.ai/api/apply/v2/jobs?domain=…` | T2 | 3 | planned | Check terms carefully before enabling |

## Board feeds

| Source | Method | Endpoint (to verify) | Tier | Phase | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| RemoteOK | GET JSON | `remoteok.com/api` | T1 | 1 | planned | Terms require attribution and a link back; honour them on the public board |
| Himalayas | GET JSON | `himalayas.app/jobs/api` | T1 | 1 | planned | Paginated |
| We Work Remotely | GET RSS | `weworkremotely.com/categories/*.rss` | T1 | 1 | planned | Per-category feeds |
| Remotive | GET JSON | `remotive.com/api/remote-jobs` | T2 | 1 | planned | Jobs are delayed and the call limit is low (a few per day); respect it |

## Email ingestion (private plane only, never published)

| Source | Method | Phase | Notes |
| --- | --- | --- | --- |
| LinkedIn job alerts | IMAP, `earlybird` label | 2 | Parse title, company, location and link. Content stays private. |
| Naukri job alerts | IMAP, `earlybird` label | 2 | Same |
| Wellfound job alerts | IMAP, `earlybird` label | 2 | Same |
| Instahyre job alerts | IMAP, `earlybird` label | 2 | Optional; enabled if alerts are set up |
| Cutshort job alerts | IMAP, `earlybird` label | 2 | Optional |
| Hirist job alerts | IMAP, `earlybird` label | 2 | Optional |
| Otta / Welcome to the Jungle alerts | IMAP, `earlybird` label | 2 | Optional |

Each sender gets **its own parser** (`private/email/parsers/<sender>.py`), selected by the sender address and subject. All share the same label, pipeline, fixture tests (saved real emails, with personal details stripped) and the parser health check. An unknown sender is logged and skipped, never guessed at.

See [ADR 0011](decisions/0011-email-ingestion-imap.md).

## Big tech custom adapters (optional, `adapters/contrib/`)

Google, Amazon, Apple, Meta, Microsoft and Uber run their own career sites. These adapters are **out of scope until Mohan confirms** ([CONTEXT open question 2](../CONTEXT.md#open-questions)). If added, they must:
- use only public, unauthenticated endpoints
- respect robots.txt and terms
- be clearly labelled as contrib and disabled by default

## Discovery (Flock): free sources only

| Method | How | Phase |
| --- | --- | --- |
| Board-derived companies | Companies seen on boards whose apply URL points to a known ATS → derive the slug | 4 |
| Common Crawl index | Query the free CDX index for `boards.greenhouse.io/*`, `jobs.lever.co/*` and `jobs.ashbyhq.com/*` to harvest slugs (replaces paid search dorks, [ADR 0012](decisions/0012-zero-cost-operation.md)) | 4 |
| YC companies | The open-source YC company dataset → probe the ATS slug candidates | 4 |
| Slug probing | For a candidate company name, try likely slugs against each ATS (gently, cached) | 4 |

Candidates land in `registry/candidates.yaml` and are promoted once they return valid jobs.

## Not ingested, ever

Scraping LinkedIn, Naukri, Wellfound, Otta / Welcome to the Jungle, Instahyre, Cutshort, Hirist, Superset, or anything behind a login, a CAPTCHA or bot protection. Use their email alerts instead.

## Etiquette (every adapter)

- **Honest User-Agent:** `Earlybird/<version> (+https://github.com/mohangowdatdev/earlybird)`
- **Polite cadence:** poll every 1–2 hours at most, with per-source rate limits, retries with exponential backoff and jitter, and timeouts.
- **Conditional requests:** use `ETag`/`If-Modified-Since` where a source supports them.
- **Takedowns:** honour removal requests promptly ([privacy-and-ethics](privacy-and-ethics.md#takedowns)).
