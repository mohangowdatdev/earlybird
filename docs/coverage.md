# Coverage verification

> Last updated: 2026-10-18 · Related: [matching](matching.md) · [sources](sources.md) · [portal: weekly views](portal.md#weekly-views) · [roadmap Phase 3](roadmap.md#phase-3--coverage)

The goal is to never miss a good job. That's only credible if we **measure** what we miss and turn each miss into a fix.

## Recall audit

**Input:** every job Mohan would apply to that he found *anywhere* (the weekly YC and LinkedIn sweep, a friend's link, a newsletter) gets logged through **Missed it** in the portal, or `earlybird audit add <url>`.

**Process:** Earlybird resolves the URL to a company and source, looks for the job in the local DB, and classifies the outcome.

### Outcome classes

Checked in this order; the first match wins.

| Class | Test | Suggested fix (shown in the report) |
| --- | --- | --- |
| ✅ `caught` | In the DB, bucket strong or maybe, and first seen ≤ 24h after posting | none |
| `not_in_registry` | The company isn't in `registry/companies.yaml` | Add the company. Note which Flock source *should* have found it, and add that discovery path. |
| `source_not_covered` | The company or job lives on an ATS or board we have no adapter for (e.g. Workday before Phase 3, a custom careers site) | Build or prioritise that adapter; count misses per source to rank the adapter backlog |
| `adapter_gap` *(added)* | The company and its source are covered, but the job never arrived | Adapter bug: pagination, a filter, a parse error. Save the payload as a fixture, fix it, add a test. |
| `dedupe_merge` *(added)* | The job was merged into a different job by the canonical key | Tighten the canonical key (e.g. include requisition id or location); add a dedupe test case |
| `wrongly_excluded` | In the DB but bucket = excluded | Show the `excluded_reason`; fix the rule or profile; record a feedback example |
| `ranked_too_low` | In the DB, not excluded, but below the triage cut (not in the strong/maybe slice you actually reviewed) | Adjust weights or skills; record a feedback example |
| `ingested_too_late` | In the DB but first seen > 24h after posting (or after you found it) | Check cron delays, source lag (e.g. Remotive is delayed by design), poll cadence |

Mohan's five classes are kept as given. **`adapter_gap` and `dedupe_merge` are additions:** without them, adapter bugs and over-eager merges would be wrongly blamed on the registry or on scoring, and we'd fix the wrong thing.

**Metric:** `recall = caught / logged`, overall and per class, over a rolling 4-week window. **Target: ≥ 90%** (the Phase 3 done-criterion). The report lists each miss with its class and suggested fix, so every miss becomes a ticket.

**Caveat:** the sample is "jobs Mohan found by other means", so it's biased toward findable jobs. It's still the right measure for "did Earlybird save me from needing other means?"

## Registry growth report (weekly)

| Metric | Source | Plane |
| --- | --- | --- |
| Companies added this week, by discovery source (board-derived, Common Crawl, YC, slug probe, manual, audit miss) | `registry/companies.yaml` `discovered_by` / `added_at` | Public |
| Candidates found vs promoted vs rejected | `registry/candidates.yaml` | Public |
| Companies with any open roles | dataset | Public |
| Companies with **relevant** open roles (strong/maybe for your profile) | local scores | **Private** (relevance is personal) |
| Total registry size and its trend | registry | Public |

The public part goes into `health.json` and, later, onto the landing page. The private part shows only in the portal.

## Benchmark against an external dataset

**Question:** should we occasionally sample a paid job-data API to measure what we miss?

**Recommendation: no, not now.** Use free ground truth first:
1. **The weekly manual sweep** (YC + LinkedIn) is already a benchmark, and it's the one that matches Mohan's real behaviour.
2. **HN "Who is hiring?"** monthly threads (free via the public HN API): a large, independent sample of startup and remote roles. Parse them, keep those matching the profile, and check how many Earlybird caught. This can be automated.
3. **YC Work at a Startup** listings, sampled by hand during the weekly sweep.

**Revisit paid sampling only if** recall plateaus below target and the free sources stop explaining why. If so: a one-off free trial or free tier, a small sample (e.g. 200 relevant jobs), used only for measurement and only where the provider's terms allow benchmarking. Never ingest it into the dataset. That keeps us within zero spend ([ADR 0012](decisions/0012-zero-cost-operation.md)) and within the "public sources only" rule.
