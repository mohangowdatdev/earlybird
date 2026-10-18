# 0017. Claude Haiku reads every posting into one schema, under a hard budget

- Status: Accepted
- Date: 2026-10-19
- Supersedes: [0012](0012-zero-cost-operation.md) (zero spend), [0016](0016-small-local-model-extraction.md) (local model)
- Refines: [0007](0007-llm-provider.md)

## Context

The filters weren't reliable. Location fields lie (one says "Hybrid" while the description says "Dubai only"), and skills, experience, level and eligibility live in the description. Rules and a small local model couldn't read that well enough:
- qwen2.5:1.5b mislabelled US-only roles "India OK".
- qwen2.5:3b took about 26 s/job on GitHub's CPU runners (57 jobs in 25 minutes).

Mohan approved a budget of $20 (out of $100) for a small Claude model.

## Decision

- **Enrichment, public plane.** `claude-haiku-5-5` (thinking off, effort low) reads each posting once, and again only if its content or `AI_VERSION` changes, into one strict JSON schema:
  - domain (data / ai / cybersecurity / other) and subdomain
  - an 8-level seniority
  - years of experience
  - work setup
  - eligible countries and regions
  - office cities
  - required languages
  - visa sponsorship
  - required and preferred skills
  - responsibilities
  - salary
  - a one-line summary
- **How it runs:**
  - The schema is enforced by structured outputs and re-validated with pydantic.
  - The system prompt is cached.
  - Bulk work goes through the **Batch API** (half price; collected on a later run). Small increments use direct calls, with the cache warmed first.
- **Guardrails:**
  - A conservative title **prefilter** marks obvious non-tech roles out of scope without a call.
  - Results apply only if the posting is unchanged since submission.
- **Fit scoring, private plane.** Only jobs that pass the hard filters are scored 0–100 against the profile, using the structured facts rather than descriptions. The profile is in a cached system prompt, with one score per (job, profile version).
- **Budgets are hard caps.** Every call's real usage is recorded in `ai_usage`. Open batches reserve their estimate. Enrichment defaults to $5/month (set to $8 on Actions), fit scoring to $2/month. Without `ANTHROPIC_API_KEY`, Earlybird runs on rules alone.

## Measured (2026-10-19)

| Run | Jobs | Cost | Per job |
| --- | --- | --- | --- |
| Pilot, direct, cache warmed | 45 | $0.0196 | $0.00044 |
| Ingest stage, direct | 243 | $0.0892 | $0.00037 |
| Real batch | 20 | $0.0036 | $0.00018 |
| Fit scoring | 15 | $0.0027 | $0.00018 |

The backlog (about 9k jobs after the prefilter) is about **$1.60** by batch. Ongoing costs are a few dollars a month at the current registry size. 0 of 313 responses failed to parse.

## Consequences

- Filters run on what the job actually says. Fit is judged against skills and stated expectations, not keywords.
- A small, predictable spend; Mohan should also set a matching limit in the Anthropic console.
- New postings get rule facts immediately and AI facts within one or two runs (direct calls, or a batch collected about 2h later).
- The public dataset now carries more generic facts, including short paraphrased responsibilities, never the description itself.

## Alternatives considered

- **Local model (ADR 0016):** free but too slow and too inaccurate for this schema.
- **Free API tiers:** rate limits, and some free tiers may use data for training.
- **Larger models:** unnecessary; Haiku's extraction quality was good in the pilot.
