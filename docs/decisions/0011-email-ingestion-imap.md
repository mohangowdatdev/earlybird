# 0011. Email ingestion via IMAP app password (Gmail API as fallback)

- Status: Accepted (verify at build time)
- Date: 2026-10-18

## Context

LinkedIn, Naukri and Wellfound can't be scraped; their alert emails are the legitimate channel. The Gmail API needs a Google Cloud OAuth app. In "Testing" status, its refresh tokens expire every 7 days, which would force a weekly re-consent.

## Decision

Read a dedicated Gmail label over **IMAP with an app password** (requires 2-Step Verification), read-only and incremental by UID. Keep the Gmail API as a fallback if Google restricts app passwords. **Re-verify Google's app-password policy before building (Phase 2).**

## Consequences

- No Google Cloud project, no weekly re-consent, and free.
- An app password grants full mailbox access. Store it only in `.env`; the code only ever selects the one label, read-only.
- Parsers depend on email templates, which change. Save fixture emails and run a parser health check.

## Alternatives considered

- **Gmail API with OAuth:** finer scopes, but token expiry and setup burden.
- **Forwarding to a parsing service:** sends private email to a third party.
