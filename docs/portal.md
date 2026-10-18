# Portal UX: Dawn and Nest

> Last updated: 2026-10-18 · Related: [operations: daily routine](operations.md#daily-and-weekly-routine) · [matching](matching.md) · [coverage](coverage.md) · ADR [0010](decisions/0010-portal-fastapi-htmx.md)

**Design principle:** the portal is for **triage**; applying is the real work.

## Pages and workflow

| Page | Job | Key interactions |
| --- | --- | --- |
| **Overview** (`/`) | The morning briefing | Greeting, a start-triage call to action, strong/maybe counts, saved/shortlisted/applied/interviewing tiles, top matches, source health with trend lines, pipeline bars, recent activity |
| **Dawn** (`/dawn`) | Clear the queue | Two panes on desktop: the queue on the left, details on the right. On phones the details open as a bottom sheet. Tabs: Queue / Strong / Maybe / Excluded. Keyboard triage. Each action animates the job out, auto-selects the next one, and shows an Undo toast. |
| **Nest** (`/nest`) | Turn the best jobs into real applications | A drag-and-drop board (saved → shortlisted → applied → interviewing → offer / rejected). A drawer per job holds the stage and notes. On phones the columns swipe. |
| **Explore** (`/explore`) | Look things up | Search and filters across every open job, paginated, with save and open buttons |
| **Sources** (`/sources`) | Trust the data | A health card per source with run trends, and a searchable company registry with dead links flagged |
| **Profile** (`/profile`) | Define "good" | The profile builder below, with a live preview |

Flow: **Overview → Dawn (clear the queue) → Nest (shortlist 3–5, apply properly)**, with Profile and Sources as the supporting pages. Global shortcuts: `g` then `o/d/n/e/s/p` jumps to a page, `/` searches, `?` shows the shortcut help.

## Design system

- **Look:** a warm sunrise-yellow brand (`#FFC21A`) on soft warm neutrals, with green for strong, indigo for maybe and stone for excluded. Light and dark themes follow the system setting, with a manual toggle that's remembered. Font: Inter.
- **Code:** hand-written CSS tokens and components (`portal/static/app.css`) plus vanilla JS (`app.js`), with htmx vendored locally. There is no build step and no CDN dependency except the font.
- **Components:** tag inputs with autocomplete and quick-add, option cards, toggle pills, a range slider, steppers, segmented tabs, toasts with undo, a drawer, a bottom sheet, and a modal.
- **Layouts:** a sidebar from 960px up, an icon rail between 720 and 960px, and a bottom tab bar below 720px. Verified at 1440px and 390px, in both themes, plus an automated interaction run (Playwright on Chrome). Every screen should end in a decision. There is no infinite scroll and no "browse everything" as the default. A morning session should finish with Dawn empty, in about 15 minutes.

## Profile builder (`/profile`)

The first visit goes straight here. It's eight numbered sections with a **live preview** (strong/maybe/excluded counts and the top matches, recomputed as you edit) and a sticky save bar (`⌘S`). It writes `profile.yaml`:
- name and years of experience
- role families and must-have / nice-to-have skills (suggestions come from the stack dictionary)
- accepted work arrangements and cities for hybrid/onsite
- preferred seniority and title excludes
- the Perch watchlist (suggested from the registry)
- an optional minimum salary and the Chirp cap

Saving changes the profile version, and Dawn re-scores immediately because scoring runs at read time.

## Dawn: the morning queue

```text
┌──────────────────────────────────────────────────────────────────────┐
│ ● All 9 sources fresh · last sync 06:02          [⚠ Lever: 0 jobs ×3]  │  ← health banner
├──────────────────────────────────────────────────────────────────────┤
│ 47 new since yesterday · 12 strong · 35 maybe      ⏱ 6:40  ▓▓▓▓░░ 21/47 │  ← finite queue + timer
├──────────────────────────────────────────────────────────────────────┤
│ ★ Senior Data Engineer · Acme AI                       9  strong     │
│   Remote (India OK) · 5–8 yrs · Python, Spark, Airflow · 3h ago      │
│   Greenhouse + RemoteOK                                              │
│   [s] save   [d] dismiss…   [a] applied   [o] open   [n] note        │
└──────────────────────────────────────────────────────────────────────┘
```

- **Health banner first.** Stale or broken sources are shown before any job, because an empty Dawn is only good news if every source is healthy.
- **A finite queue** of untriaged jobs only (new since the last session): strong first, then maybe, each ranked by fit score and then by `first_seen_at`. A progress counter and an optional timer make "done" visible.
- **Keyboard-first:** `j`/`k` to move, `s` save, `d` dismiss, `a` applied, `o` open the original in a new tab (also marks it seen), `n` note, `u` undo.
- **Dismiss takes a one-word reason.** A single keypress picks from a short list: `1` seniority · `2` location · `3` stack · `4` company · `5` salary · `6` domain, or type a word. Reasons feed matching ([matching: feedback loop](matching.md#safety-nets)).
- **Cards show only decision facts:** title, company (★ if on the Perch watchlist), remote type, YOE range, top stack tags, the summary, how long ago it was first seen, and its sources. Clicking through opens the original posting.
- **Filters** (remote type, YOE, fit, source, company, posted date) exist, but are collapsed by default.
- **Duplicates collapse:** one card per canonical job, listing every source it was seen on.

## Nest: from triage to real applications

| Status | Meaning |
| --- | --- |
| `new` | In Dawn, untriaged |
| `seen` | Opened but not decided (resurfaces in the next Dawn) |
| `saved` | Interesting; decide this week |
| **`shortlisted`** *(proposed)* | One of the **top 3–5** getting a proper application |
| `applied` | Submitted |
| `interviewing` | In process |
| `offer` / `rejected` | Outcome |
| `dismissed` | Not for me, with a reason |

**Proposal: add `shortlisted`.** Your routine distinguishes "worth a look" from "worth a tailored application". Shortlisted cards carry a small checklist:
- [ ] CV tailored
- [ ] referral or message sent (who)
- [ ] applied (link)

Nest warns when more than 5 jobs are shortlisted at once, to keep the effort focused.

Nest is a column board (saved → shortlisted → applied → interviewing → outcome), with notes on every job and a "days since applied" age shown on cards.

## Weekly views

- **Excluded sample:** around 20 random excluded jobs from the past week. Mark each as "correctly excluded" or "should have kept" (which creates a feedback example and flags the rule).
- **Missed it:** paste the URL of a job you found elsewhere (YC sweep, LinkedIn). The audit classifies it immediately ([coverage.md](coverage.md)).
- **Coverage report:** recall by miss class, registry growth, and source health trends.

## Deliberately secondary

The **All jobs** search view exists for lookups (e.g. "what does Acme have open?"), one click away from Dawn but never the landing page.
