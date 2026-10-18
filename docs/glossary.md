# Glossary

> Last updated: 2026-10-18

| Term | Meaning |
| --- | --- |
| **Dawn** | The morning view: new jobs since your last visit, ranked |
| **Nest** | The personal application tracker |
| **Perch** | Watchlist companies; their jobs bypass scoring |
| **Chirp** | Telegram alerts |
| **Flock** | Discovery of new companies and ATS slugs |
| **Earlybird Board** | The public static job board on GitHub Pages |
| **Public plane** | GitHub Actions + Pages; handles public data only |
| **Private plane** | Your laptop; handles personal data |
| **Adapter** | A module that fetches one source and yields `Job` models |
| **Registry** | `registry/companies.yaml`; the companies whose ATS feeds are polled |
| **Canonical key** | A hash of normalized company + title + location, used to merge one job seen on several sources |
| **Generic extraction** | Facts true for everyone (YOE, remote type, stack); public-safe |
| **Fit scoring** | Personal score against a profile; private only |
| **Bucket** | strong (8–10) / maybe (5–7 or unknowns) / excluded (<5 or a hard exclude) |
| **Fail open** | When unsure, keep the job rather than drop it |
| **Missed it** | Logging a job found elsewhere so the recall audit can check whether Earlybird caught it |
| **Recall** | Share of jobs you'd apply to that Earlybird caught on time ([coverage](coverage.md)) |
| **Shortlisted** | (Proposed) The top 3–5 jobs getting a tailored application |
| **YOE** | Years of experience |
| **ATS** | Applicant tracking system (Greenhouse, Lever, Ashby, …) |
