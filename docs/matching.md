# Matching

> Last updated: 2026-10-18 · Related: [data-model](data-model.md) · ADRs [0006](decisions/0006-fail-open-matching.md), [0007](decisions/0007-llm-provider.md), [0012](decisions/0012-zero-cost-operation.md)

**Principle: fail open.** The goal is to never miss a good job. Every step may *raise* a job's rank, but only near-certain rules may exclude one, and each exclusion records its reason. Unknown means "keep".

## Two kinds of work, split by plane

| | Generic extraction | Personal fit scoring |
| --- | --- | --- |
| Question | "What is this job?" | "Is this job good for *me*?" |
| Same for everyone? | Yes | No |
| Runs on | Public plane (Actions) | Private plane (laptop) |
| Outputs | `remote_type, yoe_min/max, seniority, stack, salary, summary` | `rule_score, llm_score, fit_score, bucket, reason, excluded_reason` |
| Needs a profile? | No | Yes (`profile.yaml`) |

## Pipeline (private plane)

```text
job ──► 1. hard excludes ──► 2. rule score ──► 3. LLM fit (optional) ──► 4. bucket
            │                                                              │
            └──► excluded (with reason) ◄──────────────────────────────────┘
                 (weekly random sample goes to review)
```

### 1. Hard excludes (near-certain only)

Title patterns from the profile, for example:
- intern, internship, new grad, graduate program
- director, VP, head of, chief
- clearly non-tech functions (sales, account executive, recruiter, legal, …)

Each match stores `excluded_reason` (e.g. `title:intern`). Anything ambiguous is **not** excluded.

### 2. Rule score (0–10)

*Implemented in `earlybird.private.scoring`. Points: role family 0–4, skills 0–3, experience 0–1.5, location 0–1.5. A seniority mismatch costs −2 and a stated salary below your minimum costs −1. Scores are computed at read time, so a profile change takes effect instantly.*

The score is a weighted sum, with weights from the profile:
- **Role family:** title matches a role-family keyword (e.g. "data engineer", "ML engineer", "analytics engineer").
- **Skills:** skill keywords found in the description.
- **YOE fit:** the extracted range overlaps the profile's YOE with a tolerance of **−1 to +2 years**. Unknown YOE scores neutral, never negative.
- **Location fit:** `remote_india_ok` is best, `remote_unspecified` and `unknown` are neutral, and `hybrid` in an allowed city depends on the profile. `remote_restricted` (e.g. "US only") is down-ranked, not excluded, unless the profile says otherwise.

### 3. LLM fit (optional, off by default)

When an LLM is configured ([ADR 0007](decisions/0007-llm-provider.md)), it returns strict JSON validated by pydantic:

```json
{"yoe_min": 5, "yoe_max": 8, "remote_type": "remote_india_ok", "seniority": "senior",
 "stack": ["python", "spark", "airflow"], "salary": null,
 "fit_score": 8, "reason": "Senior DE, Spark/Airflow, remote incl. India"}
```

- The profile and rubric sit in a cached prompt prefix (prompt caching).
- Non-urgent scoring uses the Batch API, submitted in one run and collected in the next.
- Save and dismiss decisions are injected as few-shot examples.
- Calls are capped per day; anything over the cap gets the rule score only.
- Invalid JSON is retried once, then the job falls back to the rule score.

**With no LLM (the zero-cost default),** `fit_score = rule_score`, and any job with key unknowns is held in **maybe**, not excluded.

### 4. Buckets

| Bucket | Fit score | Shown in Dawn |
| --- | --- | --- |
| **Strong** | 8–10 | Top, expanded |
| **Maybe** | 5–7, or any job with unknown key facts | Below strong |
| **Excluded** | < 5, or a hard exclude | Hidden; sampled weekly |

## Safety nets

1. **Unknown means keep.** Unknown remote type, YOE or seniority never lowers a job below maybe.
2. **YOE tolerance** of −1 to +2 years around the profile.
3. **Perch bypass:** jobs from watchlist companies skip excludes and scoring and always show (marked ★).
4. **Weekly excluded sample:** a random sample (default 20) of last week's excluded jobs, shown for review. Every "this should have been kept" becomes a rule fix or a feedback example.
5. **Feedback loop:** save and dismiss clicks are stored and used as examples (LLM) and as keyword weight hints (rules).
6. **Chirp discipline:** Telegram alerts only for **strong** matches at **watchlist** companies, capped per day (default 5).
7. **Recall audit:** "Missed it" URLs are checked against the database, and every miss is classified with a suggested fix ([coverage.md](coverage.md)).
8. **Profile versioning:** scores carry `profile_version`, so a profile change triggers a re-score instead of mixing old and new scores.

## Generic extraction (public plane)

This step is rules-first and deterministic:
- **YOE:** regexes for `5+ years`, `3-5 yrs`, `minimum of 4 years`, etc. Take the minimum and maximum across matches in the requirements section where detectable.
- **Remote type:** the source flag plus location strings plus phrase rules ("remote (India)", "anywhere", "US only", "must be located in …"). The result is `unknown` when signals conflict.
- **Stack:** dictionary matching against `enrich/stack.yaml` (aliases → canonical tag).
- **Seniority:** title tokens.
- **Summary:** template, e.g. `Senior · Remote (India OK) · 5–8 yrs · Python, Spark, Airflow`.

An LLM pass on the public plane is possible later, under a hard daily cap, and only for jobs where rules left `remote_type` or YOE unknown.
