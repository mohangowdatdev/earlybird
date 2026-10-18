# Sources

> Last updated: 2026-10-18 · Related: [privacy-and-ethics](privacy-and-ethics.md) · [contributing](contributing.md#adding-an-adapter)

Every adapter emits the same normalized `Job` model. **The company registry is the real coverage limit:** an ATS adapter only sees companies listed in [`registry/companies.yaml`](../registry/companies.yaml).

**Public dataset:** each board declares `PUBLIC_OK`. Boards whose terms forbid redistribution (Himalayas, Remotive) are fetched **only on the private plane** (your laptop) and never published ([ADR 0015](decisions/0015-terms-restricted-sources-and-descriptions.md)).

**Status legend:** `planned` → `verified` (endpoint shape checked against a live response and saved as a fixture) → `live` (running in Actions) → `broken` / `paused`.

**Tiers:**
- **T1:** core coverage, must be healthy
- **T2:** expanded coverage
- **T3:** optional or contrib

> **Rule:** endpoint shapes below are from prior knowledge and are **unverified**. Each one is checked against a live response and saved as a fixture before its adapter is written.

## ATS adapters (per company slug)

| Source | Method | Endpoint (to verify) | Tier | Phase | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Greenhouse | GET JSON | `boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true` | T1 | 1 | verified | Verified 2026-10-18. No pagination (all jobs in one response, `meta.total`). `content` is entity-escaped HTML. `location.name` can join several places with `;` or `\|`; `offices[]` lists more. Dates: `first_published` and `updated_at`. No remote or salary field (some boards put a custom "Location Type" in `metadata`). Unknown slug: 404 |
| Lever | GET JSON | `api.lever.co/v0/postings/{slug}?mode=json` | T1 | 1 | verified | Verified 2026-10-18 (US and EU). EU tenants use `api.eu.lever.co` (registry `options: {region: eu}`); the other host returns 404 for them. A bare JSON list, unpaginated unless `skip`/`limit` are passed. `workplaceType` (onsite / hybrid / remote seen), `categories.allLocations`, `createdAt` in epoch ms, optional `salaryRange` {min, max, currency, interval like `per-year-salary`}. Unknown slug: 404 |
| Ashby | GET JSON | `api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true` | T1 | 1 | verified | Verified 2026-10-18. No pagination; `{apiVersion, jobs}`. `workplaceType` (OnSite / Hybrid / Remote / null) is the reliable remote signal: `isRemote` is also true for hybrid roles. `secondaryLocations[]`, `publishedAt`, `isListed`; `compensation.summaryComponents[]` gives Salary min/max/currency with an interval like `1 YEAR`. Unknown slug: 404; a real but empty board: 200 with `jobs: []` |
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
| RemoteOK | GET JSON | `remoteok.com/api` | T1 | 1 | verified | Verified 2026-10-18. One call returns ~100 newest jobs; element 0 is a legal notice, not a job. Terms: link back to the RemoteOK job URL (followed link, no `nofollow`) and name Remote OK as the source, no logo; honour on the public board. Most text is double-encoded UTF-8 (repaired in the adapter). `salary_min`/`max` are numbers, 0 = not stated; no currency or period given. robots.txt `Crawl-delay: 1`. |
| Himalayas | GET JSON | `himalayas.app/jobs/api?limit=20&cursor=…` | T1 | 1 | verified | Verified 2026-10-18. Cursor pagination via `nextCursor` (`offset` is deprecated); `limit` max 20; we stop after 10 pages (~200 newest of ~128k jobs). Unkeyed calls share one public allowance (a free key gives 60/min, 10k/day); docs say data refreshes about daily, so the adapter runs at most every 6h. Terms: visible Himalayas credit with a link back, Apply must use `applicationLink`, and no redistribution to other job boards or aggregators (check against the public board). Live `pubDate` is epoch seconds and `locationRestrictions` are plain names, unlike the docs (ms, objects); both are accepted. Empty restrictions = worldwide. |
| We Work Remotely | GET RSS | `weworkremotely.com/categories/{category}.rss` | T1 | 1 | verified | Verified 2026-10-18. We poll back-end, full-stack, front-end and devops-sysadmin feeds and dedupe by guid (feeds repeat items). `remote-jobs.rss` only carries the latest ~10 per category; data-science/ML feeds do not exist (301). Titles are `Company: Title`; `region` is usually "Anywhere in the World" and the flag-prefixed `country` list is the real restriction; `state` looks like HQ and is ignored. Feed `<ttl>` is 60 min. HTML pages (incl. terms) return 403 to non-browsers, so no written API terms were found. |
| Remotive | GET JSON | `remotive.com/api/remote-jobs` | T2 | 1 | verified | Verified 2026-10-18. Free feed is small (12 jobs) and delayed 24h; the `category` filter returned the same 12 jobs, so we fetch all. Advised max 4 calls a day (adapter runs at most every 6h); more than 2 a minute are blocked. Terms: link back to the Remotive URL and name Remotive as the source; do not submit jobs to third-party sites (Google Jobs, LinkedIn Jobs, Jooble…). `salary` is free text, so not parsed. `publication_date` has no timezone (read as UTC). |

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
