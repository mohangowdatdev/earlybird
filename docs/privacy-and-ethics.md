# Privacy and ethics

> Last updated: 2026-10-18 · Related: [sources](sources.md) · ADRs [0005](decisions/0005-public-private-split.md), [0013](decisions/0013-privacy-boundary-import-linter.md)

## What is public vs private

| Data | Public | Private (laptop only) | Never stored |
| --- | --- | --- | --- |
| Job card fields (title, company, location, remote type, URL) from ATS and boards | ✅ | ✅ | |
| Generic facts (YOE, stack, seniority, salary if stated) | ✅ | ✅ | |
| One-line template summary | ✅ | ✅ | |
| Full job description text | ❌ (never published or rendered) | ✅ | |
| Raw source payloads | ❌ | debug only | |
| Profile, fit scores, buckets, reasons | ❌ | ✅ | |
| Tracker statuses, notes, feedback, audit log | ❌ | ✅ | |
| **Any job that came from email alerts** (LinkedIn, Naukri, Wellfound, Instahyre, Cutshort, Hirist, Otta / WTTJ) | ❌ **never** | ✅ | |
| Email bodies | ❌ | parsed, then only the extracted fields are kept | the full email |
| Credentials (IMAP app password, Telegram token, API keys) | ❌ | `.env` only | in git |

## How this is enforced

1. **Code boundary:** public-plane packages cannot import `private`, `notify` or `portal` (import-linter in CI).
2. **Data boundary:** email-derived jobs carry `visibility=private`. The publisher only ever reads the public-plane database in Actions, which never sees email data in the first place.
3. **Environment boundary:** the Actions workflows have no profile, no email credentials and no private DB.
4. **Git boundary:** `.gitignore` covers `.env`, `profile.yaml`, `var/` and `*.db`. gitleaks runs in pre-commit and CI.
5. **Publish guard (Phase 1):** a test asserts that `jobs.json` contains only allow-listed fields.

## Public repository

The repo is public from the first commit. Every committed file, commit message and issue is public, so:
- examples use fictional data
- fixtures are stripped of personal details
- the profile and email fixtures are never committed with real content

## Scraping rules

- Public APIs and public feeds only. Never anything behind a login, CAPTCHA, paywall or bot protection.
- Respect robots.txt and each site's terms. Where terms require attribution (e.g. RemoteOK), the public board shows it.
- An honest User-Agent with a contact URL, polling every 1–2 hours at most, per-source rate limits, backoff, and conditional requests.
- Never republish full job descriptions. Link to the original so the employer gets the traffic.
- Remove closed jobs from the public board promptly.

## Takedowns

Any company or source owner can ask to be excluded by opening an issue or emailing the maintainer. Excluded slugs go into `registry/companies.yaml` with `excluded: true` and a reason, and their jobs are purged from the next dataset.

## Personal data of others

Job postings sometimes name recruiters or hiring managers. That text lives only in descriptions, which are never published. Summaries are templated from facts, so they cannot leak names.
