# Earlybird

**The early bird gets the job.**

*Every new role from company career pages, filtered to you, the morning it opens.*

> **Status:** early and working. Public ingestion from 7 verified sources, the local Dawn/Nest portal and a profile builder run today; email alerts, Chirp and the public board come next. See the [roadmap](docs/roadmap.md).

Earlybird is built for **data, AI and cybersecurity roles**. It watches public company career feeds (Greenhouse, Lever, Ashby and more) and open job boards. A small AI model reads every posting into one schema: space, seniority, experience, work setup, where you may work from, languages and skills. Your profile filters on those facts, and the AI ranks the rest by fit and freshness, so a 15-minute morning triage covers everything that opened since yesterday.

## What it does

| | Feature | What it does |
| --- | --- | --- |
| 🌅 | **Dawn** | The morning view: everything new since your last visit, deduped and ranked, strong matches first |
| 🪺 | **Nest** | Your tracker: new → seen → saved → applied → interviewing → offer, with notes |
| 🌿 | **Perch** | Watchlist companies: their jobs always reach you and are never filtered out |
| 🐦 | **Chirp** | Telegram alerts for strong matches at watchlist companies |
| 🐦‍⬛ | **Flock** | Discovery: finds new companies and adds them to the registry automatically |
| 📋 | **Earlybird Board** | A public, static board of the collected jobs |

## How it works

```mermaid
flowchart LR
  subgraph Public["Public plane · GitHub (free)"]
    A[ATS feeds<br/>Greenhouse · Lever · Ashby …] --> N[Normalize + dedupe]
    B[Job boards<br/>RemoteOK · Himalayas · WWR …] --> N
    N --> X[Generic extraction<br/>YOE · remote · stack]
    X --> R[(Release asset<br/>dataset)]
    R --> P[Pages<br/>Earlybird Board]
  end
  subgraph Private["Private plane · your laptop"]
    R -- make sync --> L[(SQLite)]
    E[Your email job alerts] --> L
    L --> S[Score vs your profile]
    S --> D[Dawn + Nest portal]
    S --> C[Chirp alerts]
  end
```

- The **public plane** only ever handles public data: job cards, generic facts, and links back to the original posting.
- The **private plane** holds everything personal: your profile, scores, statuses, notes, and jobs from your email alerts. None of it is ever published.

More detail is in [docs/architecture.md](docs/architecture.md).

## Quickstart

> Requires macOS or Linux, [uv](https://docs.astral.sh/uv/) and `make`. No Docker.

```bash
git clone https://github.com/mohangowdatdev/earlybird.git && cd earlybird
make setup                          # uv sync + pre-commit hooks
cp .env.example .env                # optional: every value has a sensible default
make up                             # portal + scheduler in the background → http://127.0.0.1:8765
                                    # first visit opens the profile builder
make sync                           # pull the latest public dataset now (the scheduler also does it hourly)
make down                           # stop everything; data persists in var/
```

## Sources

| Type | Sources | Status |
| --- | --- | --- |
| ATS (core) | Greenhouse, Lever, Ashby | Verified |
| ATS (expanded) | Workable, SmartRecruiters, Workday, Recruitee, BambooHR, Personio, Teamtailor, Breezy, Eightfold | Planned (Phase 3) |
| Boards | RemoteOK, We Work Remotely (public); Himalayas, Remotive (private only, by their terms) | Verified |
| Email alerts (private) | LinkedIn, Naukri, Wellfound, Instahyre, Cutshort, Hirist, Otta / Welcome to the Jungle alert emails | Planned (Phase 2) |

Earlybird only uses public APIs and feeds. It never scrapes behind a login or bot protection. See [docs/sources.md](docs/sources.md) and [docs/privacy-and-ethics.md](docs/privacy-and-ethics.md).

## Privacy model

- **Public:** job title, company, location, remote type, experience range, stack, a one-line summary, and a link to the original posting. Never the full description.
- **Private, and never leaves your machine:** your profile, fit scores, statuses, notes, audit logs, and every job that came from your email alerts.

## Cost

**A few dollars a month.** Infrastructure is free (GitHub's free tier and your laptop). AI enrichment and fit scoring use Claude Haiku at roughly $0.0002–0.0004 per posting, with hard monthly caps in code. Without an API key, Earlybird runs on rules alone.

## Contributing

Adding a source or a company is the most useful contribution. See [docs/contributing.md](docs/contributing.md).

## License

[AGPL-3.0](LICENSE). If you run a modified Earlybird as a network service, you must share your changes.
